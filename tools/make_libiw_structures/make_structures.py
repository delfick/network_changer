#!/usr/bin/env python

from pathlib import Path
import sys
import os

here = Path(__file__).absolute().parent
destination = here / ".." / ".." / "network_changer" / "platforms" / "iwlib.py"

__import__("venvstarter").manager(
    [
        "clang2py",
        "--clang-args=-I/usr/lib/clang/7/include/",
        "-l",
        "/usr/lib/aarch64-linux-gnu/libiw.so",
        "-o",
        destination,
        here / "file.c",
    ]
).add_pypi_deps("ctypeslib2==2.3.2").run()
