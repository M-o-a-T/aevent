====================================
``aevent``: an asyncronizing library
====================================

``aevent`` lets you call boring synchronous Python from async code.
Without blocking or splatting ``async`` and ``await`` onto it.
Ideally, this works without modifying the synchronous code.

Put another way,
``aevent`` is to ``gevent`` what ``anyio`` is to ``greenlet``.

That is, it replaces standard Python functions with calls to `anyio`_
instead of ``gevent``.

Some limitations apply.

Usage
=====

**Before any other imports**, insert this code block into your main code::

   import aevent
   aevent.setup('trio')  # or asyncio, if you must
   
This will annoy various code checkers, but that can't be helped.

**Start your main loop** using ``aevent.run``, or call ``await aevent.per_task()``
in the task(s) that need to use patched code.

The ``aevent.native`` and ``aevent.patched`` context managers can be used to
temporarily disable or re-enable ``aevent``'s patches.


Support functions
-----------------

``aevent`` monkey-patches ``anyio``'s ``TaskGroup.spawn`` in two ways.

* the child task is instrumented to support `greenback`.

* ``spawn`` returns a cancel scope. You can use it to cancel the new task.

Call ``aevent.per_task`` in your child task if you start tasks some other way.


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

``aevent``'s monkey patching is done mainly on the module/class level.
``gevent`` prefers to patch individual methods. This may cause some
reduced compatibility compared to ``gevent``.

``aevent`` works by prepending its local ``_monkey`` directory to the import path.
These modules try to afford the same public interface as the ones they're
replacing while calling the corresponding ``anyio`` functions through
`greenback_`.

Context switching back to async-flavored code is done by way of `greenback`_.

``aevent`` runs on Python 3.7 ff.

Testing
-------

The test suite runs with `Trio <trio>`_ as backend. Due to ``aevent``'s monkeypatching,
switching backends around is not supported. However, you can set the
environment variable ``AEVENT_BACKEND`` to `asyncio`_ to run the test
suite with that.

.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _trio: https://github.com/python-trio/trio
.. _anyio: https://github.com/agronholm/anyio
.. _greenback: https://github.com/oremanj/greenback
