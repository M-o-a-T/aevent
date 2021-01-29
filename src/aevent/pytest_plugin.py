# This code is an extended copy of anyio.pytest_plugin

import sys
from contextlib import contextmanager
from inspect import iscoroutinefunction, isasyncgenfunction, isgeneratorfunction
from typing import Any, Dict, Iterator, Optional, Tuple, cast

import pytest
import sniffio

from anyio._core._eventloop import get_all_backends, get_asynclib
from anyio.abc import TestRunner
from anyio.pytest_plugin import extract_backend_and_options

from . import runner as aevent_runner

import _pytest.nose as _nose

_current_runner: Optional[TestRunner] = None


@contextmanager
def get_runner(backend_name: str, backend_options: Dict[str, Any]) -> Iterator[TestRunner]:
    global _current_runner
    if _current_runner:
        yield _current_runner
        return

    asynclib = get_asynclib(backend_name)
    token = None
    if sniffio.current_async_library_cvar.get(None) is None:
        # Since we're in control of the event loop, we can cache the name of the async library
        token = sniffio.current_async_library_cvar.set(backend_name)

    try:
        backend_options = backend_options or {}
        with asynclib.TestRunner(**backend_options) as runner:
            _current_runner = runner
            yield runner
    finally:
        _current_runner = None
        if token:
            sniffio.current_async_library_cvar.reset(token)


def pytest_configure(config):
    config.addinivalue_line('markers', 'aevent: mark the test to be run via anyio.')


def pytest_fixture_setup(fixturedef, request):
    def wrapper(*args, **kwargs):
        backend_name, backend_options = extract_backend_and_options("trio")

        with get_runner(backend_name, backend_options) as runner:
            if isasyncgenfunction(func):
                gen = func(*args, **kwargs)
                try:
                    value = runner.call(gen.asend, None)
                except StopAsyncIteration:
                    raise RuntimeError('Async generator did not yield')

                yield value

                try:
                    runner.call(gen.asend, None)
                except StopAsyncIteration:
                    pass
                else:
                    runner.call(gen.aclose)
                    raise RuntimeError('Async generator fixture did not stop')

            elif isgeneratorfunction(func):
                gen = func(*args, **kwargs)
                try:
                    value = runner.call_sync(gen.send, None)
                except StopAsyncIteration:
                    raise RuntimeError('Async generator did not yield')

                yield value

                try:
                    runner.call_sync(gen.send, None)
                except StopIteration:
                    pass
                else:
                    runner.call_sync(gen.close)
                    raise RuntimeError('Generator fixture did not stop')

            elif iscoroutinefunction(func):
                yield runner.call(func, *args, **kwargs)
            else:
                yield runner.call_sync(func, *args, **kwargs)

    # Only apply this to coroutine functions and async generator functions in requests that involve
    # the aevent_backend fixture
    if fixturedef.argname == "anyio_backend":
        return
    func = fixturedef.func
    fixturedef.func = wrapper


def pytest_pycollect_makeitem(collector, name, obj):
    if collector.istestfunction(obj, name):
        inner_func = obj.hypothesis.inner_test if hasattr(obj, 'hypothesis') else obj
        if True: # iscoroutinefunction(inner_func):
            marker = collector.get_closest_marker('aevent')
            own_markers = getattr(obj, 'pytestmark', ())
            if marker or any(marker.name == 'aevent' for marker in own_markers):
                pytest.mark.usefixtures('aevent_options')(obj)


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    def run_with_hypothesis(**kwargs):
        with get_runner(backend_name, backend_options) as runner:
            if iscoroutinefunction(original_func):
                runner.call(original_func, **kwargs)
            else:
                runner.call_sync(original_func, **kwargs)

    if pyfuncitem.funcargs.get('aevent_options') or \
            any(marker.name == 'aevent' for marker in pyfuncitem.own_markers):
        backend_name, backend_options = extract_backend_and_options("trio")

        if hasattr(pyfuncitem.obj, 'hypothesis'):
            # Wrap the inner test function unless it's already wrapped
            original_func = pyfuncitem.obj.hypothesis.inner_test
            if original_func.__qualname__ != run_with_hypothesis.__qualname__:
                if True: # iscoroutinefunction(original_func):
                    pyfuncitem.obj.hypothesis.inner_test = run_with_hypothesis
            return None

        funcargs = pyfuncitem.funcargs
        testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        with get_runner(backend_name, backend_options) as runner:
            async def _main():
                teardown = False
                async with aevent_runner():
                    try:
                        self = pyfuncitem.obj.__self__
                    except AttributeError:
                        pass
                    else:
                        _nose.call_optional(self, "setup")
                        try:
                            teardown = self.teardown
                        except AttributeError:
                            pass
                    try:
                        if iscoroutinefunction(pyfuncitem.obj):
                            await pyfuncitem.obj(**testargs)
                        else:
                            pyfuncitem.obj(**testargs)
                    finally:
                        if teardown:
                            teardown()
            runner.call(_main)
        return True


@pytest.fixture
def aevent_options(request):
    """
    None defined yet, fixture is used as marker.
    """
    return True


# We call setup and teardown from _pyfunc_call.
def no_nose(fn):
    return False
_nose.is_potential_nosetest = no_nose



