import contextlib
import asyncio
import logging
import time
import sys

log = logging.getLogger("network_changer.async_helpers")


def create_future(*, name=None, loop=None):
    future = (loop or asyncio.get_event_loop()).create_future()
    future.name = name
    future.add_done_callback(silent_reporter)
    return future


def async_as_background(coroutine, silent=False):
    """
    Create a task with :func:`reporter` as a done callback and return the created
    task. If ``silent=True`` then use :func:`silent_reporter`.

    This is useful because if a task exits with an exception, but nothing ever
    retrieves that exception then Python will print annoying warnings about this.

    .. code-block:: python

        from photons_app import helpers as hp


        async def my_func():
            await something()

        # Kick off the function in the background
        hp.async_as_background(my_func())
    """
    t = asyncio.get_event_loop().create_task(coroutine)
    if silent:
        t.add_done_callback(silent_reporter)
    else:
        t.add_done_callback(reporter)
    return t


async def wait_for_all_futures(*futs, name=None):
    """
    Wait for all the futures to be complete and return without error regardless
    of whether the futures completed successfully or not.

    If there are no futures, nothing is done and we return without error.

    We determine all the futures are done when the number of completed futures
    is equal to the number of futures we started with. This is to ensure if a
    future is special and calling done() after the future callback has been
    called is not relevant anymore, we still count the future as done.
    """
    if not futs:
        return

    waiter = create_future(name=f"||wait_for_all_futures({name})[waiter]")

    unique = {id(fut): fut for fut in futs}.values()
    complete = {}

    def done(res):
        complete[id(res)] = True
        if not waiter.done() and len(complete) == len(unique):
            waiter.set_result(True)

    for fut in unique:
        fut.add_done_callback(done)

    try:
        await waiter
    finally:
        for fut in unique:
            fut.remove_done_callback(done)


async def wait_for_first_future(*futs, name=None):
    """
    Return without error when the first future to be completed is done.
    """
    if not futs:
        return

    waiter = create_future(name=f"||wait_for_first_future({name})[waiter]")
    unique = {id(fut): fut for fut in futs}.values()

    def done(res):
        if not waiter.done():
            waiter.set_result(True)

    for fut in unique:
        fut.add_done_callback(done)

    try:
        await waiter
    finally:
        for fut in unique:
            fut.remove_done_callback(done)


async def stop_async_generator(gen, provide=None, name=None, exc=None):
    try:
        try:
            await gen.athrow(exc or asyncio.CancelledError())
        except StopAsyncIteration:
            pass

        try:
            await gen.asend(provide)
        except StopAsyncIteration:
            pass
    finally:
        await gen.aclose()


def fut_to_string(f, with_name=True):
    if not isinstance(f, asyncio.Future):
        s = repr(f)
    else:
        s = ""
        if with_name:
            s = f"<Future#{getattr(f, 'name', None)}"
        if not f.done():
            s = f"{s}(pending)"
        elif f.cancelled():
            s = f"{s}(cancelled)"
        else:
            exc = f.exception()
            if exc:
                s = f"{s}(exception:{type(exc).__name__}:{exc})"
            else:
                s = f"{s}(result)"
        if with_name:
            s = f"{s}>"
    return s


def reporter(res):
    """
    A generic reporter for asyncio tasks.

    For example:

    .. code-block:: python

        t = loop.create_task(coroutine())
        t.add_done_callback(hp.reporter)

    This means that exceptions are logged to the terminal and you won't
    get warnings about tasks not being looked at when they finish.

    This method will return ``True`` if there was no exception and ``None``
    otherwise.

    It also handles and silences ``asyncio.CancelledError``.
    """
    if not res.cancelled():
        exc = res.exception()
        if exc:
            if not isinstance(exc, KeyboardInterrupt):
                log.exception(exc, exc_info=(type(exc), exc, exc.__traceback__))
        else:
            res.result()
            return True


def silent_reporter(res):
    """
    A generic reporter for asyncio tasks that doesn't log errors.

    For example:

    .. code-block:: python

        t = loop.create_task(coroutine())
        t.add_done_callback(silent_reporter)

    This means that exceptions are **not** logged to the terminal and you won't
    get warnings about tasks not being looked at when they finish.

    This method will return ``True`` if there was no exception and ``None``
    otherwise.

    It also handles and silences ``asyncio.CancelledError``.
    """
    if not res.cancelled():
        exc = res.exception()
        if not exc:
            res.result()
            return True


