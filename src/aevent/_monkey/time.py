import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await

from time import *

@_patch
async def sleep(t):
	await _anyio.sleep(t)

