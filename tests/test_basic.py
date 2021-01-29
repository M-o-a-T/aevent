#
# Simple test that error handling works.
#

import pytest
import os

import anyio
import aevent

async def sleeper(t):
    time.sleep(t)

class TestMe:

    def setup(self):
        print("A")

    @pytest.mark.aevent
    def test_base(self):
        print("B")
        # testing this within Python is TODO via subprocess
        if os.environ.get("AEVENT_CRASHTEST",0):
            raise RuntimeError
    
    def teardown(self):
        print("C")

