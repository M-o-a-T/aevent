import anyio as _anyio
import sniffio as _sniffio
from aevent import patch_ as _patch, await_ as _await, \
	taskgroup as _taskgroup, daemons as _daemons
import os as _os
from collections import deque as _deque

from threading import current_thread, Lock, RLock, Event, Thread, \
		_shutdown, excepthook, active_count, get_ident, get_native_id, \
		main_thread, Condition, Barrier
from contextvars import ContextVar


from aevent.local import local

class _Lock_Common:
	async def _acquire(self, timeout, me=None):
		if self._lock is None:
			self._lock = _anyio.create_lock()
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

	async def _release(self):
		if _sniffio.current_async_library() == "trio":
			import trio
			self._lock._lock._owner = trio.lowlevel.current_task()
		await self._lock.release()

	def __enter__(self):
		self.acquire()
	def __exit__(self, *tb):
		self.release()
	async def __aenter__(self):
		if self._lock is None:
			self._lock = _anyio.create_lock()
		return await self._lock.__aenter__()
	async def __aexit__(self, *tb):
		return await self._lock.__aexit__(*tb)


@_patch
class Lock(_Lock_Common):
	_lock = None
	def __init__(self):
		pass

	def acquire(self, blocking=True, timeout=-1):
		if not blocking:
			timeout = 0.001
			# XXX use nowait instead
		return _await(self._acquire(timeout))

	def release(self):
		# threading.Lock has no protection against releasing by the wrong task
		_await(self._release())


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
		_await(self._release())

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
	_tg = None
	_ctx = None
	_daemon = False
	_daemons = None

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
		self._daemon = daemon


	@property
	def native_id(self):
		return _os.getpid()

	@property
	def ident(self):
		return self._th_id

	def is_alive(self):
		return self._done is not None and not self._done.is_set()


	def start(self):
		_await(self._start())

	async def _start(self):
		_active_threads.add(self)
		self._tg = tg = _taskgroup.get()
		self._daemons = _daemons[tg]
		up = _anyio.create_event()
		self._ctx = await tg.spawn(self._run, up, _aevent_name=self.name)
		if self._daemon:
			self._daemons.add(self._ctx)
		await up.set()

	@property
	def daemon(self):
		return self._daemon
	@daemon.setter
	def daemon(self, flag):
		if self._daemon == flag:
			return
		self._daemon = flag
		if self._daemons is None:
			return
		if flag:
			self._daemons.add(self._ctx)
		else:
			self._daemons.remove(self._ctx)

	async def _run(self, evt):
		await evt.wait()
		self.run(evt)

	def run(self, evt):
		try:
			if self._target:
				self._target(*self._args, **self._kwargs)
		except Exception as exc:
			excepthook(_ThreadExc(exc,self))
		finally:
			_await(self._done.set())
			_active_threads.remove(self)
			if self._daemon:
				self._daemons.remove(self._ctx)

			del self._daemons

	def join(self, timeout=-1):
		_await(self._join(timeout))

	async def _join(self,timeout):
		if current_thread() is self:
			raise RuntimeError("tried to join myself")
		if self._ctx is None:
			raise RuntimeError("not yet started")
		if timeout<0:
			await self._done.wait()
		else:
			async with _anyio.fail_after(timeout):
				await self._done.wait()

	def setDaemon(self, flag):
		self.daemon = flag

	def isDaemon(self):
		return self.daemon

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
	return _os.getpid()

@_patch
def main_thread():
	return _root_thread


# This is almost a straight copy from `threading`.

@_patch
class Condition:
	def __init__(self, lock=None):
		if lock is None:
			lock = RLock()
		self._lock = lock
		# Export the lock's acquire() and release() methods
		self.acquire = lock.acquire
		self.release = lock.release
		self._waiters = _deque()

	def __enter__(self):
		return self._lock.__enter__()

	def __exit__(self, *args):
		return self._lock.__exit__(*args)

	def __aenter__(self):
		return self._lock.__aenter__()

	def __aexit__(self, *args):
		return self._lock.__aexit__(*args)

	def __repr__(self):
		return "<Condition(%s, %d)>" % (self._lock, len(self._waiters))

	def _is_owned(self):
		# Return True if lock is owned by current_thread.
		# This method is called only if _lock doesn't have _is_owned().
		if self._lock.acquire(False):
			self._lock.release()
			return False
		else:
			return True

	async def _wait(self, timeout):
		if not self._is_owned():
			raise RuntimeError("cannot wait on un-acquired lock")
		waiter = _anyio.create_event()
		self._waiters.append(waiter)
		gotit = False
		try:	# restore state no matter what (e.g., KeyboardInterrupt)
			if timeout is None:
				await waiter.wait()
				gotit = True
			else:
				async with _anyio.move_on_after(timeout):
					await waiter.wait()
					gotit = True
			return gotit
		finally:
			if not gotit:
				try:
					self._waiters.remove(waiter)
				except ValueError:
					pass

	def wait(self, timeout=None):
		_await(self._wait(timeout))

	def wait_for(self, predicate, timeout=None):
		"""Wait until a condition evaluates to True.

		predicate should be a callable which result will be interpreted as a
		boolean value.  A timeout may be provided giving the maximum time to
		wait.

		"""
		endtime = None
		waittime = timeout
		result = predicate()
		while not result:
			if waittime is not None:
				if endtime is None:
					endtime = _time() + waittime
				else:
					waittime = endtime - _time()
					if waittime <= 0:
						break
			self.wait(waittime)
			result = predicate()
		return result

	async def _notify(self, n):
		"""Wake up one or more threads waiting on this condition, if any.

		If the calling thread has not acquired the lock when this method is
		called, a RuntimeError is raised.

		This method wakes up at most n of the threads waiting for the condition
		variable; it is a no-op if no threads are waiting.

		"""
		if not self._is_owned():
			raise RuntimeError("cannot notify on un-acquired lock")
		all_waiters = self._waiters
		waiters_to_notify = _deque(_islice(all_waiters, n))
		if not waiters_to_notify:
			return
		for waiter in waiters_to_notify:
			await waiter.set()
			try:
				all_waiters.remove(waiter)
			except ValueError:
				pass

	def notify(self, n=1):
		_await(self._notify(n))

	def notify_all(self):
		"""Wake up all threads waiting on this condition.

		If the calling thread has not acquired the lock when this method
		is called, a RuntimeError is raised.

		"""
		self.notify(len(self._waiters))

	notifyAll = notify_all


