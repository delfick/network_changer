from network_changer.errors import FailedToConnect, NetworkChangerException
from network_changer.info import NetworkInfo, ScanInfo
from network_changer.retrier import ConnectionRetrier
from network_changer import async_helpers as hp
from network_changer.progress import Progress

from functools import partial
import netifaces
import ipaddress
import logging
import asyncio
import sys


class NoIPInRange(NetworkChangerException):
    def __init__(self, *, available, expected):
        super().__init__()
        self.expected = expected
        self.available = available

    def __str__(self):
        return "\n".join(
            [
                "Couldn't find an IP in the expected range",
                f"  available: {', '.join(self.available)}",
                f"  expected subnet: {self.expected}",
            ]
        )


class CouldntFindSSID(NetworkChangerException):
    def __str__(self):
        return "Couldn't find ssid"


class Changer:
    def __init__(self, final_future, name):
        self.name = name
        self.final_future = final_future
        self.setup()

    def setup(self):
        pass

    @property
    def interface(self):
        if hasattr(self, "_interface"):
            return self._interface
        return self.name

    async def ssid_from(self, ssid, progress=None, retrier=None, timeout=60):
        if callable(ssid):
            if retrier is None:
                retrier = [(1, 10), (5, 30)]

            final_future = hp.ChildOfFuture(
                self.final_future, name="Changer::ssid_from[final_future]"
            )
            try:

                async def determine(*args):
                    ss = await ssid(self, progress=progress)
                    if ss is None:
                        raise CouldntFindSSID()
                    else:
                        return ss

                return await ConnectionRetrier.create(
                    retrier, name=f"{self.__class__.__name__}::ssid_from"
                ).retry(determine, final_future, timeout, progress=progress)
            finally:
                final_future.cancel()
        else:
            return ssid

    async def disconnect(self, progress=None):
        return await self.do_disconnect(progress=progress)

    async def do_disconnect(self, progress=None):
        raise NotImplementedError()

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
        check_connected = partial(
            self.check_connected,
            ssid,
            bssid=check_bssid,
            progress=progress,
            expected_subnet=expected_subnet,
        )

        if check_before:
            if await check_connected():
                return

        final_future = hp.ChildOfFuture(
            self.final_future, name=f"{self.__class__.__name__}::connect[connection_final_future]"
        )
        try:

            async def determine(*args):
                try:
                    ss = await self.ssid_from(ssid)
                    await self.do_connect(ssid=ss, check_connected=check_connected, progress=None)
                    if check_after is False:
                        return
                    if await check_connected():
                        return
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
                except FailedToConnect:
                    raise
                except:
                    exc_info = sys.exc_info()
                    raise FailedToConnect(ssid, self.name, self.__class__, error=exc_info[1])

            return await ConnectionRetrier.create(
                retrier, name=f"{self.__class__.__name__}::connect"
            ).retry(determine, final_future, timeout, progress=progress)
        finally:
            final_future.cancel()

    async def check_connected(self, ssid, bssid=None, progress=None, expected_subnet=None):
        info = await self.info(progress=progress)
        if bssid is not None:
            found = info.bssid == bssid
        else:
            found = info.ssid == await self.ssid_from(ssid, progress=progress)

        if expected_subnet is None or found is False:
            return found

        if self.interface not in netifaces.interfaces():
            return True

        first = {"val": True}
        retrier = [(3, 40)]
        final_future = hp.ChildOfFuture(
            self.final_future, name="Changer::check_connected[look_for_ip]"
        )
        try:

            async def determine(*args):
                if not first["val"]:
                    Progress.add_to_progress(
                        progress, logging.INFO, "Seeing if we have an IP in the expected subnet"
                    )
                first["val"] = False

                addresses = netifaces.ifaddresses(self.interface)
                addresses = [info["addr"] for info in addresses.get(netifaces.AF_INET, [])]
                for addr in addresses:
                    if ipaddress.ip_address(addr) in expected_subnet:
                        return True

                return NoIPInRange(available=addresses, expected=expected_subnet)

            return await ConnectionRetrier.create(
                retrier, name=f"{self.__class__.__name__}::check_connected"
            ).retry(determine, final_future, 40, progress=progress)
        finally:
            final_future.cancel()

        return False

    async def do_connect(self, ssid, check_connected=None, progress=None):
        raise NotImplementedError()

    async def scan(self, request_scan=True, progress=None):
        if self.final_future.done():
            await self.final_future

        try:
            info = await self.do_scan(request_scan=request_scan, progress=progress)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except:
            exc_info = sys.exc_info()
            Progress.no_scan(progress, exc_info[1])
            info = []

        return ScanInfo.create(info)

    async def do_scan(self, request_scan=True, progress=None):
        raise NotImplementedError()

    async def info(self, progress=None):
        try:
            info = await self.do_info(progress=progress)
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise
        except:
            exc_info = sys.exc_info()
            Progress.no_info(progress, exc_info[1])
            info = {"bssid": "", "ssid": ""}

        return NetworkInfo.create(info)

    async def do_info(self, progress=None):
        raise NotImplementedError()
