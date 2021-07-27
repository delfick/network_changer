from network_changer.errors import FailedToConnect, NetworkChangerException
from network_changer.platforms.base import Changer
from network_changer import async_helpers as hp
from network_changer.progress import Progress

from dbus_next.errors import DBusError, InterfaceNotFoundError
from dbus_next.signature import Variant as V
from dbus_next.aio import MessageBus
from dbus_next import BusType
import logging
import asyncio
import time
import uuid


class CantResolveInterface(NetworkChangerException):
    def __init__(self, want, available):
        super().__init__()
        self.want = want
        self.available = available

    def __str__(self):
        return "\n".join(
            [
                "Couldn't resolve the interface",
                f"  wanted: {self.want}",
                f"  available: {self.available}",
            ]
        )


class OldDBus(Changer):
    async def do_connect(self, ssid, *, check_connected, progress=None):
        device, manager, _ = await self.dbus_device(progress=progress)
        if device is None:
            raise FailedToConnect(
                ssid, self.name, self.__class__, error="Couldn't find a device to connect to"
            )

        s_con = {
            "type": V("s", "802-11-wireless"),
            "uuid": V("s", str(uuid.uuid4())),
            "id": V("s", ssid),
        }
        s_wifi = {"ssid": V("ay", ssid.encode()), "mode": V("s", "infrastructure")}
        s_ip4 = {"method": V("s", "auto")}
        s_ip6 = {"method": V("s", "ignore")}
        conn = {
            "connection": s_con,
            "802-11-wireless": s_wifi,
            "ipv4": s_ip4,
            "ipv6": s_ip6,
        }
        obj = await self.network_manager_dbus("/org/freedesktop/NetworkManager/Settings")
        settings = obj.get_interface("org.freedesktop.NetworkManager.Settings")
        config_path = await settings.call_add_connection_unsaved(conn)

        info = {"connecting": False}
        connected_fut = hp.create_future(name="LinuxWifi::connect_dbus[connected_fut]")

        def onchanged(interface_name, changed_properties=None, invalidated_properties=None):
            if isinstance(interface_name, dict) and changed_properties is None:
                changed_properties = interface_name

            if "State" in changed_properties:
                state = changed_properties["State"].value
                if state == 40:
                    info["connecting"] = True
                elif state == 60 and info["connecting"] and not connected_fut.done():
                    connected_fut.set_result(True)

        root = await self.network_manager_dbus("/org/freedesktop/NetworkManager")
        root_manager = root.get_interface("org.freedesktop.NetworkManager")
        root_props = root.get_interface("org.freedesktop.DBus.Properties")

        try:
            root_props.on_properties_changed(onchanged)
            start = time.time()
            Progress.add_to_progress(progress, logging.INFO, "joining network")
            access_point = await manager.get_active_access_point()
            await root_manager.call_activate_connection(config_path, device.path, access_point)
            await asyncio.wait([connected_fut], timeout=10)
            info = await self.do_info(progress=progress)
            if info["ssid"] == ssid:
                return
            if not connected_fut.done():
                raise FailedToConnect(
                    ssid, self.name, self.__class__, "Timed out waiting to join the network"
                )
            Progress.add_to_progress(
                progress,
                logging.INFO,
                "Finished joining the network",
                took_seconds=time.time() - start,
            )
        finally:
            try:
                root_props.off_properties_changed(onchanged)
            except Exception as error:
                Progress.add_to_progress(
                    progress, logging.ERROR, "Failed to deregister signal handler", reason=error
                )

    async def do_disconnect(self, progress=None):
        pass

    async def do_info(self, progress=None):
        ssid = ""
        bssid = ""

        device, manager, _ = await self.dbus_device(progress=progress)
        if manager is not None:
            access_point = await manager.get_active_access_point()
            ssid, bssid = await self.dbus_network_info(access_point, progress=progress)

        return {"ssid": ssid, "bssid": bssid}

    async def do_scan(self, request_scan=True, progress=None):
        device, manager, _ = await self.dbus_device(progress=progress)
        if device is None:
            return []

        fut = hp.create_future(name="LinuxWifi::scan_dbus[fut]")
        info = {"last_got": None}
        result = []

        def no_more_aps(last_got, fut):
            if last_got == info["last_got"] and not fut.done():
                fut.set_result(True)

        def onchanged(interface_name, changed_properties=None, invalidated_properties=None):
            if isinstance(interface_name, dict) and changed_properties is None:
                changed_properties = interface_name

            if "LastScan" in changed_properties:
                # This property only happens in new enough network managers
                if not fut.done():
                    fut.set_result(True)

            if "AccessPoints" in changed_properties:
                # This property happens when we get access points
                # it seems I get it multiple times though
                last_got = info["last_got"] = time.time()
                asyncio.get_event_loop().call_later(0.5, no_more_aps, last_got, fut)

        props = device.get_interface("org.freedesktop.DBus.Properties")

        if request_scan:
            try:
                props.on_properties_changed(onchanged)
                start = time.time()
                try:
                    Progress.add_to_progress(progress, logging.INFO, "requesting network scan")
                    await manager.call_request_scan({})
                except DBusError as error:
                    Progress.add_to_progress(
                        progress, logging.ERROR, "Failed to scan the network", reason=error
                    )
                else:
                    await asyncio.wait([fut], timeout=10)
                    Progress.add_to_progress(
                        progress,
                        logging.INFO,
                        "Finished scanning the network",
                        took_seconds=time.time() - start,
                    )
            finally:
                try:
                    props.off_properties_changed(onchanged)
                except Exception as error:
                    Progress.add_to_progress(
                        logging.ERROR, "Failed to deregister signal handler", reason=error
                    )

        for access_point in await manager.call_get_all_access_points():
            ssid, bssid = await self.dbus_network_info(access_point, progress=progress)
            result.append({"bssid": bssid, "ssid": ssid})

        return result

    ########################
    ###   DBUS HELPERS
    ########################

    async def dbus(self):
        if not hasattr(self, "_dbus"):
            self._dbus = await MessageBus(bus_type=BusType.SYSTEM).connect()

        return self._dbus

    async def network_manager_dbus(self, path, introspection="/org/freedesktop/NetworkManager"):
        dbus = await self.dbus()
        introspection = await dbus.introspect("org.freedesktop.NetworkManager", path)
        return dbus.get_proxy_object("org.freedesktop.NetworkManager", path, introspection)

    async def dbus_device(self, complain=False, progress=None):
        obj = await self.network_manager_dbus("/org/freedesktop/NetworkManager")
        manager = obj.get_interface("org.freedesktop.NetworkManager")
        devices = await manager.get_devices()
        found_interfaces = []
        for d in devices:
            device = await self.network_manager_dbus(d)
            props = device.get_interface("org.freedesktop.DBus.Properties")
            state = await props.call_get("org.freedesktop.NetworkManager.Device", "State")
            if state.value <= 2:
                continue

            iface = await props.call_get("org.freedesktop.NetworkManager.Device", "Interface")
            dtype = await props.call_get("org.freedesktop.NetworkManager.Device", "DeviceType")
            if dtype.value == 2:
                found_interfaces.append(iface.value)

                if self.name in (None, "<olddbus>") or iface.value == self.name:
                    manager = device.get_interface("org.freedesktop.NetworkManager.Device.Wireless")
                    return device, manager, iface.value
                else:
                    Progress.add_to_progress(
                        progress,
                        logging.DEBUG,
                        "Skipping network because it does not match what we want",
                        found=iface,
                        want=self.name,
                    )

        if complain:
            raise CantResolveInterface(want=self.name, available=found_interfaces)

        return (None, None, None)

    async def dbus_network_info(self, access_point, progress=None):
        ap_obj = await self.network_manager_dbus(access_point)
        try:
            ap = ap_obj.get_interface("org.freedesktop.NetworkManager.AccessPoint")
        except InterfaceNotFoundError as error:
            Progress.add_to_progress(
                progress,
                logging.ERROR,
                "failed to get a dbus object",
                access_point=access_point,
                reason=error,
            )
            ssid = b""
            bssid = ""
        else:
            ssid = await ap.get_ssid()
            bssid = await ap.get_hw_address()
        return ssid.decode("utf-8", "replace"), bssid
