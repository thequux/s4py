from collections import namedtuple
import re
import yaml

class ResourceID(namedtuple("ResourceID", "group instance type")):
    """A DBPF resource ID. This can be used directly as a RID filter; it matches only itself"""
    __slots__ = ()

    DEFAULT_FMT = "colon"
    FORMATTERS = {
        's4pe': 'S4_{id.type:08X}_{id.group:08X}_{id.instance:016X}',
        'colon': '{id.group:08x}:{id.instance:016x}:{id.type:08x}',
        'maxis': '{id.group:08x}!{id.instance:016x}.{id.type:08x}',
    }

    PARSERS = {
        's4pe': 'S4_{type}_{group}_{instance}(?:%%.*)?$',
        'colon': '{group}:{instance}:{type}',
        'maxis': '{group}!{instance}.{type}',
    }

    for fmt in PARSERS:
        PARSERS[fmt] = re.compile(PARSERS[fmt].format(
            type="(?P<type>[0-9A-Fa-f]{,8})",
            group="(?P<group>[0-9A-Fa-f]{,8})",
            instance="(?P<instance>[0-9A-Fa-f]{,16})"))

    def __str__(self):
        return self.FORMATTERS[self.DEFAULT_FMT].format(id=self)

    def match(self, rid):
        """Determine if this RID is the same as the argument. Strictly
        speaking, this is the same as __eq__, but ResourceFilters must
        implement this function
        """
        return rid == self

    def as_filename(self):
        return str(self)

    @classmethod
    def from_string(cls, string):
        # Handles:
        # - colon-format (group:instance:type)
        # - Maxis format (group!instance.type)
        # - S4 format (S4_type_group_instance(?:%%.*)?)
        for parser in cls.PARSERS.values():
            m = parser.fullmatch(string)
            if m:
                return cls(
                    int(m.group('group'), 16),
                    int(m.group('instance'), 16),
                    int(m.group('type'), 16),
                )
        else:
            raise Exception("Invalid rid %s" % (string,))
def _represent_RID(dumper, rid):
    return dumper.represent_scalar('!s4/rid', str(rid))
yaml.add_representer(ResourceID, _represent_RID)

class ResourceFilter:
    """A simple resource filter; this matches iff all specified RID
    components are equal to the ones in the RID being tested"""

    __slots__ = ('group','instance','type')

    def __init__(self, group=None,instance=None,type=None):
        self.group = group
        self.instance = instance
        self.type = type

    def match(self, rid):
        return ((self.group is None or self.group == rid.group) and
                (self.instance is None or self.instance == rid.instance) and
                (self.type is None or self.type == rid.type))
    def __str__(self):
        group = ("%08x"%self.group) if self.group is not None else ""
        instance = ("%16x"%self.instance) if self.instance is not None else ""
        type = ("%08x"%self.type) if self.type is not None else ""
        return ":".join((group,instance,type))
