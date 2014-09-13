# At some point, I'll have schema'd objects lazily loaded from the
# TDesc files. I'm not there yet. Thus, this module's interface is
# likely to change *substantially* over the coming weeks.

from collections import namedtuple
from . import fnv1, dbpf
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

class SimDataReader(BReader):

    _TableData = namedtuple("_TableData", "name schema data_type row_size row_pos row_count")
    _Schema = namedtuple("_Schema", "name schema_hash size columns")
    _SchemaColumn = namedtuple("_SchemaColumn", "name data_type flags offset schema_pos")
    def __init__(self, bstr):
        super().__init__(bstr)
        if bstr[0:4] != b'DATA':
            raise FormatException("This is not a valid simdata file")
        self.off = 4

        version = self.get_uint32()
        tablePos = self.get_off32()
        numTables = self.get_int32()
        schemaPos = self.get_off32()
        numSchemas = self.get_int32()

        self.tables = tables = []
        self.schemas = schemas = {}

        self.off = schemaPos
        for _ in range(numSchemas):
            off = self.off
            schemas[off] = self._readSchema()

        self.off = tablePos
        for _ in range(numTables):
            print("Reading table at %x" %( self.off,))
            tables.append(self._readTable())

    def _readTable(self):
        # f is a BReader
        name = self.get_relstring()
        nameHash = self.get_uint32()
        probedHash = fnv1.fnv1((name or b"").lower(), 32)
        assert probedHash == nameHash, ("%08x != %08x (%r)" % (probedHash, nameHash, name))
        schemaPos = self.get_off32()
        dataType = self.get_uint32()
        rowSize = self.get_uint32()
        rowOffset = self.get_off32()
        rowCount = self.get_uint32()
        return self._TableData(name, self.schemas[schemaPos], dataType, rowSize, rowOffset, rowCount)

    def _readSchema(self):
        # f is a BReader
        name = self.get_relstring()
        nameHash = self.get_uint32()
        assert fnv1.fnv1((name or b"").lower(), 32) == nameHash
        schemaHash = self.get_uint32()
        schemaSize = self.get_uint32()
        columnPos = self.get_off32()
        numColumns = self.get_uint32()

        columns = []
        with self.at(columnPos):
            for _ in range(numColumns):
                cName = self.get_relstring()
                cNameHash = self.get_uint32()
                cDataType = self.get_uint16()
                cFlags = self.get_uint16()
                cOffset = self.get_uint32()
                cSchemaPos = self.get_off32()
                columns.append(self._SchemaColumn(cName, cDataType, cFlags, cOffset, cSchemaPos))
        return self._Schema(name, schemaHash, schemaSize, tuple(columns)) # Tuplifying the columns results in less work for the GC

    def _read_primitive(self, datatype):
        if datatype == 0: # BOOL
            # Boolean
            return self.get_int8() == 0
        elif datatype == 1: # CHAR8
            return self.get_uint8().decode("latin1")
        elif datatype == 2: # INT8
            return self.get_int8()
        elif datatype == 3: # UINT8
            return self.get_uint8()
        elif datatype == 4: # INT16
            self.align(2)
            return self.get_int16()
        elif datatype == 5: # UINT16
            self.align(2)
            return self.get_uint16()
        elif datatype == 6: # INT32
            self.align(4)
            return self.get_int32()
        elif datatype == 7: # UINT32
            self.align(4)
            return self.get_uint32()
        elif datatype == 8: # INT64
            self.align(8)
            return self.get_int64()
        elif datatype == 9: # UINT64
            self.align(8)
            return self.get_uint64()
        elif datatype == 10: # FLOAT
            self.align(4)
            return struct.unpack("<f", self.get_raw_bytes(4))[0]
        elif datatype == 11: # STRING8
            self.align(4)
            return self.get_relstring()
        elif datatype == 12:    # HASHEDSTRING8
            self.align(4)
            res = self.get_relstring()
            shash = self.get_uint32()
            # TODO: Validate hash
            return res
        elif datatype == 13:    # OBJECT
            self.align(4)
            off = self.get_off32()
            return ('object', off)
            # TODO: figure out how to read object from offset
        elif datatype == 14:    # VECTOR
            self.align(4)
            off = self.get_off32()
            count = self.get_uint32()
            return ('vector', off, count)
            # TODO: Read members based on table info
        elif datatype == 15:    # FLOAT2
            self.align(4)
            return struct.unpack("<ff", self.get_raw_bytes(8))
        elif datatype == 16:    # FLOAT3
            self.align(4)
            return struct.unpack("<fff", self.get_raw_bytes(12))
        elif datatype == 17:    # FLOAT4
            self.align(4)
            return struct.unpack("<ffff", self.get_raw_bytes(16))
        elif datatype == 18:    # TABLESETREFERENCE
            self.align(8)
            return ('tablesetref', self.read_uint64())
        elif datatype == 19:    # RESOURCEKEY
            self.align(8)
            instance = self.read_uint64()
            typ = self.read_uint32()
            group = self.read_uint32()
            return dbpf.ResourceID(group, instance, typ)
        elif datatype == 20:    # LOCKEY
            self.align(4)
            return ('lockey', self.read_uint32())
        else:
            # Datatype 21 is defined as "TYPE_UNDEFINED". This is not
            # in any way useful.

            # TODO: Figure out if type 21 is used anywhere, and if so,
            # reverse it.
            raise FormatException("Unknown resource type %d" % (datatype,))
