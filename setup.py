from setuptools import setup, Extension, find_packages

from network_changer import VERSION

import platform
import shutil
import os

# __file__ can sometimes be "" instead of what we want
# in that case we assume we're already in this directory
this_dir = os.path.dirname(__file__) or "."

install_requires = set(["netifaces>=0.11.0"])
install_requires_available = {"sdbus": "sdbus>=0.8.0", "sdbus-nm": "sdbus-networkmanager==1.1.0", "old_dbus": "dbus-next==0.1.2"}

if platform.system() != "Darwin" and platform.system() != "Windows":
    if shutil.which("nmcli"):
        if "NETWORK_CHANGER_NO_SDBUS" not in os.environ:
            install_requires.add(install_requires_available["sdbus"])
            install_requires.add(install_requires_available["sdbus-nm"])

if "NETWORK_CHANGER_INSTALL_SDBUS" in os.environ:
    install_requires.add(install_requires_available["sdbus"])
    install_requires.add(install_requires_available["sdbus-nm"])

if "NETWORK_CHANGER_INSTALL_OLD_DBUS" in os.environ:
    install_requires.add(install_requires_available["old_dbus"])

# fmt: off
setup(
      name = "network-changer"
    , version = VERSION
    , packages = find_packages(include="network_changer.*", exclude=["tests*"])
    , include_package_data = True

    , python_requires = ">= 3.6"

    , install_requires = list(install_requires)

    , extras_require =
      { "tests":
        [ "noseOfYeti==2.0.2"
        , "pytest==6.1.2"
        , "alt-pytest-asyncio==0.5.3"
        , "pytest-helpers-namespace==2019.1.8"
        , "mock==4.0.2"
        ]
      , "old_dbus":
        [ "dbus-next==0.1.2"
        ]
      }

    , entry_points =
      { 'console_scripts' :
        [ 'network_changer = network_changer.executor:main'
        ]
      }

    , author = 'Stephen Moore'
    , license = 'MIT'
    , author_email = 'github@delfick.com'

    , url = "https://github.com/delfick/network_changer"
    , description = 'Utility for changing to an unsecured network'
    , long_description = open("README.rst").read()
    )
# fmt: on
