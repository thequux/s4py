from collections import namedtuple

class ResourceID(namedtuple("ResourceID", "group instance type")):
    """A DBPF resource ID. This can be used directly as a RID filter; it matches only itself"""
    __slots__ = ()
    def __repr__(self):
        return "%08x!%016x.%08x" % (self.group, self.instance, self.type)

    def match(self, rid):
        """Determine if this RID is the same as the argument. Strictly speaking,
        this is the same as __eq__, but ResourceFilters must implement this function"""
        return rid == self

    def as_filename(self):
        return str(self)

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
