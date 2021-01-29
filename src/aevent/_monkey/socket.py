import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await

from socket import socket as _socket, inet_pton, inet_ntop, AF_INET, \
	AF_INET6, AF_UNSPEC, htons, ntohs, htonl, ntohl, inet_aton, inet_ntoa, \
	SOCK_DGRAM, MSG_PEEK, SOL_SOCKET, SO_RCVBUF, SO_SNDBUF, AF_UNIX, \
	IPPROTO_TCP, SOCK_STREAM, AF_PACKET, SOCK_RAW

error = OSError
import errno
from functools import partial as _partial

class socket(_socket):
	def close(self):
		super().close()

	def send(self, *args):
		_await(_anyio.wait_socket_writable(self.fileno()))
		return super().send(*args)
	def sendto(self, *args):
		_await(_anyio.wait_socket_writable(self.fileno()))
		return super().sendto(*args)
	def sendmsg(self, *args):
		_await(_anyio.wait_socket_writable(self.fileno()))
		return super().sendmsg(*args)
	def recv(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recv(*args)
	def recvmsg(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recvmsg(*args)
	def recvfrom(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recvfrom(*args)
	def recv_into(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recv_into(*args)
	def recvmsg_into(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recvmsg_into(*args)
	def recvfrom_into(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		return super().recvfrom_into(*args)

for n in "getsockname getpeername getsockopt setsockopt close bind fileno".split():
	setattr(socket,n,getattr(_socket,n))

def _is_dead(n):
	async def _dead(self,*a,**kw):
		raise NotImplementedError(n)
	return _dead

for n in dir(_socket):
	if n[0] == '_':
		continue
	fn = getattr(socket,n)
	if not callable(fn):
		continue
	setattr(socket, n, _patch(socket.__dict__.get(n,_is_dead(n)), name=n, orig=fn))

del n
