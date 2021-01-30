import anyio as _anyio
import trio as _trio
from aevent import patch_ as _patch, await_ as _await

from queue import Queue, Empty, Full

@_patch
class Queue:
	_size = 0
	_q_r,_q_w = None,None
	_count = 0
	_count_unack = 0
	_count_zero = None

	def __init__(self, maxsize=0):
		self._size = maxsize or 9999999

	def qsize(self):
		return self._count

	def get(self, block=True, timeout=None):
		return _await(self._get(block, timeout))
	
	def get_nowait(self):
		return _await(self._get(False, 0))

	async def _get(self, block, timeout):
		if self._q_r is None:
			self._q_w,self._q_r = _anyio.create_memory_object_stream(self._size)
		if not block:
			timeout = 0.1 # TODO
		if timeout is None:
			res = await self._q_r.receive()
		else:
			try:
				async with _anyio.fail_after(timeout):
					res = await self._q_r.receive()
			except TimeoutError:
				raise Empty from None
		self._count -= 1
		return res


	def put_nowait(self, item):
		_await(self._put(item,0.1))  # TODO

	def put(self, item, timeout=None):
		_await(self._put(item,timeout))
	
	async def _put(self, item, block=True, timeout=None):
		if self._q_r is None:
			self._q_w,self._q_r = _anyio.create_memory_object_stream(self._size)

		self._count += 1
		self._count_unack += 1
		if not block:
			timeout = 0.1 # TODO
		try:
			if timeout is None:
				await self._q_w.send(item)
			else:
				try:
					async with _anyio.fail_after(timeout):
						await self._q_w.send(item)
				except TimeoutError:
					raise Full from None
		except BaseException:
			self._count -= 1
			await self._task_done()
			raise

	
	def task_done(self):
		_await(self._task_done())

	async def _task_done(self):
		if self._count_unack > 0:
			self._count_unack -= 1
		if self._count_unack == 0 and self._count_zero is not None:
			await self._count_zero.set()
	

	def join(self):
		_await(self._join())
	
	async def _join(self):
		if self._count > 0:
			if self._count_zero is None or self._count_zero.is_set():
				self._count_zero = _anyio.create_event()
			await self._count_zero.wait()