def ensure_aexit(instance):
    """
    Used to make sure a manual async context manager calls ``__aexit__`` if
    ``__aenter__`` fails.

    Turns out if ``__aenter__`` raises an exception, then ``__aexit__`` doesn't
    get called, which is not how I thought that worked for a lot of context
    managers.

    Usage is as follows:

    .. code-block:: python

        from photons_app import helpers as hp


        class MyCM:
            async def __aenter__(self):
                async with ensure_aexit(self):
                    return await self.start()

            async def start(self):
                ...

            async def __aexit__(self, exc_typ, exc, tb):
                await self.finish(exc_typ, exc, tb)

            async def finish(exc_typ=None, exc=None, tb=None):
                ...
    """

    @contextlib.asynccontextmanager
    async def ensure_aexit_cm():
        exc_info = None
        try:
            yield
        except:
            exc_info = sys.exc_info()

        if exc_info is not None:
            # aexit doesn't run if aenter raises an exception
            await instance.__aexit__(*exc_info)
            exc_info[1].__traceback__ = exc_info[2]
            raise exc_info[1]

    return ensure_aexit_cm()


class AsyncCMMixin:
    async def __aenter__(self):
        async with ensure_aexit(self):
            return await self.start()

    async def start(self):
        raise NotImplementedError()

    async def __aexit__(self, exc_typ, exc, tb):
        return await self.finish(exc_typ, exc, tb)

    async def finish(self, exc_typ=None, exc=None, tb=None):
        raise NotImplementedError()


class ChildOfFuture:
    """
    Create a future that also considers the status of it's parent.

    So if the parent is cancelled, then this future is cancelled.
    If the parent raises an exception, then that exception is given to this result

    The special case is if the parent receives a result, then this future is
    cancelled.

    The recommended use is with it's context manager::

        from photons_app import helpers as hp

        parent_fut = create_future()

        with ChildOfFuture(parent_fut):
            ...

    If you don't use the context manager then ensure you resolve the future when
    you no longer need it (i.e. ``fut.cancel()``) to avoid a memory leak.
    """

    _asyncio_future_blocking = False

    def __init__(self, original_fut, *, name=None):
        self.name = name
        self.fut = create_future(name=f"ChildOfFuture({self.name})::__init__[fut]")
        self.original_fut = original_fut

        self.fut.add_done_callback(self.remove_parent_done)
        self.original_fut.add_done_callback(self.parent_done)

    def __enter__(self):
        return self

    def __exit__(self, exc_typ, exc, tb):
        self.cancel()

    def parent_done(self, res):
        if self.fut.done():
            return

        if res.cancelled():
            self.fut.cancel()
            return

        exc = res.exception()
        if exc:
            self.fut.set_exception(exc)
        else:
            self.fut.cancel()

    def remove_parent_done(self, ret):
        self.original_fut.remove_done_callback(self.parent_done)

    @property
    def _callbacks(self):
        return self.fut._callbacks

    def set_result(self, data):
        if self.original_fut.done():
            self.original_fut.set_result(data)
        self.fut.set_result(data)

    def set_exception(self, exc):
        if self.original_fut.done():
            self.original_fut.set_exception(exc)
        self.fut.set_exception(exc)

    def cancel(self):
        self.fut.cancel()

    def result(self):
        if self.original_fut.done() or self.original_fut.cancelled():
            if self.original_fut.cancelled():
                return self.original_fut.result()
            else:
                self.fut.cancel()
        if self.fut.done() or self.fut.cancelled():
            return self.fut.result()
        return self.original_fut.result()

    def done(self):
        return self.fut.done() or self.original_fut.done()

    def cancelled(self):
        if self.fut.cancelled() or self.original_fut.cancelled():
            return True

        # We cancel fut if original_fut gets a result
        if self.original_fut.done() and not self.original_fut.exception():
            self.fut.cancel()
            return True

        return False

    def exception(self):
        if self.fut.done() and not self.fut.cancelled():
            exc = self.fut.exception()
            if exc is not None:
                return exc

        if self.original_fut.done() and not self.original_fut.cancelled():
            exc = self.original_fut.exception()
            if exc is not None:
                return exc

        if self.fut.cancelled() or self.fut.done():
            return self.fut.exception()

        return self.original_fut.exception()

    def cancel_parent(self):
        if hasattr(self.original_fut, "cancel_parent"):
            self.original_fut.cancel_parent()
        else:
            self.original_fut.cancel()

    def add_done_callback(self, func):
        self.fut.add_done_callback(func)

    def remove_done_callback(self, func):
        self.fut.remove_done_callback(func)

    def __repr__(self):
        return f"<ChildOfFuture#{self.name}({fut_to_string(self.fut, with_name=False)}){fut_to_string(self.original_fut)}>"

    def __await__(self):
        return (yield from self.fut)

    __iter__ = __await__


