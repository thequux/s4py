#!/usr/bin/python3
import struct
import sys
import pprint
import zlib
from .resource import ResourceID, ResourceFilter
from collections import namedtuple

class FormatException(Exception):
    pass

# TODO: also store a reference to the DBPF that this entry is from
class IndexEntry(namedtuple("IndexEntry", 'id offset size size_decompressed compression')):
    @property
    def deleted(self):
        return self.compression[0] == 0xFFE0

foo = [None]
class DBPFFile:
    """A Sims4 DBPF file. This is the format in Sims4 packages, worlds, etc"""
    _CONST_TYPE = 1
    _CONST_GROUP = 2
    _CONST_INSTAMCE_EX = 4
    
    def __init__(self, name, prescan_index=True):
        self.file = open(name, "rb")
        self._index_cache = None
        self._read_header()
        if prescan_index:
            self._index_cache = list(self.scan_index(full_entries=True))
    def _read_header(self):

        self.file.seek(0)
        buf = self.file.read(96)

        if buf[0:4] != b"DBPF":
            raise FormatException("Wrong magic")
        self.file_version = struct.unpack_from("=II", buf, 4)
        if self.file_version != (2,1):
            raise FormatException("Don't know how to handle anything other than DBPF v2.1")

        # TODO: check the accuracy of this; it's based on code I had
        # lying around for Sims3 DBPF files
        self._index_count, self._index_size, self._index_vsn, self._index_off = struct.unpack_from("=I4xI12xII", buf, 36)

    def _get_dword(self, dword=struct.Struct("=I")):
        """This is only ever intended to be called with no arguments; the
        dword kwarg is a function static"""
        return dword.unpack(self.file.read(4))[0]
    def scan_index(self, filter=None, full_entries=False):
        """Iterate over the items that match a filter"""
        if full_entries:
            xform = lambda x: x
        else:
            xform = lambda x: x.id
        if self._index_cache is not None:
            if filter is None:
                for x in self._index_cache:
                    yield xform(x)
            else:
                for x in self._index_cache:
                    if filter.match(x.id):
                        yield xform(x)
            return
        if self._index_off == 0:
            if self._index_count == 0:
                # Empty DBPF file.
                return
            else:
                raise FormatException("Missing index")
        self.file.seek(self._index_off)
        flags = self._get_dword()

        if flags & self._CONST_TYPE:
            entry_type = self._get_dword()
        if flags & self._CONST_GROUP:
            entry_group = self._get_dword()
        if flags & self._CONST_INSTAMCE_EX:
            entry_instance_ex = self._get_dword()

        for n in range(self._index_count):
            if not flags & self._CONST_TYPE:
                entry_type = self._get_dword()
            if not flags & self._CONST_GROUP:
                entry_group = self._get_dword()
            if not flags & self._CONST_INSTAMCE_EX:
                entry_instance_ex = self._get_dword()
            entry_instance = self._get_dword()
            entry_offset = self._get_dword()
            entry_size = self._get_dword()
            entry_size_decompressed = self._get_dword()
            if entry_size & 0x80000000:
                entry_compressed = struct.unpack("=HH", self.file.read(4))
            else:
                entry_compressed = (0,1)
            entry_size = entry_size & 0x7FFFFFFF
            rid = ResourceID(entry_group, (entry_instance_ex << 32) | entry_instance, entry_type)
            if filter is None or filter.match(rid):
                # The process of reading the index may be interleaved
                # with reading the contents of the file. This way, we
                # don't lose the file pointer
                cur_pos = self.file.tell()
                if full_entries:
                    yield IndexEntry(rid, entry_offset, entry_size,
                                     entry_size_decompressed, entry_compressed)
                else:
                    yield rid
                self.file.seek(cur_pos)

            
    def __getitem__(self, item):
        if isinstance(item, int):
            item = self._index_cache[item]
        elif not isinstance(item, IndexEntry):
            # It must be a filter
            itemlist = self.scan_index(item, full_entries=True)
            try:
                item = next(itemlist)
            except StopIteration:
                raise KeyError("No item found")
            try:
                next(itemlist)
            except StopIteration:
                pass
            else:
                raise KeyError("More than one item found")
        # At this point, we know that the item is an IndexEntry;
        # hopefully it is one that refers to this file ;-)
        self.file.seek(item.offset)
        ibuf = self.file.read(item.size)

        if item.compression[0] == 0:
            return ibuf # uncompressed
        elif item.compression[0] == 0xFFFE:
            # BUG: I'm guessing "streamable compression" is the same
            # as RefPack, with a limited buffer size. This may or may
            # not be true, and even if it is, I'd need to know the
            # size of the buffer to do anything sensible.
            return decodeRefPack(ibuf)
        elif item.compression[0] == 0xFFFF:
            return decodeRefPack(ibuf)
        elif item.deleted:
            raise KeyError("Deleted file")
        elif item.compression[0] == 0x5A42:
            # BUG: Not sure if the gzip header is needed. If it is,
            # change -15 in the next line to 15
            return zlib.decompress(ibuf, 15, item.size_decompressed)

def decodeRefPack(ibuf):
    """Decode the DBPF compression. ibuf must quack like a bytes"""
    # Based on http://simswiki.info/wiki.php?title=Sims_3:DBPF/Compression
    # Sims4 compression has the first two bytes swapped
    
    iptr = optr = 0
    flags = ibuf[0]
    if ibuf[1] != 0xFB:
        raise FormatException("Invalid compressed data")
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

        
