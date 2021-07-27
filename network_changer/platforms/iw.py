from network_changer.errors import FailedToConnect, NetworkChangerException
from network_changer.platforms.base import Changer
from network_changer.platforms import iwlib
from network_changer.shell import Commands

from ctypes import cdll, byref, create_string_buffer, cast, POINTER, string_at
from contextlib import contextmanager
from ctypes import c_ubyte, c_double
from errno import EAGAIN, EPERM
import asyncio
import shutil
import fcntl
import time
import os

try:
    iw = cdll.LoadLibrary("libiw.so")
except OSError:
    raise ImportError("No libiw.so found")

SIOCGIWAP = 0x8B15
SIOCSIWSCAN = 0x8B18
SIOCGIWSCAN = 0x8B19
SIOCGIWNAME = 0x8B01
SIOCGIWESSID = 0x8B1B

IW_SCAN_MAX_DATA = 4096

IW_SCAN_DEFAULT = 0x0000  # Default scan of the driver
IW_SCAN_ALL_ESSID = 0x0001  # Scan all ESSIDs
IW_SCAN_THIS_ESSID = 0x0002  # Scan only this ESSID
IW_SCAN_ALL_FREQ = 0x0004  # Scan all Frequencies
IW_SCAN_THIS_FREQ = 0x0008  # Scan only this Frequency
IW_SCAN_ALL_MODE = 0x0010  # Scan all Modes
IW_SCAN_THIS_MODE = 0x0020  # Scan only this Mode
IW_SCAN_ALL_RATE = 0x0040  # Scan all Bit-Rates
IW_SCAN_THIS_RATE = 0x0080  # Scan only this Bit-Rate


class IWProblem(NetworkChangerException):
    pass


