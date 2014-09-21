# At some point, I'll have schema'd objects lazily loaded from the
# TDesc files. I'm not there yet. Thus, this module's interface is
# likely to change *substantially* over the coming weeks.

from collections import namedtuple
from . import fnv1
from . import resource
from . import utils
import contextlib
import struct

import yaml

class FormatException(Exception):
    pass

_dword = struct.Struct("=I")



class SimData:
    "An object that is beholden to a schema"

    # These are not directly accessible...
    HIDDEN_MEMBERS = frozenset((
        'HIDDEN_MEMBERS',
        'schema_dict',
        'value_dict',
        'schema',
        'name'
    ))

    def __init__(self, schema):
        schema_dict = {column.name: column
                       for column in schema.columns}
        value_dict = {column.name: None
                      for column in schema.columns}

        # We do funny things with setattribute and getattribute that
        # refer to these values. To prevent using this class in a daft
        # way, we block direct access to this class's instance
        # dictionary except via super().__getattribute__ and
        # super().__setattribute__
        super().__setattr__('schema_dict', schema_dict)
        super().__setattr__('value_dict', value_dict)
        super().__setattr__('schema', schema)

    def __getattribute__(self, name):
        value_dict = super().__getattribute__('value_dict')
        if name in value_dict:
            val = value_dict[name]
            if isinstance(val, utils.Thunk):
                return val.value
            else:
                return val
        elif name in __class__.HIDDEN_MEMBERS: # We don't care about __getattribute__ here
            return AttributeError("This object's instance members are hidden.")
        else:
            return super().__getattribute__(name)
    def __setattribute__(self, name, value):
        schema_dict = super().__getattribute__('schema_dict')
        value_dict = super().__getattribute__('value_dict')
        if name in schema_dict:
            # TODO: validate data value against value_dict
            value_dict[name] = value
        else:
            raise AttributeError("%s not found in schema" % (name,))

    def __setitem__(self, name, value):
        schema_dict = super().__getattribute__('schema_dict')
        value_dict = super().__getattribute__('value_dict')
        if name in schema_dict:
            # TODO: validate data value against value_dict
            value_dict[name] = value
        else:
            raise AttributeError("%s not found in schema" % (name,))
    def __getitem__(self, name):
        value_dict = super().__getattribute__('value_dict')
        if name in value_dict:
            val = value_dict[name]
            if isinstance(val, utils.Thunk):
                return val.value
            else:
                return val
        else:
            raise AttributeError("%s not found in schema" % (name,))

    def __dir__(self):
        return iter(super().__getattribute__("schema_dict"))

def _represent_SimData(dumper, sd):
    mapping = {key:sd[key]
               for key in super(SimData, sd).__getattribute__('value_dict').keys()}
    return dumper.represent_mapping('!s4/tuning', mapping)
yaml.add_representer(SimData, _represent_SimData)