# This is a straight copy from `threading`.

@_patch
class Barrier:
	def __init__(self, parties, action=None, timeout=None):
		"""Create a barrier, initialised to 'parties' threads.

		'action' is a callable which, when supplied, will be called by one of
		the threads after they have all entered the barrier and just prior to
		releasing them all. If a 'timeout' is provided, it is used as the
		default for all subsequent 'wait()' calls.

		"""
		self._cond = Condition(Lock())
		self._action = action
		self._timeout = timeout
		self._parties = parties
		self._state = 0 #0 filling, 1, draining, -1 resetting, -2 broken
		self._count = 0

	def wait(self, timeout=None):
		"""Wait for the barrier.

		When the specified number of threads have started waiting, they are all
		simultaneously awoken. If an 'action' was provided for the barrier, one
		of the threads will have executed that callback prior to returning.
		Returns an individual index number from 0 to 'parties-1'.

		"""
		if timeout is None:
			timeout = self._timeout
		with self._cond:
			self._enter() # Block while the barrier drains.
			index = self._count
			self._count += 1
			try:
				if index + 1 == self._parties:
					# We release the barrier
					self._release()
				else:
					# We wait until someone releases us
					self._wait(timeout)
				return index
			finally:
				self._count -= 1
				# Wake up any threads waiting for barrier to drain.
				self._exit()

	# Block until the barrier is ready for us, or raise an exception
	# if it is broken.
	def _enter(self):
		while self._state in (-1, 1):
			# It is draining or resetting, wait until done
			self._cond.wait()
		#see if the barrier is in a broken state
		if self._state < 0:
			raise BrokenBarrierError
		assert self._state == 0

	# Optionally run the 'action' and release the threads waiting
	# in the barrier.
	def _release(self):
		try:
			if self._action:
				self._action()
			# enter draining state
			self._state = 1
			self._cond.notify_all()
		except:
			#an exception during the _action handler.  Break and reraise
			self._break()
			raise

	# Wait in the barrier until we are released.  Raise an exception
	# if the barrier is reset or broken.
	def _wait(self, timeout):
		if not self._cond.wait_for(lambda : self._state != 0, timeout):
			#timed out.  Break the barrier
			self._break()
			raise BrokenBarrierError
		if self._state < 0:
			raise BrokenBarrierError
		assert self._state == 1

	# If we are the last thread to exit the barrier, signal any threads
	# waiting for the barrier to drain.
	def _exit(self):
		if self._count == 0:
			if self._state in (-1, 1):
				#resetting or draining
				self._state = 0
				self._cond.notify_all()

	def reset(self):
		"""Reset the barrier to the initial state.

		Any threads currently waiting will get the BrokenBarrier exception
		raised.

		"""
		with self._cond:
			if self._count > 0:
				if self._state == 0:
					#reset the barrier, waking up threads
					self._state = -1
				elif self._state == -2:
					#was broken, set it to reset state
					#which clears when the last thread exits
					self._state = -1
			else:
				self._state = 0
			self._cond.notify_all()

	def abort(self):
		"""Place the barrier into a 'broken' state.

		Useful in case of error.  Any currently waiting threads and threads
		attempting to 'wait()' will have BrokenBarrierError raised.

		"""
		with self._cond:
			self._break()

	def _break(self):
		# An internal error was detected.  The barrier is set to
		# a broken state all parties awakened.
		self._state = -2
		self._cond.notify_all()

	@property
	def parties(self):
		"""Return the number of threads required to trip the barrier."""
		return self._parties

	@property
	def n_waiting(self):
		"""Return the number of threads currently waiting at the barrier."""
		# We don't need synchronization here since this is an ephemeral result
		# anyway.  It returns the correct value in the steady state.
		if self._state == 0:
			return self._count
		return 0

	@property
	def broken(self):
		"""Return True if the barrier is in a broken state."""
		return self._state == -2

# exception raised by the Barrier class
class BrokenBarrierError(RuntimeError):
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
			try:
				async with _anyio.fail_after(timeout):
					await self._evt.wait()
			except TimeoutError:
				return False
		return True

	def wait(self, timeout=None):
		return _await(self._wait(timeout))

	def set(self):
		_await(self._evt.set())

	def clear(self):
		self._event = _anyio.create_event()
	
	def is_set(self):
		return self._evt.is_set()

# _shutdown is not patched
