# stactools-geoparquet-items

[![PyPI](https://img.shields.io/pypi/v/stactools-geoparquet-items)](https://pypi.org/project/stactools-geoparquet-items/)

- Name: geoparquet-items
- Package: `stactools.geoparquet_items`
- [stactools-geoparquet-items on PyPI](https://pypi.org/project/stactools-geoparquet-items/)
- Owner: @m-mohr

Uses stac-geoparquet to generate a geoparquet for a list of STAC items.

## Installation

```shell
pip install stactools-geoparquet-items
```

## Command-line Usage

Use `stac geoparquet-items --help` to see all subcommands and options.

### Create GeoParquet from STAC Items

You need to provide a folder to read the items (deeply) from.
Then you provide a file to write the geoparquet to.
Optionally, you can add the geoparquet as an asset to a STAC Collection.

```shell
stac geoparquet-items create https://example.com/collections/id/items result.geoparquet
```

```shell
stac geoparquet-items create /path/to/folder result.geoparquet --collection /path/to/collection.json
```

### Convert from GeoParquet to other file formats

Convert from geoparquet to GeoPackage (without stac_version, type and assets):

```shell
stac geoparquet-items convert source.geoparquet result.gpkg
```

Convert to FlatGeoBuf and exclude even more fields:

```shell
stac geoparquet-items convert source.geoparquet result.fgb --format flatgeobuf --exclude stac_version,type,assets,links,collection
```

Supported formats: flatgeobuf, geojson, geojsonseq, gpkg (default), shapefile

### Show information about a geoparquet file

You can easily retrieve metadata and a data excerpt:

```shell
stac geoparquet-items info source.geoparquet
```

## Contributing

We use [pre-commit](https://pre-commit.com/) to check any changes.
To set up your development environment:

```shell
pip install -e .
pip install -r requirements-dev.txt
pre-commit install
```

To check all files:

```shell
pre-commit run --all-files
```
