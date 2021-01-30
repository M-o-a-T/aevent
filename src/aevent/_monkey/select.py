import anyio as _anyio
import errno as _errno
from aevent import patch_ as _patch, await_ as _await

from select import poll,select,epoll, POLLIN,POLLOUT, POLLHUP,POLLERR,POLLRDHUP,POLLNVAL,POLLPRI

@_patch
def epoll(*a,**kw):
    raise NotImplementedError()

@_patch
def select(*a,**kw):
    raise NotImplementedError()

@_patch
class poll:
    def __init__(self):
        self._mask = dict()

    def register(self, fd, mask=POLLIN|POLLOUT):
        if hasattr(fd,"fileno"):
            fd = fd.fileno()
        self._mask[fd] = mask

    def modify(self, fd, mask):
        if hasattr(fd,"fileno"):
            fd = fd.fileno()
        if fd not in self._mask:
            raise FileNotFoundError(str(fd))
        self._mask[fd] = mask

    def unregister(self, fd):
        if hasattr(fd,"fileno"):
            fd = fd.fileno()
        del self._mask[fd]

    def poll(self, timeout=None):
        return _await(self._poll(timeout))

    async def _poll(self, timeout):
        # This is annoyingly inefficient.

        result = []

        async def fd_read(fd):
            try:
                await _anyio.wait_socket_readable(fd)
            except EnvironmentError as e:
                if e.errno == _errno.EBADF:
                    result.append((fd,POLLNVAL))
                else:
                    raise
            else:
                result.append((fd,POLLIN|POLLHUP|POLLERR))
            await ctx.cancel()

        async def fd_write(fd):
            try:
                await _anyio.wait_socket_writable(fd)
            except EnvironmentError as e:
                if e.errno == _errno.EBADF:
                    result.append((fd,POLLNVAL))
                else:
                    raise
            else:
                result.append((fd,POLLOUT))
            await ctx.cancel()

        async with _anyio.create_task_group() as tg:
            ctx = tg.cancel_scope
            for fd,mask in self._mask.items():
                if fd == -1:
                    result.append((fd,POLLNVAL))
                    timeout=0.01
                else:
                    if mask&POLLIN:
                        await tg.spawn(fd_read, fd)
                    if mask&POLLOUT:
                        await tg.spawn(fd_write, fd)
            if timeout:
                await anyio.sleep(timeout)
                await ctx.cancel()
        return result

