from .abstractpackage import AbstractPackage
from .. import resource

class MetaPackage(AbstractPackage):
    """A stack of packages, where the last package added is the first
    package checked for a resource. Each package can be any object
    that implements the AbstractPackage interface.
    """
    def __init__(self, package_list):
        super().__init__()
        self._package_list = package_list
        self._reset_caches()

    @classmethod
    def open(cls, filename):
        # Metapackages are always read-only
        packages = []
        with open(filename, "r") as f:
            for name in f.readlines():
                name = name.strip("\uFEFF\n")
                packages.append(open_package(name, mode="r"))
        return cls(packages)

    def scan_index(self, filter=None):
        if filter is None:
            return self._entry_cache.keys()
        return (rid for rid in self._entry_cache
                    if filter.match(rid))

    def __getitem__(self, key):
        return self._entry_cache[key]

    def _get_content(self, resource):
        # This should never actually get called as we shouldn't be in
        # the package field of any resources. Still, if somebody
        # *does* decide to call this method directly, it should work.
        return _resource.package._get_content(resource)

    def flush_index_cache(self):
        self._entry_cache = None
    def _reset_caches(self):
        from . import stbl
        self._entry_cache = {}
        for package in self._package_list:
            for id in package.scan_index():
                self._entry_cache[id] = package[id]
            package.flush_index_cache()
