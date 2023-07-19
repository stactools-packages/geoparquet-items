import io
import json
import logging
import os

# Used only for partitioning / dask variant
import pathlib
import shutil
from typing import Any, Optional, Sequence

import click
import dask.bag as db
import dask_geopandas
import geopandas
import pyarrow
import pyarrow.parquet as pq
import pyogrio
import requests
import stac_geoparquet
from click import Command, Group

logger = logging.getLogger(__name__)

IGNORE_FIELDS = ["stac_version", "type", "assets"]


def create_geoparquetitems_command(cli: Group) -> Command:
    """Creates the stactools-geoparquet-items command line utility."""

    @cli.group(
        "geoparquet-items",
        short_help=("Commands for working with stactools-geoparquet-items"),
    )
    def geoparquetitems() -> None:
        pass

    @geoparquetitems.command("create", short_help="Create geoparquet from STAC Items")
    @click.argument("source")
    @click.argument("destination")
    @click.option(
        "--collection",
        default="",
        help="Adds a geoparquet asset to the Collection JSON at the given path.",
    )
    @click.option(
        "--partition",
        default=1,
        show_default=True,
        help="Runs via dask and creates the number of partitions given (if >= 2)",
    )
    @click.option(
        "--selflink",
        default=False,
        show_default=True,
        help="Tries to add the absolute link to the source STAC Item to a column named 'self_link'",
        is_flag=True,
    )
    def create_command(
        source: str,
        destination: str,
        collection: str = "",
        partition: int = 1,
        selflink: bool = False,
    ) -> None:
        """Create geoparquet from STAC Items

        Args:
            source (str): Link to a list of STAC Items (ItemCollection) or a folder with STAC files.
            destination (str): Path where the geoparquet file will be stored.
        """
        p = pathlib.Path(destination)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)

        if partition > 1:
            p.mkdir()
            print("Created destination folder")

        items = []
        bag = None
        if source.startswith("https://") or source.startswith("http://"):
            print("Requesting remote source")
            response = requests.get(source)
            features = response.json().get("features")
            if features is not None:
                items = features

            if partition > 1:
                bag = db.from_sequence(items, npartitions=partition)

        elif os.path.exists(source):
            print("Reading from file system")
            paths = []
            for root, _, files in os.walk(source):
                for name in files:
                    if not name.endswith(".json"):
                        continue
                    elif name == "catalog.json" or name == "collection.json":
                        continue
                    else:
                        path = os.path.join(root, name)
                        paths.append(pathlib.Path(path))

            print("Found {} potential STAC Items".format(len(paths)))

            if partition > 1:
                bag = (
                    db.from_sequence(paths, npartitions=partition)
                    .map(lambda file: file.read_text())
                    .map(json.loads)
                    .filter(lambda item: item["type"] == "Feature")
                )

        def create_fn(items: Sequence[dict[str, Any]]) -> geopandas.GeoDataFrame:
            return stac_geoparquet.to_geodataframe(items, add_self_link=selflink)

        if bag is not None:
            print("Initialized for parallel processing")
            # Taken from Tom Augpurger's notbook at
            # https://notebooksharing.space/view/1c2922b90622013d91dc22182e7f60d64e119c0f7cf1f977ccaa4dd0994bd1b6
            sample = create_fn(bag.take(1))
            meta = sample.iloc[:0, :]

            dfs = bag.map_partitions(create_fn)
            df = dask_geopandas.GeoDataFrame(
                dfs.dask, dfs.name, meta, [None] * (dfs.npartitions + 1)
            )

            buf = io.BytesIO()
            sample.to_parquet(buf, engine="pyarrow")
            buf.seek(0)
            schema = pq.read_schema(buf)

            df.to_parquet(destination, schema=schema, write_index=False)
            print("Wrote geoparquet file(s)")
        else:
            for p in paths:
                with p.open() as f:
                    item = json.load(f)
                    if item["type"] == "Feature":
                        items.append(item)
            del paths

            num = len(items)
            if num > 0:
                print(f"Loaded {num} actual STAC Items")
                df = create_fn(items)
                del items
                print("Created dataframe")
                df.to_parquet(destination)
                del df
                print("Wrote geoparquet file")
            else:
                raise Exception("Aborting, no items available")

        if len(collection) > 0:
            with open(collection, "r+") as f:
                collection_json = json.load(f)
                if "assets" not in collection_json:
                    collection_json["assets"] = {}

                basepath = os.path.abspath(os.path.dirname(collection))
                collection_json["assets"]["geoparquet-items"] = {
                    "href": os.path.relpath(destination, basepath),
                    "type": "application/x-parquet",
                    "roles": ["stac-items"],
                    "title": "GeoParquet STAC Items",
                }

                f.seek(0)
                json.dump(collection_json, f, indent=2)
                f.truncate()
                print("Updated STAC Collection")

        return None

    @geoparquetitems.command(
        "convert", short_help="Convert geoparquet to other OGR file formats"
    )
    @click.argument("source")
    @click.argument("destination")
    @click.option(
        "--exclude",
        "-e",
        default=",".join(IGNORE_FIELDS),
        show_default=True,
        help="A list of comma-separated fields that should be excluded from the target file. "
        + " Use 'none' to include all fields."
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(
            ["shapefile", "gpkg", "geojson", "geojsonseq", "flatgeobuf"],
            case_sensitive=False,
        ),
        default="gpkg",
        show_default=True,
        help="File format to convert to.",
    )
    def convert_command(
        source: str,
        destination: str,
        format: str = "gpkg",
        exclude: Optional[str] = None,
    ) -> None:
        """Convert geoparquet to other OGR file formats

        Args:
            source (str): Path where the geoparquet file is located.
            destination (str): Path where the new file will be stored.
        """
        if not os.path.exists(source):
            raise Exception("Source file does not exist")

        if exclude is None:
            to_exclude = IGNORE_FIELDS
        elif exclude == "none" or exclude == "NONE":
            to_exclude = []
        else:
            to_exclude = exclude.split(",")

        columns = None
        if len(to_exclude) > 0:
            schema = pq.read_schema(source)
            columns = schema.names.copy()
            for col in to_exclude:
                columns.remove(col.strip())

        df = geopandas.read_parquet(source, columns=columns)
        pyogrio.write_dataframe(df, destination, driver=format)

        return None

    @geoparquetitems.command(
        "info", short_help="Show some information about a geoparquet file"
    )
    @click.argument("source")
    def info_command(source: str) -> None:
        """Print some information about a geoparquet file

        Args:
            source (str): Path where the geoparquet file is located.
        """
        if not os.path.exists(source):
            raise Exception("Source file does not exist")
        
        metadata = pq.read_metadata(source)
        
        print("Parquet Format Version:", metadata.format_version)
        print("Created by:", metadata.created_by)
        print("Columns:", metadata.num_columns, "(", ", ".join(metadata.schema.names), ")")
        print("Rows/Items:", metadata.num_rows, "in", metadata.num_row_groups, "groups")
        print("")

        geo = json.loads(metadata.metadata[b"geo"])
        print("GeoParquet metadata:", geo)
        print("")

        print("Excerpt:")
        pf = pq.ParquetFile(source) 
        rows = next(pf.iter_batches(batch_size = 10)) 
        df = pyarrow.Table.from_batches([rows]).to_pandas()
        print(df)

        return None

    return geoparquetitems