class ResettableFuture:
    """
    A future object with a ``reset()`` function that resets it

    Usage:

    .. code-block:: python

        fut = ResettableFuture()
        fut.set_result(True)
        await fut == True

        fut.reset()
        fut.set_result(False)
        await fut == False

    Calling reset on one of these will do nothing if it already isn't resolved.

    Calling reset on a resolved future will also remove any registered done
    callbacks.
    """

    _asyncio_future_blocking = False

    def __init__(self, name=None):
        self.name = name
        self.fut = create_future(name=f"ResettableFuture({self.name})::__init__[fut]")

    def reset(self, force=False):
        if force:
            self.fut.cancel()

        if not self.fut.done():
            return

        self.fut = create_future(name=f"ResettableFuture({self.name})::reset[fut]")

    @property
    def _callbacks(self):
        return self.fut._callbacks

    def set_result(self, data):
        self.fut.set_result(data)

    def set_exception(self, exc):
        self.fut.set_exception(exc)

    def cancel(self):
        self.fut.cancel()

    def result(self):
        return self.fut.result()

    def done(self):
        return self.fut.done()

    def cancelled(self):
        return self.fut.cancelled()

    def exception(self):
        return self.fut.exception()

    def add_done_callback(self, func):
        self.fut.add_done_callback(func)

    def remove_done_callback(self, func):
        self.fut.remove_done_callback(func)

    def __repr__(self):
        return f"<ResettableFuture#{self.name}({fut_to_string(self.fut, with_name=False)})>"

    def __await__(self):
        return (yield from self.fut)

    __iter__ = __await__


class TaskHolder(AsyncCMMixin):
    """
    An object for managing asynchronous coroutines.

    Usage looks like:

    .. code-block:: python

        from photons_app import helpers as hp


        final_future = hp.create_future()

        async def something():
            await asyncio.sleep(5)

        with hp.TaskHolder(final_future) as ts:
            ts.add(something())
            ts.add(something())

    If you don't want to use the context manager, you can say:

    .. code-block:: python

        from photons_app import helpers as hp


        final_future = hp.create_future()

        async def something():
            await asyncio.sleep(5)

        ts = hp.TaskHolder(final_future)

        try:
            ts.add(something())
            ts.add(something())
        finally:
            await ts.finish()

    Once your block in the context manager is done the context manager won't
    exit until all coroutines have finished. During this time you may still
    use ``ts.add`` or ``ts.add_task`` on the holder.

    If the ``final_future`` is cancelled before all the tasks have completed
    then the tasks will be cancelled and properly waited on so their finally
    blocks run before the context manager finishes.

    ``ts.add`` will also return the task object that is made from the coroutine.

    ``ts.add`` also takes a ``silent=False`` parameter, that when True will
    not log any errors that happen. Otherwise errors will be logged.

    If you already have a task object, you can give it to the holder with
    ``ts.add_task(my_task)``.

    .. automethod:: add

    .. automethod:: add_task

    .. automethod:: finish
    """

    def __init__(self, final_future, *, name=None):
        self.name = name

        self.ts = []
        self.final_future = ChildOfFuture(
            final_future, name=f"TaskHolder({self.name})::__init__[final_future]"
        )

        self._cleaner = None
        self._cleaner_waiter = ResettableFuture(
            name=f"TaskHolder({self.name})::__init__[cleaner_waiter]"
        )

    def add(self, coro, *, silent=False):
        return self.add_task(async_as_background(coro, silent=silent))

    def _set_cleaner_waiter(self, res):
        self._cleaner_waiter.reset()
        self._cleaner_waiter.set_result(True)

    def add_task(self, task):
        if not self._cleaner:
            self._cleaner = async_as_background(self.cleaner())

            t = self._cleaner

            def remove_cleaner(res):
                if self._cleaner is t:
                    self._cleaner = None

            t.add_done_callback(remove_cleaner)

        task.add_done_callback(self._set_cleaner_waiter)
        self.ts.append(task)
        return task

    async def start(self):
        return self

    async def finish(self, exc_typ=None, exc=None, tb=None):
        if exc and not self.final_future.done():
            self.final_future.set_exception(exc)

        try:
            while any(not t.done() for t in self.ts):
                for t in self.ts:
                    if self.final_future.done():
                        t.cancel()

                if self.ts:
                    if self.final_future.done():
                        await wait_for_all_futures(
                            self.final_future,
                            *self.ts,
                            name=f"TaskHolder({self.name})::finish[wait_for_all_tasks]",
                        )
                    else:
                        await wait_for_first_future(
                            self.final_future,
                            *self.ts,
                            name=f"TaskHolder({self.name})::finish[wait_for_another_task]",
                        )

                    self.ts = [t for t in self.ts if not t.done()]
        finally:
            try:
                await self._final()
            finally:
                self.final_future.cancel()

    async def _final(self):
        if self._cleaner:
            self._cleaner.cancel()
            await wait_for_all_futures(
                self._cleaner, name=f"TaskHolder({self.name})::finish[finally_wait_for_cleaner]"
            )

        await wait_for_all_futures(
            async_as_background(self.clean()),
            name=f"TaskHolder({self.name})::finish[finally_wait_for_clean]",
        )

    @property
    def pending(self):
        return sum(1 for t in self.ts if not t.done())

    def __contains__(self, task):
        return task in self.ts

    def __iter__(self):
        return iter(self.ts)

    async def cleaner(self):
        while True:
            await self._cleaner_waiter
            self._cleaner_waiter.reset()
            await self.clean()

    async def clean(self):
        destroyed = []
        remaining = []
        for t in self.ts:
            if t.done():
                destroyed.append(t)
            else:
                remaining.append(t)

        await wait_for_all_futures(
            *destroyed, name=f"TaskHolder({self.name})::clean[wait_for_destroyed]"
        )
        self.ts = remaining


