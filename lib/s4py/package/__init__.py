# Provides useful tools for working with packages, including metapackage support

from collections import namedtuple
import os.path

from .. import utils
from .metapackage import MetaPackage
from .dbpf import DbpfPackage
from .dirpackage import DirPackage

def open_package(filename, mode="r"):
    absname = os.path.abspath(filename)
    import sys
    if mode == "r":
        if not os.path.exists(filename):
            raise FileNotFoundError(
                "No such file or directory: %s" % (filename,))
        if os.path.isdir(filename):
            return DirPackage(absname)
        with open(filename, "rb") as f:
            magic = f.read(4)
            if magic == b"DBPF":
                return DbpfPackage(filename)
        if filename.lower().endswith(".meta"):
            # It's a metapackage...
            try:
                return MetaPackage.open(filename)
            except UnicodeError:
                raise utils.FormatException("Invalid unicode in metapackage")
        raise utils.FormatException("Couldn't identify package format")
    elif mode == 'w':
        if filename.endswith(".package"):
            return DbpfPackage(filename, "w")
        elif filename.endswith("/") or os.path.isdir(filename):
            return DirPackage(filename, mode="w")
