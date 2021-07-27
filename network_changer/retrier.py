from network_changer import async_helpers as hp
from network_changer.progress import Progress

import logging
import asyncio
import time
import sys


class ConnectionRetrier:
    @classmethod
    def create(self, retrier, name=None):
        if retrier is None:
            retrier = [(3, 15), (5, 30)]

        if isinstance(retrier, list):
            return ConnectionRetrier(timeouts=retrier, name=name)
        else:
            return retrier

    def __init__(self, *, timeouts, name=None):
        self.name = name
        self.timeouts = timeouts

        self.timeout = None
        self.timeout_item = None

    async def retry(self, determine, final_future, timeout, min_wait=0.1, progress=None):
        timeouts = list(self.timeouts)
        step, end = timeouts.pop(0)
        ticker = hp.ATicker(
            every=step,
            final_future=final_future,
            max_time=timeout,
            min_wait=min_wait,
            name=f"ConnectionRetrier({self.name})::tick[ticker]",
        )

        start = time.time()
        final_time = time.time() + timeout

        error = None

        async with ticker as ticks:
            async for _, nxt in ticks:
                if error is not None:
                    Progress.add_to_progress(progress, logging.ERROR, "Failure", error=error)
                    error = None

                now = time.time()

                if end and now - start > end:
                    if timeouts:
                        step, end = timeouts.pop(0)
                        ticker.change_after(step)
                    else:
                        end = None

                try:
                    return await determine(round(final_time - now, 3), nxt)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
                except:
                    exc_info = sys.exc_info()
                    error = exc_info[1]

        if error:
            raise error
