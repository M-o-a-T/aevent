import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await

from threading import current_thread, Lock, RLock, Event, Thread, \
	_shutdown

from aevent.local import local

@_patch
def current_thread():
	return 0

class _Lock_Common:
	async def _acquire(self, timeout, me=None):
		if timeout < 0:
			await self._lock.acquire()
		else:
			try:
				async with _anyio.fail_after(timeout):
					await self._lock.acquire()
			except TimeoutError:
				return False
		if me is not None:
			self._owner = me
		return True

	def __enter__(self):
		self.acquire()
	def __exit__(self, *tb):
		self.release()


@_patch
class Lock(_Lock_Common):
	_lock = None
	def __init__(self):
		pass

	def acquire(self, blocking=True, timeout=-1):
		if self._lock is None:
			self._lock = _anyio.create_lock()
		if not blocking:
			timeout = 0.001
			# XXX use nowait instead
		return _await(self._acquire(timeout))

	def release(self):
		_await(self._lock.release())

@_patch
class RLock(_Lock_Common):
	_lock = None
	_count = 0
	_owner = None

	def __init__(self):
		pass

	def acquire(self, blocking=True, timeout=-1):
		if self._lock is None:
			self._lock = _anyio.create_lock()
		me = current_thread()
		if self._owner == me:
			self._count += 1
			return
		if not blocking:
			timeout = 0.001
			# XXX use nowait instead
		_await(self._acquire(timeout, me))

	def release(self):
		me = current_thread()
		if self._owner != me:
			raise RuntimeError("Lock crash %r %r",self._owner,me)
		if self._count:
			self._count -= 1
			return
		self._owner = None
		_await(self._lock.release())

	def __enter__(self):
		self.acquire()
	def __exit__(self, *tb):
		self.release()

@_patch
class Thread:
	pass

@_patch
class Event:
	_event = None

	@property
	def _evt(self):
		if self._event is None:
			self._event = _anyio.create_event()
		return self._event

	async def _wait(self, timeout):
		if timeout is None:
			await self._evt.wait()
		else:
			async with _anyio.fail_after(timeout):
				await self._evt.wait()

	def wait(self, timeout=None):
		_await(self._wait(timeout))

	def set(self):
		_await(self._evt.set())

	def clear(self):
		self._event = _anyio.create_event()
	
	def is_set(self):
		return self._evt.is_set()

# _shutdown is not patched
