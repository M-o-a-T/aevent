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
from inspect import currentframe

_monkey = None
no_patch = ContextVar('no_patch', default=False)

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

    import_mod('time')
    if 'spawn' not in exclude:
        _real_spawn = TG.spawn
        async def spawn(taskgroup, proc, *args, **kw):
            """
            Run a task within this task group.

            Returns a cancel scope you can use to stop the task.
            """

            if no_patch.get():
                return await _real_spawn(taskgroup, proc, *args, **kw)

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

            evt = anyio.create_event()
            await _real_spawn(taskgroup, _run, proc, args, kw, evt)
            await evt.wait()
            return scope
        TG.spawn = spawn

    sys.path[0:0] = [os.path.join(_monkey.__path__[0],"_monkey")]

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

def _patch(fn):
    fname = fn.__name__
    f = currentframe().f_back
    _orig = f.f_globals[fname]

    def _new(_orig, *a, **k):
        if no_patch.get():
            return _orig(*a, **k)
        return greenback.await_(fn(*a, **k))
    return update_wrapper(partial(_new,_orig), fn)

