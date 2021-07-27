from network_changer.platforms import Airport, Windows, OldDBus, DBus, IW

import platform
import shutil


def changer(final_future, name=None, kls=None):
    if kls is None:
        p = platform.system()
        if p == "Darwin":
            kls = Airport
        elif p == "Windows":
            kls = Windows
        else:
            if name != "<iw>" and shutil.which("nmcli"):
                if name == "<olddbus>":
                    kls = OldDBus
                else:
                    kls = DBus
            else:
                kls = IW

    return kls(final_future, name)
