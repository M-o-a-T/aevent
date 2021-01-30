#
# aevent replaces various system modules with a version that uses anyio and
# greenback behind your back.

import anyio
import greenback
import sys
import os

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from functools import partial, update_wrapper
from inspect import currentframe, iscoroutinefunction
from outcome import Error, Value

_monkey = None
no_patch = ContextVar('no_patch', default=False)
in_wrapper = ContextVar('in_wrapper', default=False)
taskgroup = ContextVar('taskgroup')
daemons = dict()  # taskgroup > set

await_ = greenback.await_

@contextmanager
def native(val=True):
    """
    A context manager that temporarily switches off all patches imposed by
    `aevent.setup`.
    """
    t = no_patch.set(True)
    try:
        yield None
    finally:
        no_patch.reset(t)

def patched():
    """
    A context manager that undoes the effect of `aevent.native`.
    """
    return native(val=False)

@asynccontextmanager
async def runner():
    async with anyio.create_task_group() as tg:
        await per_task()
        daemons[tg] = to_kill = set()
        token = taskgroup.set(tg)
        try:
            yield tg
        finally:
            taskgroup.reset(token)
            del daemons[tg]
            for d in list(to_kill):
                await d.cancel()

def run(proc, *args, **kwargs):
    """
    A replacement for anyio.run().

    You need to use this, or an async `runner` context, if you want to use
    threading.
    """
    async def _run():
        async with runner():
            return await proc(*args, **kwargs)
    return anyio.run(_run)

_setup_done = False
def setup(backend='trio', exclude=()):
    """
    Set up the aevent imports and patches.

    This function changes core Python modules.
    It *must* be called before you import *anything else*.

    :param backend: The back-end to use, may be 'trio' or 'asyncio'.
    :param exclude: a set of modules that should not be patched.

    Supported modules:
    * time

    Pseudo modules:
    * spawn: controls the behavior of `anyio.spawn`.
    """

    global _setup_done
    if not _setup_done:
        _setup_done = backend
    elif _setup_done == backend:
        return
    else:
        raise RuntimeError("You're trying to mix backends")

    global _monkey
    global _backend
    global trio, asyncio

    if backend == 'trio':
        import trio
        from anyio._backends._trio import TaskGroup as TG
    elif backend == 'asyncio':
        import asyncio
        from anyio._backends._asyncio import TaskGroup as TG
    else:
        raise RuntimeError("backend must be 'trio' or 'asyncio', not %r" % (backend),)
    _backend = backend

    from . import _monkey

    def import_mod(m):
        if m in exclude:
            mm = __import__(m, level=0) 
            setattr(_monkey, m, mm)
        else:
            mm = __import__('aevent._monkey.'+m)
            mm = getattr(mm._monkey, m)
        sys.modules[m] = mm

    import_mod('os')
    import_mod('time')
    import_mod('socket')
    import_mod('queue')
    import_mod('atexit')
    import_mod('select')
    import_mod('threading')
    if 'spawn' not in exclude:
        _real_spawn = TG.spawn
        async def spawn(taskgroup, proc, *args, _aevent_name=None, **kw):
            """
            Run a task within this task group.

            Returns a cancel scope you can use to stop the task.
            """

            if no_patch.get():
                if kw:
                    proc=partial(proc,*args,**kw)
                    args=()
                    kw={}
                return await _real_spawn(taskgroup, proc, *args, name=_aevent_name)

            scope = None

            async def _run(proc, args, kw, evt):
                """
                Helper for starting a task within a cancel scope.
                """
                nonlocal scope
                async with anyio.open_cancel_scope() as sc:
                    scope = sc
                    await evt.set()
                    await per_task()
                    await proc(*args, **kw)
                    pass  # end of scope

            evt = anyio.create_event()
            await _real_spawn(taskgroup, _run, proc, args, kw, evt, name=_aevent_name)
            await evt.wait()
            return scope
        TG.spawn = spawn

    if backend == 'trio':
        from anyio._backends._trio import TestRunner as TR
        if not hasattr(TR,"call_sync"):
            TR_init = TR.__init__
            TR_trio_main = TR._trio_main
            TR_call = TR.call
            TR_call_func = TR._call_func
            TR_close = TR.close
            def _init(*a,**k):
                with native():
                    TR_init(*a,**k)
            async def _trio_main(self):
                #in_wrapper.set(True)
                await TR_trio_main(self)

            async def call_func(self, func, args, kwargs):
                if not in_wrapper.get():
                    in_wrapper.set(True)
                    await per_task()
                await TR_call_func(self, func, args, kwargs)


            def call_sync(self, func, *args, **kwargs):
                async def _func(func, *args, **kwargs):
                    try:
                        return func(*args, **kwargs)
                    except StopIteration:
                        raise StopAsyncIteration
                if in_wrapper.get():
                    return func(*args, **kwargs)
                try:
                    return TR_call(self, _func, func, *args, **kwargs)
                except StopAsyncIteration:
                    raise StopIteration
                except Exception as exc:
                    # attach debugger here:
                    raise

            def call(self, func, *args, **kwargs):
                if self._stop_event is not None and self._stop_event.is_set():
                    # Owch.
                    T = TR()
                    try:
                        return T.call(func, *args, **kwargs)
                    finally:
                        T.close()
                assert not in_wrapper.get()
                try:
                    return TR_call(self, func, *args, **kwargs)
                except StopAsyncIteration:
                    raise StopIteration

            def close(self):
                TR_close(self)

            TR.__init__ = _init # update_wrapper(_init, TR_init)
            TR._trio_main = _trio_main # update_wrapper(_main, TR_trio_main)
            TR.call = call # update_wrapper(call, TR_call)
            TR.call_sync = call_sync
            TR._call_func = call_func
            TR.close = close


    sys.path[0:0] = [os.path.join(_monkey.__path__[0],"_monkey")]

