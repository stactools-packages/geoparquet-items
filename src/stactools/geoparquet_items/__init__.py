import stactools.core
from stactools.cli.registry import Registry

from stactools.geoparquet_items.stac import create_collection, create_item

__all__ = ["create_collection", "create_item"]

stactools.core.use_fsspec()


def register_plugin(registry: Registry) -> None:
    from stactools.geoparquet_items import commands

    registry.register_subcommand(commands.create_geoparquetitems_command)


__version__ = "0.1.0"
