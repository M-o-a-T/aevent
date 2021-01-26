import aevent
import os
backend = os.environ.get("AEVENT_BACKEND","trio")
aevent.setup(backend)

import pytest

@pytest.fixture
def anyio_backend():
    return backend

