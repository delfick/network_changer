from setuptools import setup, Extension, find_packages

from network_changer import VERSION

import platform
import shutil
import os

# __file__ can sometimes be "" instead of what we want
# in that case we assume we're already in this directory
this_dir = os.path.dirname(__file__) or "."

install_requires = set(["netifaces>=0.11.0"])
install_requires_available = {
    "sdbus": "sdbus>=0.8.0",
    "sdbus-nm": "sdbus-networkmanager==1.1.0",
}

if platform.system() != "Darwin" and platform.system() != "Windows":
    if shutil.which("nmcli"):
        if "NETWORK_CHANGER_NO_SDBUS" not in os.environ:
            install_requires.add(install_requires_available["sdbus"])
            install_requires.add(install_requires_available["sdbus-nm"])

# fmt: off
setup(
      name = "network-changer"
    , version = VERSION
    , packages = find_packages(include="network_changer.*", exclude=["tests*"])
    , include_package_data = True

    , python_requires = ">= 3.7"

    , install_requires = list(install_requires)

    , extras_require =
      { "tests":
        [ "noseOfYeti==2.3.1"
        , "pytest==7.1.2"
        , "alt-pytest-asyncio==0.6.0"
        , "pytest-helpers-namespace==2021.12.29"
        ]
      , "sdbus":
        [ install_requires_available["sdbus"]
        , install_requires_available["sdbus-nm"]
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
