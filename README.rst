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


Threading
---------

Threads are translated to tasks. In order for that to work, you must start
your program with `aevent.run`, or run the sync code in question within an
`aevent.runner` async context manager. Runners may be nested.


Supported modules
=================

* time

  * sleep

* threading
* queue
* atexit
* socket
* select

  * poll

Not yet supported
-----------------

* select

  * anything else

* dns
* os

  * read

  * write

* ssl
* subprocess
* signal


Subclassing patched classes
---------------------------

Directly subclassing one of the classes patched by ``aevent`` does not
work and requires special consideration. Consider this code::

   class my_thread(threading.Thread):
      def run(self):
          ...

For use with ``aevent`` you can choose the original ``Thread``
implementation::

    orig_Thread = getattr(threading.Thread, "_aevent_orig", threading.Thread)
    class my_thread(orig_Thread):
      ...

or the ``aevent``-ified version::

    new_Thread = threading.Thread._aevent_new # fails when aevent is not loaded
    class my_thread(new_Thread):
      ...

or you might want to create two separate implementations, and switch based
on the aevent context::

    class _orig_my_thread(threading.Thread._aevent_orig):
       ...
    class _new_my_thread(threading.Thread._aevent_new):
       ...
    my_thread = aevent.patch__new_my_thread, name="my_thread", orig=_orig_my_thread)

If you generate local subclasses on the fly, you can simplify this to::

    def some_code():
        class my_thread(threading.Thread._aevent_select()):
            def run(self):
                ...
        job = my_tread()
        my_thread.start()


Other affected modules
----------------------

You need to import any module which requires non-patched code before
importing ``aevent``.

Modules which are known to be affected:

* multiprocessing


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

The test suite runs with `trio`_ as backend. Due to ``aevent``'s monkeypatching,
switching backends around is not supported. However, you can set the
environment variable ``AEVENT_BACKEND`` to `asyncio`_ to run the test
suite with that.

.. _asyncio: https://docs.python.org/3/library/asyncio.html
.. _trio: https://github.com/python-trio/trio
.. _anyio: https://github.com/agronholm/anyio
.. _greenback: https://github.com/oremanj/greenback
