# Provides useful tools for working with packages, including metapackage support

from . import resource
from . import utils
from collections import namedtuple
import abc
import io
import os.path

class AbstractPackage(abc.ABC):

    def __init__(self):
        self.__stbl_cache = None

    @abc.abstractmethod
    def scan_index(self, filter=None):
        pass

    @abc.abstractmethod
    def _get_content(self, resource):
        """Retrieve the content from Resource (which is guaranteed to have
        been returned from a __getitem__ call to this package)

        """

    @abc.abstractmethod
    def __getitem__(self, item):
        """Maps from a ResourceID to a Resource. Any other usage is an error.

        This method MUST NOT use any caches that are flushed by
        flush_index_cache.

        """

    def flush_index_cache(self):
        """Flush the index cache to save memory. This method is optional; some
        database formats may not need an index cache due to use of an
        efficient file format."""

    @property
    def stbl(self):
        if self.__stbl_cache is None:
            self.__stbl_cache = {}
            for stblid in self.scan_index(
                    resource.ResourceFilter(type=0x220557DA)):
                for key, value in stbl.read_stbl(self[stblid]):
                    self.__stbl_cache[key] = value
        return self.__stbl_cache

class MetaPackage(AbstractPackage):
    """A stack of packages, where the last package added is the first
    package checked for a resource. Each package can be any object
    that implements the AbstractPackage interface.
    """
    def __init__(self, package_list):
        super().__init__()
        self._package_list = package_list
        self._reset_caches()

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

# TODO: also store a reference to the DBPF that this entry is from
class DbpfLocator(namedtuple("DbpfLocator", 'offset raw_len compression')):
    @property
    def deleted(self):
        return self.compression[0] == 0xFFE0

class _DbpfReader(utils.BReader):
    _Header = namedtuple('_Header',
                         'file_version user_version ctime ' +
                         'mtime index_count index_pos index_size')
    @property
    def header(self):
        if hasattr(self, "_header"):
            return self._header

        with self.at(0):
            if self.get_raw_bytes(4) != b'DBPF':
                raise utils.FormatException(
                    "Not a valid DBPF file; invalid magic")

            fileVersion = (self.get_uint32(), self.get_uint32())
            if fileVersion != (2,1):
                raise utils.FormatException("Only DBPF v2.1 is supported")

            userVersion = (self.get_uint32(), self.get_uint32())
            _unused1 = self.get_uint32()
            mnCreationTime = self.get_uint32()
            mnUpdatedTime = self.get_uint32()
            _unused2 = self.get_uint32()
            indexRecordEntryCount = self.get_uint32()
            indexRecordPosLow = self.get_uint32()
            indexRecordSize = self.get_uint32()
            self.off += 16
            indexRecordPosHigh = self.get_uint32()
            self.off += 4 * 6

            if indexRecordPosHigh != 0:
                indexRecordPos = indexRecordPosHigh
            else:
                indexRecordPos = indexRecordPosLow
            self._header = self._Header(fileVersion, userVersion,
                                        mnCreationTime, mnUpdatedTime,
                                        indexRecordEntryCount, indexRecordPos,
                                        indexRecordSize)
            return self._header

    def get_index(self, package=None):
        # Package is used for the package field in Resource
        # This doesn't cache at all.
        _CONST_TYPE = 1
        _CONST_GROUP = 2
        _CONST_INSTAMCE_EX = 4
        header = self.header
        if header.index_pos == 0:
            if header.index_count != 0:
                raise utils.FormatException(
                    "Package contains entries but no index")
            return

        with self.at(header.index_pos):
            flags = self.get_uint32()
            if flags & _CONST_TYPE:        entry_type    = self.get_uint32()
            if flags & _CONST_GROUP:       entry_group   = self.get_uint32()
            if flags & _CONST_INSTAMCE_EX: entry_inst_ex = self.get_uint32()

            for _ in range(header.index_count):
                if not flags & _CONST_TYPE:
                    entry_type    = self.get_uint32()
                if not flags & _CONST_GROUP:
                    entry_group   = self.get_uint32()
                if not flags & _CONST_INSTAMCE_EX:
                    entry_inst_ex = self.get_uint32()
                entry_inst = self.get_uint32()
                entry_pos = self.get_uint32()
                entry_size = self.get_uint32()
                entry_size_decompressed = self.get_uint32()
                if entry_size & 0x80000000:
                    entry_compressed = (self.get_uint16(), self.get_uint16())
                else:
                    entry_compressed = (0,1)
                entry_size &= 0x7FFFFFFF
                locator = DbpfLocator(entry_pos, entry_size, entry_compressed)
                with self.at(None):
                    yield resource.Resource(
                        resource.ResourceID(entry_group,
                                            entry_inst_ex << 32 | entry_inst_ex,
                                            entry_type),
                        locator,
                        entry_size_decompressed,
                        package)

