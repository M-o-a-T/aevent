import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await

from queue import Queue

@_patch
class Queue:
	_size = 0
	def __init__(self, maxsize=1):
		self._size = maxsize
	def qsize(self):
		return self._size
