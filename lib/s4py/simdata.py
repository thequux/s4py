# At some point, I'll have schema'd objects lazily loaded from the
# TDesc files. I'm not there yet. Thus, this module's interface is
# likely to change *substantially* over the coming weeks.

from collections import namedtuple
from . import fnv1
import contextlib
import struct

class FormatException(Exception):
    pass

_dword = struct.Struct("=I")

class BReader:
    def __init__(self, bstr):
        self.raw = bstr
        self._off = 0
    def __getitem__(self, index):
        return bstr[index]
    def seek(self, off):
        assert off < len(self.raw)
        self.off = off

    @property
    def off(self):
        return self._off
    @off.setter
    def off(self, val):
        assert val <= len(self.raw) # <= so that you can point one past the end
        self._off = val

    def get_raw_bytes(self, count):
        res = self.raw[self.off:self.off+count]
        self.off += count
        return res

    def get_off32(self):
        """Read an offset relative to the current position; returns the absolute offset"""
        off = self.off
        res = self.get_int32()
        if res == -0x80000000:
            return None
        else:
            return off + res

    def _get_int(self, size, signed=False):
        return int.from_bytes(self.get_raw_bytes(size)
                              "little", signed=signed)

    def get_uint64(self): return self._get_int(8, False)
    def get_int64(self): return self._get_int(8, True)

    def get_uint32(self): return self._get_int(4, False)
    def get_int32(self): return self._get_int(4, True)

    def get_uint16(self): return self._get_int(2, False)
    def get_int16(self): return self._get_int(2, True)

    def get_uint8(self): return self._get_int(1, False)
    def get_int8(self): return self._get_int(1, True)


    def get_string(self):
        """Read a null-terminated string"""
        endOff = self.raw.index(b'\0', self.off)
        res = self.raw[self.off:endOff]
        self.off = endOff + 1
        return res
        
    def get_relstring(self):
        """Read a string from the next offset, read as an off32"""
        off = self.get_off32()
        if off is not None:
            with self.at(off):
                return self.get_string()
        else:
            return None

    def align(self, size):
        assert size & (size - 1) == 0, "Must align to a power of two"
        self.off = (self.off + size - 1) & (-size)

    @contextlib.contextmanager
    def at(self, posn):
        """Temporarily read from another place

        This is intended to be used like:
        with reader.at(offset):
           # read some stuff
        """
        saved = self.off
        try:
            self.off = posn
            yield
        finally:
            self.off = saved

        

class SimData:

    _TableData = namedtuple("_TableData", "name schema data_type row_size row_pos row_count")
    _Schema = namedtuple("_Schema", "name schema_hash size columns")
    _SchemaColumn = namedtuple("_SchemaColumn", "name data_type flags offset schema_pos")
    def __init__(self):
        pass

    def fromBytes(self, bstr):
        f = BReader(bstr)
        if bstr[0:4] != b'DATA':
            raise FormatException("This is not a valid simdata file")
        f.off = 4
        
        version = f.get_uint32()
        tablePos = f.get_off32()
        numTables = f.get_int32()
        schemaPos = f.get_off32()
        numSchemas = f.get_int32()

        f.off = tablePos
        tables = []
        schemas = {}
        for _ in range(numTables):
            print("Reading table at %x" %( f.off,))
            tables.append(self._readTable(f))
        
        f.off = schemaPos
        for _ in range(numSchemas):
            off = f.off
            schemas[off] = self._readSchema(f)

        return (tables, schemas)
        

    def _readTable(self, f):
        # f is a BReader
        name = f.get_relstring()
        nameHash = f.get_uint32()
        probedHash = fnv1.fnv1((name or b"").lower(), 32)
        assert probedHash == nameHash, ("%08x != %08x (%r)" % (probedHash, nameHash, name))
        schemaPos = f.get_off32()
        dataType = f.get_uint32()
        rowSize = f.get_uint32()
        rowOffset = f.get_off32()
        rowCount = f.get_uint32()
        return self._TableData(name, schemaPos, dataType, rowSize, rowOffset, rowCount)
    
    def _readSchema(self, f):
        # f is a BReader
        name = f.get_relstring()
        nameHash = f.get_uint32()
        assert fnv1.fnv1((name or b"").lower(), 32) == nameHash
        schemaHash = f.get_uint32()
        schemaSize = f.get_uint32()
        columnPos = f.get_off32()
        numColumns = f.get_uint32()

        columns = []
        with f.at(columnPos):
            for _ in range(numColumns):
                cName = f.get_relstring()
                cNameHash = f.get_uint32()
                cDataType = f.get_uint16()
                cFlags = f.get_uint16()
                cOffset = f.get_uint32()
                cSchemaPos = f.get_off32()
                columns.append(self._SchemaColumn(cName, cDataType, cFlags, cOffset, cSchemaPos))
        return self._Schema(name, schemaHash, schemaSize, tuple(columns)) # Tuplifying the columns results in less work for the GC
