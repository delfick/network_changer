Network Changer
===============

Some python3.7+ utilities for changing the network you're computer is on

With super thanks to @igo95862 for the sdbus library I use after
https://github.com/igo95862/python-sdbus/issues/1

Installation
------------

Something like::

    > python3 -m venv network_changer
    > ./network_changer/bin/python -m pip install network_changer
    > ./network_changer/network_changer info

On Linux systems with nmcli it'll install sdbus related dbus libraries. You can
modify that behaviour with these environment variables at pip install:

NETWORK_CHANGER_NO_SDBUS
  Don't automatically install sdbus. If you want sdbus anyway then use::

    > python -m pip instal network_changer[sdbus]

On linux systems without nmcli, you'll need ``libiw-dev`` to be installed for
network switching to work. You will also wpasupplicant to be uninstalled and
you need to use this with ``sudo`` so it may call out to ``iw``.

If you are using nmcli on a raspberry Pi, you'll need to do the following::

    > sudo apt-get install network-manager
    # Make /etc/NetworkManager/NetworkManager.conf look like this
    |   [main]
    |   plugins=ifupdown,keyfile
    |   dhcp=internal
    |
    |   [ifupdown]
    |   managed=true
    # Make sure /etc/dhcpcd.conf has "denyinterfaces wlan0" in it somewhere
    > sudo reboot

On a Mac, it'll shell out to the airport CLI command. Note that the only thing
that requires ``sudo`` is disconnection.

There is no Windows support.

Usage
-----

Once you've installed network_manager you have three commands available to you:

network_manager info
    Display the bssid and ssid of the interface

    --interface <iface>
        Specify which interface to use. By default it'll find the one most
        appropriate for your system. So en0 on Mac and wlan0 on a linux

network_manager scan
    Display the bssid and ssid of the access points the interface can see

    --interface <iface>
        Specify which interface to use. By default it'll find the one most
        appropriate for your system. So en0 on Mac and wlan0 on a linux

    --filter-bssid <some string>
        Only show networks whose bssid contains the specified string in it

    --filter-ssid <some string>
        Only show networks whose ssid contains the specified string in it

network_manager connect
    Connect to the network with the specified ssid. Note that this library does
    not support networks that have any type of security.

    --interface <iface>
        Specify which interface to use. By default it'll find the one most
        appropriate for your system. So en0 on Mac and wlan0 on a linux

    --ssid <ssid>
        The ssid to connect to

Changelog
---------

.. _release-0.1.0:

0.1.0 - 12 August 2022
    * Initial release
    * Note that there are no unit tests and this code isn't actively used by me
