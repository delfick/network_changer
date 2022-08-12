from network_changer.errors import NetworkChangerException
from network_changer.platforms.base import Changer
from network_changer import async_helpers as hp
from network_changer.progress import Progress

from sdbus_async.networkmanager import (
    NetworkManager,
    NetworkManagerSettings,
    AccessPoint,
    NetworkDeviceWireless,
    NetworkConnectionSettings,
    NetworkDeviceGeneric,
    DeviceState,
    DeviceType,
)
from sdbus import sd_bus_open_system
import logging
import uuid


def boot_time():
    """Return the system boot time expressed in seconds since the epoch."""
    with open("/proc/stat", "rb") as f:
        for line in f:
            if line.startswith(b"btime"):
                return float(line.strip().split()[1])
        raise ImportError("line 'btime' not found in /proc/stat")


BOOT_TIME = boot_time()


class DbusProblem(NetworkChangerException):
    pass


class memoized_property:
    class Empty:
        pass

    def __init__(self, func):
        self.func = func
        self.name = func.__name__
        self.cache_name = "_{0}".format(self.name)

    def __get__(self, instance=None, owner=None):
        if instance is None:
            return self

        if getattr(instance, self.cache_name, self.Empty) is self.Empty:
            setattr(instance, self.cache_name, self.func(instance))
        return getattr(instance, self.cache_name)

    def __set__(self, instance, value):
        setattr(instance, self.cache_name, value)


class DBus(Changer):
    @memoized_property
    def system_bus(self):
        return sd_bus_open_system()

    @memoized_property
    def nm(self):
        return NetworkManager(self.system_bus)

    @memoized_property
    def settings(self):
        return NetworkManagerSettings(self.system_bus)

    async def device(self):
        device = None
        devices_paths = await self.nm.get_devices()
        for device_path in devices_paths:
            generic_device = NetworkDeviceGeneric(device_path, self.system_bus)
            device_type = await generic_device.device_type
            if device_type != DeviceType.WIFI:
                continue

            state = await generic_device.state
            if state not in (
                DeviceState.DISCONNECTED,
                DeviceState.DEACTIVATING,
                DeviceState.ACTIVATED,
            ):
                continue

            interface = await generic_device.interface
            if self.name in (None, "<dbus>") or interface == self.name:
                self._interface = interface
                device = NetworkDeviceWireless(device_path, self.system_bus)
                break

        if not device:
            raise DbusProblem(f"Couldn't find an interface: {self.name}")

        return device

    async def do_connect(self, ssid, *, check_connected, progress=None):
        await self.do_disconnect(progress=progress)

        device = await self.device()
        connection = await self.settings.add_connection_unsaved(
            {
                "connection": {
                    "type": ("s", "802-11-wireless"),
                    "uuid": ("s", str(uuid.uuid4())),
                    "id": ("s", ssid),
                    "interface-name": ("s", self._interface),
                    "autoconnect": ("b", False),
                },
                "802-11-wireless": {"ssid": ("ay", ssid.encode()), "mode": ("s", "infrastructure")},
                "ipv4": {"method": ("s", "auto")},
                "ipv6": {"method": ("s", "ignore")},
            }
        )

        connection = NetworkConnectionSettings(connection, self.system_bus)

        Progress.add_to_progress(
            progress, logging.INFO, f"Activating connection to {self.interface} -> {ssid}"
        )
        await self.nm.activate_connection(
            connection=connection._remote_object_path, device=device._remote_object_path
        )

        async with hp.ATicker(0.5, final_future=self.final_future, max_time=60) as ticker:
            async for _ in ticker:
                state = await device.state
                if state == DeviceState.ACTIVATED:
                    break

        state = await device.state
        if state != DeviceState.ACTIVATED:
            raise DbusProblem(f"Failed to connect: {self.interface}: {DeviceState(state).name}")

    async def do_disconnect(self, progress=None):
        Progress.add_to_progress(progress, logging.INFO, "Disconnecting active connections")
        device = await self.device()
        connections = await device.available_connections
        for conn in connections:
            connection = NetworkConnectionSettings(conn, self.system_bus)
            await connection.delete()

    async def do_scan(self, request_scan=True, progress=None):
        device = await self.device()

        last_scan = await device.last_scan
        await device.request_scan({})
        async with hp.ATicker(0.5, final_future=self.final_future, max_time=5) as ticker:
            async for _ in ticker:
                nxt = await device.last_scan
                if nxt != last_scan:
                    break

        aps = await device.get_all_access_points()

        results = []
        for ap in aps:
            ap = AccessPoint(ap, self.system_bus)
            ssid = (await ap.ssid).decode()
            bssid = (await ap.hw_address).lower()
            last_seen = BOOT_TIME + await ap.last_seen
            results.append({"bssid": bssid, "ssid": ssid, "last_seen": last_seen})

        return results

    async def do_info(self, progress=None):
        device = await self.device()

        state = await device.state
        if state != DeviceState.ACTIVATED:
            return {"bssid": "", "ssid": ""}

        ap = await device.active_access_point
        ap = AccessPoint(ap, self.system_bus)
        ssid = (await ap.ssid).decode()
        bssid = (await ap.hw_address).lower()
        return {"bssid": bssid, "ssid": ssid}
