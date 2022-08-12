from network_changer.errors import NetworkChangerException, FailedToConnect
from network_changer.platforms.base import Changer
from network_changer.progress import Progress
from network_changer.shell import Commands

from pathlib import Path


class CouldntFindAirport(NetworkChangerException):
    def __str__(self):
        return "Failed to discover the airport CLI utility"


class BadAirportOutput(NetworkChangerException):
    def __init__(self, headers):
        super().__init__()
        self.headers = headers

    def __str__(self):
        s = [
            "The first line from `airport -s` was unexpected. Should start with SSID BSSID",
            f"  Got: {self.headers}",
        ]
        return "\n".join(s)


class Airport(Changer):
    def setup(self):
        self.name = self.name or "en0"

        locations = [
            "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
            "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/A/Resources/airport",
        ]

        for loc in locations:
            if Path(loc).exists():
                self.airport = loc
                break

        if self.airport is None:
            raise CouldntFindAirport()

    async def do_connect(self, ssid, *, check_connected, progress=None):
        await Commands.run_command(
            ["networksetup", "-setairportnetwork", self.name, ssid],
            error_kls=lambda error, stde, stdo: FailedToConnect(
                ssid, self.name, self.__class__, error=f"{error}\n\nstderr: {stde}\nstdout: {stdo}"
            ),
        )

    async def do_disconnect(self, progress=None):
        # Note this does nothing unless you're root sigh
        return await Commands.run_command([self.airport, "-z"])

    async def do_scan(self, request_scan=True, progress=None):
        output = await Commands.run_command([self.airport, "-s"])
        lines = output.split("\n")

        if len(lines) < 2:
            Progress.no_networks(progress)
            return []

        headers = lines[0]
        ssid_length = headers.find("SSID") + 4

        if headers == "No networks found":
            return []

        if headers[ssid_length : ssid_length + 7] != " BSSID ":
            raise BadAirportOutput(headers)

        result = []

        for line in lines[1:]:
            if not line.strip():
                continue

            ssid = line[:ssid_length].strip()
            bssid = line[ssid_length : ssid_length + 18].strip()
            result.append({"bssid": bssid, "ssid": ssid})

        return result

    async def do_info(self, progress=None):
        ssid = ""
        bssid = ""

        output = await Commands.run_command([self.airport, "-I"])
        lines = output.split("\n")

        for line in lines:
            if "BSSID" in line:
                bssid = line.split(":", 1)[1].lstrip()

            elif "SSID" in line:
                ssid = line.split(":", 1)[1].lstrip()

        return {"bssid": bssid, "ssid": ssid}
