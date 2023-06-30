import stactools.geoparquet_items


def test_version() -> None:
    assert stactools.geoparquet_items.__version__ is not None
