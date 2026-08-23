import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture()
def loader():
    from hfsg.config import ConfigurationLoader

    return ConfigurationLoader()


@pytest.fixture()
def base_config(loader):
    return loader.load("config/base.yaml")