class DbpfPackage(AbstractPackage):
    """A Sims4 DBPF file. This is the format in Sims4 packages, worlds, etc"""

    def __init__(self, name):
        super().__init__()
        if isinstance(name, io.RawIOBase):
            self.file = _DbpfReader(name)
        else:
            self.file = _DbpfReader(open(name, "rb"))
        self._index_cache = None

    def scan_index(self, filter=None):
        if self._index_cache is None:
            self._index_cache = {}
            for item in self.file.get_index(self):
                if item.locator.deleted:
                    continue
                self._index_cache[item.id] = item

        for key in self._index_cache:
            if filter is None or filter.match(key):
                yield key

    def __getitem__(self, resource):
        return self._index_cache[resource]

    def _get_content(self, item):
        assert isinstance(item, resource.Resource)
        assert item.package is self
        self.file.off = item.locator.offset
        ibuf = self.file.get_raw_bytes(item.locator.raw_len)

        if item.locator.compression[0] == 0:
            return ibuf # uncompressed
        elif item.locator.compression[0] == 0xFFFE:
            # BUG: I'm guessing "streamable compression" is the same
            # as RefPack, with a limited buffer size. This may or may
            # not be true, and even if it is, I'd need to know the
            # size of the buffer to do anything sensible.
            return decodeRefPack(ibuf)
        elif item.locator.compression[0] == 0xFFFF:
            return decodeRefPack(ibuf)
        elif item.locator.compression[0] == 0x5A42:
            return zlib.decompress(ibuf, 15, item.size)

    def flush_index_cache(self):
        self._index_cache = None

def decodeRefPack(ibuf):
    """Decode the DBPF compression. ibuf must quack like a bytes"""
    # Based on http://simswiki.info/wiki.php?title=Sims_3:DBPF/Compression
    # Sims4 compression has the first two bytes swapped

    iptr = optr = 0
    flags = ibuf[0]
    if ibuf[1] != 0xFB:
        raise utils.FormatException("Invalid compressed data")
    iptr = 2
    osize = 0 # output size
    for _ in range(4 if flags & 0x80 else 3):
        osize = (osize << 8) | ibuf[iptr]
        iptr += 1

    obuf = bytearray(osize)
    while iptr < len(ibuf):
        numPlaintext = numToCopy = copyOffset = 0
        # Copyoffset is 0-indexed back from obuf[optr]
        # I.e., copyoffset=0 ==> copying starts at obuf[optr-1]

        # Read a control code
        cc0 = ibuf[iptr]; iptr+=1
        if cc0 <= 0x7F:
            cc1 = ibuf[iptr]; iptr+=1
            cc = (cc0,cc1)
            numPlaintext = cc0 & 0x03
            numToCopy = ((cc0 & 0x1C) >> 2) + 3
            copyOffset = ((cc0 & 0x60) << 3) + cc1
        elif cc0 <= 0xBF:
            cc1 = ibuf[iptr]; iptr+=1
            cc2 = ibuf[iptr]; iptr+=1
            cc = (cc0,cc1,cc2)
            numPlaintext = (cc1 & 0xC0) >> 6
            numToCopy = (cc0 & 0x3F) + 4
            copyOffset = ((cc1 & 0x3F) << 8) + cc2
        elif cc0 <= 0xDF:
            cc1 = ibuf[iptr]; iptr+=1
            cc2 = ibuf[iptr]; iptr+=1
            cc3 = ibuf[iptr]; iptr+=1
            cc = (cc0,cc1,cc2,cc3)
            numPlaintext = cc0 & 0x03
            numToCopy = ((cc0 & 0x0C) << 6) + cc3 + 5
            copyOffset = ((cc0 & 0x10) << 12) + (cc1 << 8) + cc2
        elif cc0 <= 0xFB:
            cc = (cc0,)
            numPlaintext = ((cc0 & 0x1F) << 2) + 4
            numToCopy = 0
        else:
            cc = (cc0,)
            numPlaintext = cc0 & 3
            numToCopy = 0

        # Copy from source
        obuf[optr:optr+numPlaintext] = ibuf[iptr:iptr+numPlaintext]
        iptr += numPlaintext
        optr += numPlaintext

        # Copy from output
        for _ in range(numToCopy):
            obuf[optr] = obuf[optr - 1 - copyOffset]
            optr += 1
    # Done decompressing
    return bytes(obuf)

################################################################################
## Probing
################################################################################

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
                return open_metapackage(filename)
            except UnicodeError:
                raise utils.FormatException("Invalid unicode in metapackage")
        raise utils.FormatException("Couldn't identify package format")

def open_metapackage(filename):
    # Metapackages are always read-only
    packages = []
    with open(filename, "r") as f:
        for name in f.readlines():
            name = name.strip("\uFEFF\n")
            packages.append(open_package(name, mode="r"))
    return MetaPackage(packages)
