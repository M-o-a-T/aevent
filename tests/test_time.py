#
# Simple test that sleeps in parallel.
#
# This should take half a second in total, not five.
#

import pytest

import time
import anyio

import aevent

async def sleeper(t):
    time.sleep(t)

@pytest.mark.anyio
async def test_time():
    """Test that sleep() calls run in parallel."""
    t1 = time.time()
    async with anyio.create_task_group() as tg:
        for _ in range(10):
            await tg.spawn(sleeper, 0.5)
    t2 = time.time()
    assert 0.49<(t2-t1)<4

@pytest.mark.anyio
async def test_time_native():
    """Test that sleep() calls do not run in parallel."""
    t1 = time.time()
    with aevent.native():
        async with anyio.create_task_group() as tg:
            for _ in range(5):
                await tg.spawn(sleeper, 0.1)
    t2 = time.time()
    assert 0.4<(t2-t1)<2

