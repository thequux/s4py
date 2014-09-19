import os.path
from collections import namedtuple

from .abstractpackage import AbstractPackage
from .. import resource

class FileLocator(namedtuple("FileLocator", "filename")):
    pass

class DirPackage(AbstractPackage):
    """A dirpackage is the most versatile form of package: it is the only
    form that can be opened read/write. It is simply a loose
    collection of properly-named files (in Maxis, S4pe, or colon
    format) in a directory. By default, it writes files in Maxis
    format. """

    def __init__(self, path, *args, mode="r", config=None, **kwargs):
        """The config file is completely overridden by any config file that
        already exists in the directory.
        """

        self.path = os.path.abspath(path)
        if mode == "r":
            if not os.path.exists(self.path):
                raise FileNotFoundError(
                    "Couldn't open directory package at %s"% (path,))
            self._index_cache = None
            self.writable = False
        elif mode == "w":
            if not os.path.isdir(self.path):
                os.makedirs(self.path)
            self._index_cache = None
            self.writable = True

    @property
    def _index(self):
        if self._index_cache is not None:
            return self._index_cache
        self._index_cache = {}
        for fname in os.listdir(self.path):
            fullpath = os.path.join(self.path, fname)
            if not os.path.isfile(fullpath):
                continue
            try:
                rid = resource.ResourceID.from_string(fname)
            except ValueError:
                # Ignore the file
                pass
            else:
                self._index_cache[rid] = resource.Resource(
                    id=rid,
                    locator = fullpath,
                    size = os.stat(fullpath).st_size,
                    package=self)
        return self._index_cache

    def scan_index(self, filter=None):
        for x in self._index:
            if filter is None or filter.match(x):
                yield x

    def _get_content(self, resource):
        return open(resource.locator, "rb").read()
    def __getitem__(self, rid):
        return self._index[rid]
    def flush_index_cache(self):
        self._index_cache = None

    def put(self, rid, value):
        fname = os.path.join(self.path, rid.as_filename())
        with open(fname, "wb") as f:
            f.write(value)
        self._index[rid] = resource.Resource(
            id=rid,
            locator=fname,
            size=len(value),
            package=self)