class SimDataReader(utils.BinPacker):
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

        self.tableData = tableData = []
        self.schemas = schemas = {}

        self.off = schemaPos
        for _ in range(numSchemas):
            off = self.off
            schemas[off] = self._readSchema()

        self.off = tablePos

        self.patchups = [] # A set of closures that are called with no
                           # arguments at the end of the parse
        for _ in range(numTables):
            tableData.append(self._readTableHdr())

        self.tables = []
        self.content = {}
        for thdr in tableData:
            table = self._readTable(thdr)
            self.tables.append(table)
            if thdr.name is not None:
                if thdr.row_count != 1:
                    self.errors.append("Named table with >1 element")
                    continue
                else:
                    self.content[thdr.name.decode('utf-8')] = table[0]
        self.tables = list(map(self._readTable, tableData))
        for patch in self.patchups:
            patch()


    def _readTableHdr(self):
        name = self.get_relstring()
        nameHash = self.get_uint32()
        probedHash = fnv1.fnv1((name or b"").lower(), 32)
        assert probedHash == nameHash, ("%08x != %08x (%r)" % (probedHash, nameHash, name))
        schemaPos = self.get_off32()
        dataType = self.get_uint32()
        rowSize = self.get_uint32()
        rowOffset = self.get_off32()
        rowCount = self.get_uint32()

        if schemaPos is not None:
            schema = self.schemas[schemaPos]
        else:
            schema = None
        return self._TableData(name, schema, dataType, rowSize, rowOffset, rowCount)

    def _readSchema(self):
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
                columns.append(self._SchemaColumn(cName.decode("utf-8"), cDataType, cFlags, cOffset, cSchemaPos))
        return self._Schema(name, schemaHash, schemaSize, tuple(columns)) # Tuplifying the columns results in less work for the GC

    def _readTable(self, tableData):
        content = []
        # The template assumes that the table data is all contiguous
        # immediately after the table headers. I'm not sure that
        # actually works in general, and I'm almost certain that
        # that's not how TS4 parses SD resources.
        if tableData.schema is None:
            # TODO: Special-case data_type == TYPE_CHAR8(1)
            for row in range(tableData.row_count):
                with self.at(tableData.row_pos + row * tableData.row_size):
                    content.append(self._read_primitive(tableData.data_type))
            return content
        else:
            assert tableData.schema.size == tableData.row_size, "Table data and schema don't correspond with each other"
            for row in range(tableData.row_count):
                rowBase = tableData.row_pos + row * tableData.row_size
                rowData = SimData(tableData.schema)
                for column in tableData.schema.columns:
                    with self.at(rowBase + column.offset):
                        # TODO: Figure out how to apply fixups
                        rowData[column.name] = self._read_primitive(column.data_type)
                content.append(rowData)
            return content

    def resolve_ref(self, pos, count):
        for i, thdr in enumerate(self.tableData):
            if pos >= thdr.row_pos and pos < thdr.row_pos + thdr.row_size * thdr.row_count:
                table_no = i
                row_idx = int((pos - thdr.row_pos) / thdr.row_size)
                if thdr.row_count < row_idx + count:
                    raise FormatException("Object runs off end of table")
                if row_idx * thdr.row_size + thdr.row_pos != pos:
                    raise FormatException("Unaligned read of an object")
                return (i, slice(row_idx, row_idx+count))
        else:
            raise FormatException("Object not in a table")

    def _read_primitive(self, datatype):
        if datatype == 0: # BOOL
            # Boolean
            return self.get_int8() == 0
        elif datatype == 1: # CHAR8
            return chr(self.get_uint8())
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
            return self.get_relstring().decode('utf-8')
        elif datatype == 12:    # HASHEDSTRING8
            self.align(4)
            res = self.get_relstring()
            shash = self.get_uint32()
            # TODO: Validate hash
            return res.decode('utf-8')
        elif datatype == 13:    # OBJECT
            self.align(4)
            off = self.get_off32()
            tbl_idx, row_slice = self.resolve_ref(off, 1)
            def thunk():
                return self.tables[tbl_idx][row_slice][0]
            return utils.Thunk(thunk)
        elif datatype == 14:    # VECTOR
            self.align(4)
            off = self.get_off32()
            count = self.get_uint32()

            if off is None or count == 0:
                return []
            else:
                tbl_idx, row_slice = self.resolve_ref(off, count)
                def thunk():
                    return self.tables[tbl_idx][row_slice]
                return utils.Thunk(thunk)
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
            return ('tablesetref', self.get_uint64())
        elif datatype == 19:    # RESOURCEKEY
            self.align(8)
            instance = self.get_uint64()
            typ = self.get_uint32()
            group = self.get_uint32()
            return resource.ResourceID(group, instance, typ)
        elif datatype == 20:    # LOCKEY
            self.align(4)
            # I'm pretty sure this refers to an stbl
            return ('lockey', self.get_uint32())
        else:
            # Datatype 21 is defined as "TYPE_UNDEFINED". This is not
            # in any way useful.

            # TODO: Figure out if type 21 is used anywhere, and if so,
            # reverse it.
            raise FormatException("Unknown resource type %d" % (datatype,))
