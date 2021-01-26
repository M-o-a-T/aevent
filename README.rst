====================================
``aevent``: an asyncronizing library
====================================

``aevent`` allows you to call boring synchronous Python from async code,
without blocking.

``aevent`` is to ``gevent`` what ``anyio`` is to ``greenlet``.

That is, it replaces standard Python functions with calls to ``anyio``
instead of ``gevent``.

Some limitations apply.

Usage
=====

**Before any other imports**, insert this code block into your main code::

   import aevent
   aevent.setup('trio')  # or asyncio, if you must
   
This will annoy various code checkers, but that can't be helped.

**Start your main loop** using `aevent.run`, or call ``await aevent.per_task()``
in the task(s) that need to use patched code.


Supporting code
---------------

``aevent`` monkey-patches `anyio.abc.TaskGroup.spawn` in two ways.

* the child task is instrumented to support `greenback`.

* ``spawn`` returns a cancel scope. You can use it to cancel the new task.

Call `aevent.per_task` in your child task if you start tasks some other way.


Supported modules
=================

* time

  * sleep

Not yet supported
-----------------

* threading
* queue
* socket

* dns
* select
* os

  * read

  * write

* ssl
* subprocess
* signal

This list is cribbed from ``gevent.patch``.

Internals
=========

``aevent`` works by prepending its local ``_monkey`` directory to the import path.
These try hard to afford the same public interface, but call the
corresponding ``anyio`` functions in the background.

Context switching back to async-flavored code is done by way of greenback_.

``aevent`` runs on Python 3.7 ff.

Testing
-------

The test suite runs with Trio as backend. Due to ``aevent``'s monkeypatching,
switching backends around is not supported. However, you can set the
environment variable ``AEVENT_BACKEND`` to ``asyncio`` to run the test
suite with that.
