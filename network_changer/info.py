import fnmatch
import time


class ScanInfo:
    @classmethod
    def create(self, info):
        if isinstance(info, ScanInfo):
            return info

        final = []
        for i in info:
            ii = NetworkInfo.create(i)
            if ii.bssid or ii.ssid:
                final.append(ii)

        return ScanInfo(final)

    def __init__(self, info):
        self.info = info

    def __iter__(self):
        return iter(self.info)

    def filter(self, bssid=None, ssid=None):
        result = []
        for ii in self:
            if bssid is None and ssid is None:
                result.append(ii)
                continue

            if bssid is not None and fnmatch.fnmatch(ii.bssid, bssid):
                result.append(ii)
                continue

            if ssid is not None and fnmatch.fnmatch(ii.ssid, ssid):
                result.append(ii)
                continue

        return ScanInfo.create(result)


class NetworkInfo:
    @classmethod
    def create(self, info):
        if isinstance(info, NetworkInfo):
            return info
        return NetworkInfo(info.get("bssid", ""), info.get("ssid", ""), info.get("last_seen", -1))

    def __init__(self, bssid, ssid, last_seen=-1):
        self.ssid = ssid
        self.last_seen = last_seen
        if bssid:
            self.bssid = ":".join(f"{int(part or 0, 16):02x}" for part in bssid.split(":"))
        else:
            self.bssid = ""

    @property
    def age(self):
        if self.last_seen == -1:
            return 0
        return time.time() - self.last_seen

    def present(self):
        yield "Network:"
        yield f"  BSSID: {self.bssid}"
        yield f"   SSID: {self.ssid}"
        yield f"    AGE: {self.age} seconds"
