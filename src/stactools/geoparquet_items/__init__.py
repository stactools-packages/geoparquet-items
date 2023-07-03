import stactools.core
from stactools.cli.registry import Registry

__all__ = ["create"]

stactools.core.use_fsspec()


def register_plugin(registry: Registry) -> None:
    from stactools.geoparquet_items import commands

    registry.register_subcommand(commands.create_geoparquetitems_command)


__version__ = "0.1.1"
