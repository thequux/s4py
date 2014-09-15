from . import utils
import sys

def read_stbl(bstr):
    """Parse a string table (ID 0x220557DA)"""

    f = utils.BReader(bstr)
    if f.get_raw_bytes(4) != b'STBL':
        raise utils.FormatException("Bad magic")
    version = f.get_uint16()
    if version != 5:
        raise utils.FormatException("We only support STBLv5")
    compressed = f.get_uint8()
    numEntries = f.get_uint64()
    f.off += 2
    mnStringLength = f.get_uint32() # This is the total size of all
                                    # the strings plus one null byte
                                    # per string (to make the parsing
                                    # code faster, probably)

    entries = {}
    size = 0
    for _ in range(numEntries):
        keyHash = f.get_uint32()
        flags = f.get_uint8() # What is in this?
        length = f.get_uint16()
        val = f.get_raw_bytes(length).decode('utf-8')
        entries[keyHash] = val
        size += sys.getsizeof(keyHash, val)
    size += sys.getsizeof(entries)
    return entries
