import os as _os
import anyio as _anyio
from aevent import patch_ as _patch, await_ as _await

from socket import socket as _socket, inet_pton, inet_ntop, AF_INET, \
	AF_INET6, AF_UNSPEC, htons, ntohs, htonl, ntohl, inet_aton, inet_ntoa, \
	SOCK_DGRAM, MSG_PEEK, SOL_SOCKET, SO_RCVBUF, SO_SNDBUF, AF_UNIX, \
	IPPROTO_TCP, SOCK_STREAM, AF_PACKET, SOCK_RAW, SO_REUSEADDR, \
	SHUT_RDWR, IPPROTO_ICMP, IPPROTO_ICMPV6, IPPROTO_UDP, AI_PASSIVE, \
	getprotobyname

error = OSError
import errno # as _errno ## used as public API by too many
from functools import partial as _partial

class _Error:
	def __getattribute__(self,key):
		e = EnvironmentError()
		e.errno = getattr(errno, key)
		return e
_Error = _Error()

class socket(_socket):
	def __init__(self,*args,**kwargs):
		super().__init__(*args, **kwargs)
		super().setblocking(False)

	def _wait_write(self):
		if self.fileno() < 0:
			raise _Error.EBADF
		_await(_anyio.wait_socket_writable(self.fileno()))
	def _wait_read(self):
		if self.fileno() < 0:
			raise _Error.EBADF
		_await(_anyio.wait_socket_readable(self.fileno()))

	def connect(self, *args):
		try:
			super().connect(*args)
		except BlockingIOError:
			_await(_anyio.wait_socket_writable(self.fileno()))
			try:
				self.getpeername()
			except EnvironmentError:
				if exc.errno == errno.ENOTCONN:
					raise _Error.ECONNREFUSED
	def accept(self, *args):
		_await(_anyio.wait_socket_readable(self.fileno()))
		sock,addr = super().accept(*args)
		fd = _os.dup(sock.fileno())
		nsock = type(self)(sock.family, sock.type, sock.proto, fileno=fd)
		sock.close()
		nsock.setblocking(False)
		return nsock,addr

	def send(self, *args):
		_await(_anyio.wait_socket_writable(self.fileno()))
		return super().send(*args)
	def sendto(self, *args):
		self._wait_write()
		return super().sendto(*args)
	def sendmsg(self, *args):
		self._wait_write()
		return super().sendmsg(*args)
	def recv(self, *args):
		self._wait_read()
		return super().recv(*args)
	def recvmsg(self, *args):
		self._wait_read()
		return super().recvmsg(*args)
	def recvfrom(self, *args):
		self._wait_read()
		return super().recvfrom(*args)
	def recv_into(self, *args):
		self._wait_read()
		return super().recv_into(*args)
	def recvmsg_into(self, *args):
		self._wait_read()
		return super().recvmsg_into(*args)
	def recvfrom_into(self, *args):
		self._wait_read()
		return super().recvfrom_into(*args)

	def setblocking(self, flag):
		super().setblocking(False)

for n in "getsockname getpeername getsockopt setsockopt close bind fileno listen gettimeout settimeout shutdown".split():
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
