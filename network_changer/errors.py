from platform import system


class NetworkChangerException(Exception):
    pass


class UnsupportedPlatform(NetworkChangerException):
    def __init__(self, reason):
        super().__init__()
        self.reason = reason

    def __str__(self):
        return f"Network changer does not support changing networks on this platform ({system()}): {self.reason}"


class FailedToConnect(NetworkChangerException):
    def __init__(self, ssid, interface, platform, *, error):
        super().__init__()
        self.ssid = ssid
        self.error = error
        self.platform = platform
        self.interface = interface

        if isinstance(self.error, bytes):
            self.error = self.error.decode()

    def __str__(self):
        return "\n".join(
            [
                "Failed to connect to a network.",
                "",
                f"  ssid: {self.ssid}",
                f"  interface: {self.interface}",
                f"  platform: {self.platform}",
                f"  error: {self.error}",
            ]
        )
