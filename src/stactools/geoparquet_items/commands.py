import json
import logging
import os
from typing import Optional

import click
import geopandas
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
    def create_command(source: str, destination: str, collection: str = "") -> None:
        """Create geoparquet from STAC Items

        Args:
            source (str): Link to a list of STAC Items (ItemCollection) or a folder with STAC files.
            destination (str): Path where the geoparquet file will be stored.
        """

        items = []
        if source.startswith("https://") or source.startswith("http://"):
            print("Requesting remote source")
            response = requests.get(source)
            features = response.json().get("features")
            if features is not None:
                items = features
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
                        paths.append(path)

            print("Found {} potential STAC Items".format(len(paths)))

            for path in paths:
                with open(path) as f:
                    item = json.load(f)
                    if item["type"] == "Feature":
                        items.append(item)

        num = len(items)
        if num > 0:
            print("Loaded {} actual STAC Items".format(num))
            df = stac_geoparquet.to_geodataframe(items)
            del items
            print("Created dataframe")
            df.to_parquet(destination)
            del df
            print("Wrote geoparquet file")
        else:
            raise Exception("No items found")

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
        help="A list of comma-separated fields that should be excluded from the target file. "
        + " Use 'none' to include all fields. Default: "
        + ",".join(IGNORE_FIELDS),
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(
            ["shapefile", "gpkg", "geojson", "geojsonseq", "flatgeobuf"],
            case_sensitive=False,
        ),
        default="gpkg",
        help="File format to convert to. Default: gpkg",
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

    return geoparquetitems
