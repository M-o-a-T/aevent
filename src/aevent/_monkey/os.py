import anyio as _anyio
import trio as _trio
from aevent import patch_ as _patch, await_ as _await

from os import *
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

