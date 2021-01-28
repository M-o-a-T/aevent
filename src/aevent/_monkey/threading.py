import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await, \
	taskgroup as _taskgroup
import os

from threading import current_thread, Lock, RLock, Event, Thread, \
		_shutdown, excepthook, active_count, get_ident, get_native_id, \
		main_thread
from contextvars import ContextVar


from aevent.local import local

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

class _ThreadExc:
	def __init__(self,exc,thread):
		self.exc_type = type(exc)
		self.exc_value = exc
		self.exc_traceback = getattr(exc,'__traceback__',None)
		self.thread = thread

class _Thread:
	_th_id = None

	def __init__(self, group=None, target=None, name=None, 
			args=(), kwargs={}, *, daemon=None):

		global _th_id
		_th_id += 1
		self._th_id = _th_id

		self._target = target
		self._args = args
		self._kwargs = kwargs
		self._done = _anyio.create_event()
		self.name = name or "task_%d" % (self._th_id,)

		if daemon is None:
			daemon = current_thread().daemon
		self.daemon = daemon


	@property
	def native_id(self):
		return os.getpid()

	@property
	def ident(self):
		return self._th_id

	def is_alive(self):
		return self._done is not None and not self._done.is_set()


	def start(self):
		_await(self._start())

	async def _start(self):
		_active_threads.add(self)
		up = _anyio.create_event()
		self._ctx = await _taskgroup.get().spawn(self._run, up, _aevent_name=self.name)
		_await(up.wait())

	async def _run(self, evt):
		await evt.set()
		self.run()

	def run(self):
		try:
			if self._target:
				self._target(*self._args, **self._kwargs)
		except Exception as exc:
			excepthook(_ThreadExc(exc,self))
		finally:
			_await(self._done.set())
			_active_threads.remove(self)

	def join(self, timeout=-1):
		_await(self._join(timeout))

	async def _join(self,timeout):
		if timeout<0:
			await self._done.wait()
		else:
			async with _anyio.fail_after(timeout):
				await self._done.wait()


	def __hash__(self):
		return self._th_id
	def __cmp__(self,other):
		if isinstance(other,Thread):
			other = other._th_id
		return self._th_id - other

@_patch
def excepthook(k):
	raise k.exc_value

class RootThread(_Thread):
	_th_id = 1
	daemon = False
	def __init__(self):
		pass # do not call super()
	pass

Thread = _patch(_Thread)

_root_thread = RootThread()
_th_id = 1
_this_thread = ContextVar("_this_thread", default=RootThread())
_active_threads = set()

@_patch
def current_thread():
	return _this_thread.get()

@_patch
def get_ident():
	return _this_thread.get()._th_id

@_patch
def get_native_id():
	return os.getpid()

@_patch
def main_thread():
	return _root_thread


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
