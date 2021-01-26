import anyio as _anyio
from greenback import await_ as _await
from aevent import _patch

from time import *

@_patch
async def sleep(t):
	await _anyio.sleep(t)

