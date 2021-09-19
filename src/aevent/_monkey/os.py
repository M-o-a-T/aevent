import anyio as _anyio
import trio as _trio
from aevent import patch_ as _patch, await_ as _await

from os import supports_dir_fd,supports_fd,supports_follow_symlinks
import os as _os
import sys  # yes, some standard modules actually need that.

_read = read
_write = write

def _BadFD():
	e = EnvironmentError()
	e.errno = _errno.EBADF
	return e

@_patch
def read(fd, *args):
    _await(_anyio.wait_socket_readable(fd))
    return _read(fd, *args)

@_patch
def write(fd, *args):
    _await(_anyio.wait_socket_writable(fd))
    return _write(fd, *args)

for k in dir(_os):
    if k.startswith("supports_"):
        globals()[k] = getattr(_os,k)