class IW(Changer):
    def setup(self):
        self.name = self.name or "wlan0"

    async def do_connect(self, ssid, *, check_connected, progress=None):
        await self.do_disconnect(progress=progress)

        await Commands.run_command(
            ["iw", "dev", self.name, "connect", ssid],
            error_kls=lambda error, stde, stdo: FailedToConnect(
                ssid, self.name, self.__class__, error=f"{error}: {stde}: {stdo}"
            ),
        )

    async def do_disconnect(self, progress=None):
        await Commands.run_command(["iw", "dev", self.name, "disconnect"], ignore_errors=True)
        if shutil.which("ip"):
            await Commands.run_all(
                ["ip", "link", "set", self.name, "down"],
                ["ip", "link", "set", self.name, "up"],
                ignore_errors=True,
            )
        elif shutil.which("ifconfig"):
            await Commands.run_all(
                ["ifconfig", self.name, "down"],
                ["ifconfig", self.name, "up"],
                ignore_errors=True,
            )

    async def do_scan(self, request_scan=True, progress=None):
        with self.iw_sock() as skfd:
            rng = iwlib.struct_iw_range()
            has_range = iw.iw_get_range_info(skfd, self.interface.encode(), byref(rng)) >= 0

            if not has_range or rng.we_version_compiled < 14:
                await self.do_disconnect(progress=progress)
                raise IWProblem("Interface doesn't support scanning.")

            scanopt = iwlib.struct_iw_scan_req()

            for i, ch in enumerate([1, 6, 11]):
                freq = c_double()
                ret = iw.iw_channel_to_freq(ch, byref(freq), byref(rng))
                if ret < 0:
                    raise IWProblem(f"Unknown channel ({ch}) in range")

                iw.iw_float2freq(freq, byref(scanopt.channel_list[i]))

            scanopt.num_channels = 3

            start = time.time()
            while time.time() - start < 15:
                ret, errno, wrq = self.iw_set_ext(skfd, SIOCSIWSCAN)
                if ret < 0:
                    if errno != EPERM:
                        await self.do_disconnect(progress=progress)
                        await asyncio.sleep(1)
                    else:
                        raise IWProblem(
                            f"{self.interface} Interface doesn't support scanning: {os.strerror(errno)}"
                        )
                else:
                    break

            buflen = 0xFFFF
            buffer = create_string_buffer(buflen)
            start = time.time()
            have_reply = False

            while time.time() - start < 15:
                buffer.value = b""

                wrq.u.data.pointer = cast(buffer, POINTER(None))
                wrq.u.data.flags = (
                    IW_SCAN_ALL_ESSID | IW_SCAN_THIS_FREQ | IW_SCAN_ALL_MODE | IW_SCAN_ALL_RATE
                )
                wrq.u.data.length = buflen

                ret, errno, _ = self.iw_get_ext(skfd, SIOCGIWSCAN, wrq=wrq)
                if ret < 0 and errno != EAGAIN:
                    raise IWProblem(
                        f"Failed to get scan info: {self.interface}: {os.strerror(errno)}"
                    )

                if ret == 0:
                    have_reply = True
                    break

                await asyncio.sleep(0.1)

            if not have_reply:
                raise IWProblem(f"Timed out waiting for scan info: {self.interface}")

        iwe = iwlib.struct_iw_event()
        stream = iwlib.struct_stream_descr()

        iw.iw_init_event_stream(byref(stream), buffer, wrq.u.data.length)

        results = []
        nxt = {"bssid": None, "ssid": None}

        while True:
            ret = iw.iw_extract_event_stream(byref(stream), byref(iwe), rng.we_version_compiled)
            if ret <= 0:
                break

            if iwe.cmd == SIOCGIWAP:
                if nxt["bssid"] is not None:
                    results.append(nxt)
                    nxt = {"bssid": None, "ssid": None}

                bssid = ""
                if any(part != 0 for part in iwe.u.ap_addr.sa_data[:6]):
                    bssid = ":".join([f"{part or 0:02x}" for part in iwe.u.ap_addr.sa_data[:6]])
                nxt["bssid"] = bssid
            elif iwe.cmd == SIOCGIWESSID:
                nxt["ssid"] = string_at(iwe.u.essid.pointer, iwe.u.essid.length).decode(
                    errors="ignore"
                )

        if nxt["bssid"] is not None:
            results.append(nxt)

        return results

    async def do_info(self, progress=None):
        with self.iw_sock() as skfd:
            ret, _, _ = self.iw_get_ext(skfd, SIOCGIWNAME)
            if ret != 0:
                raise IWProblem(f"No wireless extensions for {self.interface}")

            wc = iwlib.struct_wireless_config()
            ret = iw.iw_get_basic_config(skfd, self.interface.encode(), byref(wc))
            if ret != 0:
                raise IWProblem(f"iw_get_basic_config failed for interface: {self.interface}")

            ret, _, wrq = self.iw_get_ext(skfd, SIOCGIWAP)
            if ret != 0:
                raise IWProblem(f"iw_get_ext failed for interface: {self.interface}")

            bssid = ""
            if any(part != 0 for part in wrq.u.ap_addr.sa_data[:6]):
                bssid = ":".join([f"{part or 0:02x}" for part in wrq.u.ap_addr.sa_data[:6]])

            return {
                "ssid": "".join([chr(i) for i in wc.essid]).rstrip("\x00"),
                "bssid": bssid,
            }

    @contextmanager
    def iw_sock(self):
        skfd = iw.iw_sockets_open()
        if skfd < 0:
            raise IWProblem("Failed to open iw sockets")

        try:
            yield skfd
        finally:
            iw.close(skfd)

    def iw_get_ext(self, skfd, request, wrq=None):
        if wrq is None:
            wrq = iwlib.struct_iwreq()
            wrq.ifr_ifrn.ifrn_name = (c_ubyte * 16)(*list(bytearray(self.interface.encode())))

        try:
            ret = fcntl.ioctl(skfd, request, wrq)
            errno = 0
        except OSError as error:
            ret = -1
            errno = error.errno
        return ret, errno, wrq

    def iw_set_ext(self, skfd, request):
        return self.iw_get_ext(skfd, request)
