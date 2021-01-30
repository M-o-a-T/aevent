import aevent
import os
backend = os.environ.get("AEVENT_BACKEND","trio")
aevent.setup(backend)

from pathlib import Path
import pytest

@pytest.fixture
def anyio_backend():
    return backend

here = Path(__file__).parent

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if Path(item.fspath).is_relative_to(here):
            item.add_marker(pytest.mark.aevent)

@pytest.fixture(autouse=True)
def chdir_here():
    pwd = os.getcwd()
    os.chdir(Path("tests") / here.name)
    yield None
    os.chdir(pwd)
