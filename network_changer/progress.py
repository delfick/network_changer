import logging
import inspect
import time


class Progress:
    @classmethod
    def no_connect(kls, progress, error, stack_level=0):
        kls.add_to_progress(
            progress,
            logging.ERROR,
            "Failed to connect to the network",
            stack_level=stack_level + 1,
            error=error,
        )

    @classmethod
    def no_scan(kls, progress, error, stack_level=0):
        kls.add_to_progress(
            progress,
            logging.ERROR,
            "Failed to scan the network",
            stack_level=stack_level + 1,
            error=error,
        )

    @classmethod
    def no_info(kls, progress, error, stack_level=0):
        kls.add_to_progress(
            progress,
            logging.ERROR,
            "Failed to get info about the network",
            stack_level=stack_level + 1,
            error=error,
        )

    @classmethod
    def no_networks(kls, progress, stack_level=0):
        kls.add_to_progress(
            progress, logging.WARNING, "Didn't find any wifi networks", stack_level=stack_level
        )

    @classmethod
    def add_to_progress(self, progress, level, msg=None, stack_level=0, at=None, **kwargs):
        if at is None:
            at = time.time()

        mod = None
        try:
            stack = inspect.stack()
            frm = stack[1 + stack_level]
            mod = inspect.getmodule(frm[0])
        except:
            pass

        if mod and hasattr(mod, "__name__"):
            log = logging.getLogger(mod.__name__)
        else:
            log = logging.getLogger("network_changer.progress")

        if progress is None or isinstance(progress, dict):
            s = "" if msg is None else msg
            for k, v in kwargs.items():
                s = f"{s}\n  {k}={v}"

            exc_info = None
            if isinstance(progress, dict) and progress.get("debug") and "error" in kwargs:
                exc_info = (type(kwargs["error"]), kwargs["error"], kwargs["error"].__traceback__)
            log.log(level, s, exc_info=exc_info)
        elif isinstance(progress, list):
            progress.append((at, {"msg": msg, **kwargs}))
        elif callable(progress):
            progress(at, msg, **kwargs)
        else:
            raise Exception("Progress is not None, a list, or a callable")
