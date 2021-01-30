import sys as _sys
import anyio as _anyio
import aevent as _aevent

from atexit import *

_calls = {}

async def _run():
    for p,a,k in _calls.values():
        try:
            p(*a,**k)
        except Exception as e:
            print(repr(e), file=_sys.stderr)

@register
def _call_run():
    _aevent.run(_run)

@_aevent.patch_
def register(fn,*a,**k):
    _calls[fn] = (fn,a,k)


@_aevent.patch_
def unregister(fn):
    del _calls[fn]
