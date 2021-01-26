#
# Simple test program that sleeps in parallel.
#
# This should take half a second in total, not five.
#
import aevent
aevent.setup()

import time
import anyio

async def sleeper():
    time.sleep(0.5)

async def test():
    async with anyio.create_task_group() as tg:
        for _ in range(10):
            await tg.spawn(sleeper)
aevent.run(test)