class ATicker(AsyncCMMixin):
    """
    This object gives you an async generator that yields every ``every``
    seconds, taking into account how long it takes for your code to finish
    for the next yield.

    For example:

    .. code-block:: python

        from photons_app import helpers as hp

        import time


        start = time.time()
        timing = []

        async for _ in ATicker(10):
            timing.append(time.time() - start)
            asyncio.sleep(8)
            if len(timing) >= 5:
                break

        assert timing == [0, 10, 20, 30, 40]

    The value that is yielded is a tuple of (iteration, time_till_next) where
    ``iteration`` is a counter of how many times we yield a value starting from
    1 and the ``time_till_next`` is the number of seconds till the next time we
    yield a value.

    You can use the shortcut :func:`tick` to create one of these, but if you
    do create this yourself, you can change the ``every`` value while you're
    iterating.

    .. code-block:: python

        from photons_app import helpers as hp


        ticker = ATicker(10)

        done = 0

        async with ticker as ticks:
            async for _ in ticks:
                done += 1
                if done == 3:
                    # This will mean the next tick will be 20 seconds after the last
                    # tick and future ticks will be 20 seconds apart
                    ticker.change_after(20)
                elif done == 5:
                    # This will mean the next tick will be 40 seconds after the last
                    # tick, but ticks after that will go back to 20 seconds apart.
                    ticker.change_after(40, set_new_every=False)

    There are three other options:

    final_future
        If this future is completed then the iteration will stop

    max_iterations
        Iterations after this number will cause the loop to finish. By default
        there is no limit

    max_time
        After this many iterations the loop will stop. By default there is no
        limit

    min_wait
        The minimum amount of time to wait after a tick.

        If this is False then we will always just tick at the next expected time,
        otherwise we ensure this amount of time at a minimum between ticks

    pauser
        If not None, we use this as a semaphore in an async with to pause the ticks
    """

    class Stop(Exception):
        pass

    def __init__(
        self,
        every,
        *,
        final_future=None,
        max_iterations=None,
        max_time=None,
        min_wait=0.1,
        pauser=None,
        name=None,
    ):
        self.name = name
        self.every = every
        self.pauser = pauser
        self.max_time = max_time
        self.min_wait = min_wait
        self.max_iterations = max_iterations

        if self.every <= 0:
            self.every = 0
            if self.min_wait is False:
                self.min_wait = 0

        self.handle = None
        self.expected = None

        self.waiter = ResettableFuture(name=f"ATicker({self.name})::__init__[waiter]")
        self.final_future = ChildOfFuture(
            final_future
            or create_future(name=f"ATicker({self.name})::__init__[owned_final_future]"),
            name=f"ATicker({self.name})::__init__[final_future]",
        )

    async def start(self):
        self.gen = self.tick()
        return self

    def __aiter__(self):
        if not hasattr(self, "gen"):
            raise Exception(
                "The ticker must be used as a context manager before being used as an async iterator"
            )
        return self.gen

    async def finish(self, exc_typ=None, exc=None, tb=None):
        if hasattr(self, "gen"):
            try:
                await stop_async_generator(
                    self.gen, exc=exc or self.Stop(), name=f"ATicker({self.name})::stop[stop_gen]"
                )
            except self.Stop:
                pass

        self.final_future.cancel()

    async def tick(self):
        final_handle = None
        if self.max_time:
            final_handle = asyncio.get_event_loop().call_later(
                self.max_time, self.final_future.cancel
            )

        try:
            async for info in self._tick():
                yield info
        finally:
            self.final_future.cancel()
            if final_handle:
                final_handle.cancel()
            self._change_handle()

    def change_after(self, every, *, set_new_every=True):
        old_every = self.every
        if set_new_every:
            self.every = every

        if self.expected is None:
            return

        last = self.expected - old_every

        expected = last + every
        if set_new_every:
            self.expected = expected

        diff = round(expected - time.time(), 3)
        self._change_handle()

        if diff <= 0:
            self.waiter.reset()
            self.waiter.set_result(True)
        else:
            self._change_handle(asyncio.get_event_loop().call_later(diff, self._waited))

    def _change_handle(self, handle=None):
        if self.handle:
            self.handle.cancel()
        self.handle = handle

    def _waited(self):
        self.waiter.reset()
        self.waiter.set_result(True)

    async def _wait_for_next(self):
        if self.pauser is None or not self.pauser.locked():
            return await wait_for_first_future(
                self.final_future,
                self.waiter,
                name=f"ATicker({self.name})::_wait_for_next[without_pause]",
            )

        async def pause():
            async with self.pauser:
                pass

        ts_final_future = ChildOfFuture(
            self.final_future, name=f"ATicker({self.name})::_wait_for_next[with_pause]"
        )

        async with TaskHolder(ts_final_future) as ts:
            ts.add(pause())
            ts.add_task(self.waiter)

    async def _tick(self):
        start = time.time()
        iteration = 0
        self.expected = start

        self._waited()

        while True:
            await self._wait_for_next()

            self.waiter.reset()
            if self.final_future.done():
                return

            if self.max_iterations is not None and iteration >= self.max_iterations:
                return

            now = time.time()
            if self.max_time is not None and now - start >= self.max_time:
                return

            if self.min_wait is False:
                diff = self.expected - now
                if diff == 0:
                    self.expected += self.every
                else:
                    while diff <= -self.every:
                        self.expected += self.every
                        diff = self.expected - now

                    while self.expected - now <= 0:
                        self.expected += self.every
            else:
                diff = self.min_wait
                if self.every > 0:
                    while self.expected - now < self.min_wait:
                        self.expected += self.every

                    diff = round(self.expected - now, 3)

            if diff == 0:
                diff = self.expected - now

            self._change_handle(asyncio.get_event_loop().call_later(diff, self._waited))

            if self.min_wait is not False or diff > 0:
                iteration += 1
                yield iteration, max([diff, 0])


class RetryTicker:
    def __init__(self, *, timeouts, name=None):
        self.name = name
        self.timeouts = timeouts

        self.timeout = None
        self.timeout_item = None

    async def tick(self, final_future, timeout, min_wait=0.1):
        timeouts = list(self.timeouts)
        step, end = timeouts.pop(0)
        ticker = ATicker(
            every=step,
            final_future=final_future,
            max_time=timeout,
            min_wait=min_wait,
            name=f"RetryTicker({self.name})::tick[ticker]",
        )

        start = time.time()
        final_time = time.time() + timeout

        async with ticker as ticks:
            async for _, nxt in ticks:
                now = time.time()

                if end and now - start > end:
                    if timeouts:
                        step, end = timeouts.pop(0)
                        ticker.change_after(step)
                    else:
                        end = None

                yield round(final_time - now, 3), nxt
