import io
from collections import namedtuple
import zlib

from .abstractpackage import AbstractPackage
from .. import resource
from .. import utils

class DbpfLocator(namedtuple("DbpfLocator", 'offset raw_len compression')):
    @property
    def deleted(self):
        return self.compression[0] == 0xFFE0

class _DbpfReader(utils.BinPacker):
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
            print(self.off)
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

class _DbpfWriter:
    def __init__(self, fstream):
        self.f = utils.BinPacker(fstream, mode="w")
        # Skip over header. The official docs say the header is 92
        # bytes, but all the RE'd docs say 96. Treating an extra 4
        # bytes as reserved won't hurt, so we just use 96 here
        self.f.off = 96
    def put_rsrc(self, rid, content):
        off = self.f.off
        zcontent = zlib.compress(content)
        self.f.put_raw_bytes(zcontent)
        locator = DbpfLocator(off, len(zcontent), (0x54A2, 1))
        return locator
    def write_index(self, idx):
        with self.f.at(None):
            idx_start = self.f.off
            idx_count = 0
            # Save the current position, in case we decide to write
            # more content

            # For now, don't try to optimize the index by sharing
            # group/type/etc; it's fairly unlikely that it will be
            # possible to save a significant amount of space unless
            # the file is very small, in which case who cares?
            self.f.put_uint32(0) # No flags

            for rsrc in idx.values():
                idx_count += 1
                self.f.put_uint32(rsrc.id.type)
                self.f.put_uint32(rsrc.id.group)
                self.f.put_uint32(rsrc.id.instance >> 32)
                self.f.put_uint32(rsrc.id.instance & 0xFFFFFFFF)
                self.f.put_uint32(rsrc.locator.offset)
                if rsrc.locator.raw_len & 0x80000000 != 0:
                    raise FormatException("File must be smaller than 2GB")
                # We always compress, so we always need the ExtendedCompression
                # bit set
                self.f.put_uint32(rsrc.locator.raw_len | 0x80000000)
                self.f.put_uint32(rsrc.size)
                self.f.put_uint16(rsrc.locator.compression[0])
                self.f.put_uint16(rsrc.locator.compression[1])
            idx_end = self.f.off
        header = _DbpfReader._Header((2,1), (0,0), 0,0,
                                     idx_count, idx_start, idx_end - idx_start)
        self.put_header(header)
    def put_header(self, header):
        with self.f.at(0):
            print(self.f.off)
            self.f.put_raw_bytes(b'DBPF')
            self.f.put_uint32(header.file_version[0])
            self.f.put_uint32(header.file_version[1])
            self.f.put_uint32(header.user_version[0])
            self.f.put_uint32(header.user_version[1])
            self.f.put_uint32(0)
            self.f.put_uint32(header.ctime)
            self.f.put_uint32(header.mtime)
            self.f.put_uint32(0)
            self.f.put_uint32(header.index_count)
            self.f.put_uint32(0)
            self.f.put_uint32(header.index_size)
            self.f.put_uint32(0)
            self.f.put_uint32(0)
            self.f.put_uint32(0)
            self.f.put_uint32(3)
            self.f.put_uint32(header.index_pos)
            for _ in range(6):
                self.f.put_uint32(0)
            print(self.f.off)
class DbpfPackage(AbstractPackage):
    """A Sims4 DBPF file. This is the format in Sims4 packages, worlds, etc"""

    def __init__(self, name, mode="r"):
        super().__init__()
        if isinstance(name, io.RawIOBase):
            self.file = _DbpfReader(name)
        else:
            if mode == 'r':
                self.file = _DbpfReader(open(name, "rb"))
                self._index_cache = None
                self.writable = False
            elif mode == 'w':
                self.file = _DbpfWriter(open(name, "w+b"))
                self._index_cache = {}
                self.writable = True
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
        with self.file.at(item.locator.offset):
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
        # If we're writable, the in-memory "cache" is actually the
        # *only* copy of the index, so it shouldn't be flushed.
        if not self.writable:
            self._index_cache = None

    def commit(self):
        if self.writable:
            self.file.write_index(self._index_cache)
    def put(self, rid, content):
        if self.writable:
            locator = self.file.put_rsrc(rid, content)
            self._index_cache[rid] = resource.Resource(
                rid, locator, len(content), self)
        else:
            raise TypeError("Not a writable package")
    def close(close):
        super().close()
        self.file.close()

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