def F():
    sys.stdout.flush()

async def per_task():
    """
    Call this once per task.

    This is done for you if you use our patched version of ``anyio.TaskGroup.spawn``.
    """
    await greenback.ensure_portal()

async def _runner(proc, a, k):
    await per_task()
    return await proc(*a, **k)

def run(proc, *a, **k):
    if _backend == 'trio':
        return trio.run(_runner, proc, a, k)
    elif _backend == 'asyncio':
        return asyncio.run(_runner(proc, a, k))

def patch_(fn, name=None, orig=None):
    """
    Convince an async-or-sync function to replace a sync one.

    If `fn` is a class, subclassing it no longer works.

    The patched result has three attributes
    * _aevent_orig: the original function or class
      used when `no_patch` is False
    * _aevent_new: the replaced function or class
      used when `no_patch` is True
    * _aevent_select: a no-args function which, when called,
      returns the old or new version based on `no_patch`
    """

    if isinstance(fn,partial):
        fname = fn.func.__name__
    else:
        fname = fn.__name__
    orig = orig or currentframe().f_back.f_globals[fname]

    def fn_select(orig, fn):
        return orig if no_patch.get() else fn

    def fn_async(orig, fn):
        def _new_async(*a, **k):
            if no_patch.get():
                return orig(*a, **k)
            return greenback.await_(fn(*a, **k))
        return _new_async

    def fn_sync(orig, fn):
        def _new_sync(*a, **k):
            if no_patch.get():
                return orig(*a, **k)
            return fn(*a, **k)
        return _new_sync

    if iscoroutinefunction(fn):
        w = update_wrapper(fn_async(orig,fn), fn)
    else:
        w = update_wrapper(fn_sync(orig,fn), fn)

    w._aevent_orig = orig
    w._aevent_new = orig
    w._aevent_select = lambda: fn_select(orig, fn)
    return w

