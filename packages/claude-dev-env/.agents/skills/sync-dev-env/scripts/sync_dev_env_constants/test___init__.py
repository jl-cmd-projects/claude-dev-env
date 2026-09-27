import sync_dev_env_constants


def test_sync_dev_env_constants_loads_as_package() -> None:
    assert sync_dev_env_constants.__path__
