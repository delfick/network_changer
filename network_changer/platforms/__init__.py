from network_changer.errors import UnsupportedPlatform

import importlib


class Unsupported:
    reason = None

    def __init__(self, final_future, name):
        self.name = name
        self.final_future = final_future

    async def connect(
        self,
        ssid,
        timeout=120,
        progress=None,
        check_bssid=None,
        check_before=True,
        check_after=True,
        expected_subnet=None,
        retrier=None,
    ):
        raise UnsupportedPlatform(self.reason)

    async def disconnect(self, progress=None):
        raise UnsupportedPlatform(self.reason)

    async def scan(self, request_scan=True, progress=None):
        raise UnsupportedPlatform(self.reason)

    async def info(self, progress=None):
        raise UnsupportedPlatform(self.reason)


platforms = []

available = [
    (None, "Windows"),
    ("network_changer.platforms.airport", "Airport"),
    ("network_changer.platforms.dbus", "DBus"),
    ("network_changer.platforms.iw", "IW"),
]

for impt, name in available:
    platforms.append(name)

    try:
        if impt is None:
            raise ImportError(f"No implementation for {name}")
        mod = importlib.import_module(impt)
    except ImportError as error:
        locals()[name] = type(name, (Unsupported,), {"reason": str(error)})
    else:
        locals()[name] = getattr(mod, name)

__all__ = platforms + ["Unsupported"]
