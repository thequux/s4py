import ziplib
import xml.etree
import pickle
import abc

class TuningType(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def validate_data(self, proposal):
        """Validate that a potential value conforms to this type"""
        pass

    @abc.abstractmethod
    def represent_simdata(self, value, cache):
        """Return a pair of (internal_fragment, external_fragment).

        This function performs the first step of the following
        serialization process:

        1) Elements of the object graph are asked to produce internal
           and external fragments.  An internal fragment is something
           that fits inside a column in a table; an external fragment
           is a set of rows of a table.  Both of these are high-level
           python objects that represent the data *to be serialized*,
           not necessarily the final serialized values.  (e.g., the
           internal fragment for an OBJECT simply contains a reference
           to its external fragment, and the internal fragment for a
           number doesn't necessarily have a defined width).  The
           external fragment MAY be None.

        2) These external fragments are then packed into a reasonably
           small number of tables, which are then allocated space in
           the on-disk representation.  Each external fragment is then
           updated with its final location on disk.

        3) Each internal fragment is then asked to write its value to
           the appropriate location.

        To protect against cycles and maintain structure sharing,
        there is a cache mapping from id(value) to the returned
        pair. Implementations should check that first before
        constructing new fragments.

        """
        pass

    @abc.abstractmethod
    def represent_yaml(self, dumper, obj):
        """Convert obj to YAML nodes"""

class TuningListType(TuningType):
    def __init__(self, inner_type=None, **kwargs):
        super().__init__(inner_type=inner_type, **kwargs)
        self.inner_type = inner_type
    def validate_data(self, proposal):
        if not isinstance(proposal, list) and not isinstance(proposal, tuple):
            return False
        for _ in proposal:
            if not self.inner_type.validate_data(_):
                return False
        else:
            return True
    def represent_yaml(self, dumper, obj):
        return dumper.represent_sequence('tag:yaml.org,2002:seq', obj)

def TuningTupleType(TuningType):
    def __init__(self, members=None, **kwargs):
        # Inner type must be a dict
        super.__init__(members=members, **kwargs)
        self.members = members
    def validate_data(self, proposal):
        if not isinstance(proposal, dict):
            return False
        for key in proposal:
            if key not in self.members:
                return False
            if not self.members[key].validate_data(proposal[key]):
                return False
        else:
            return True
    def represent_yaml(self, dumper, obj):
        return dumper.represent_mapping('tag:yaml.org,2002:map', obj)

# TODO: Represent atomic type, localized strings, etc

class Tunable:
    # TO BE SPECIFIED: How are descriptions, bounds, etc, represented?
    def __init__(self, *kwargs):
                 pass
    @classmethod
    @abc.abstractmethod
    def from_xml(cls, elt):
        """Extract description from TDesc "Tunable" tag and produce a new
        Tunable.

        """
        pass

    @property
    @abc.abstractmethod
    def type(self):
        """Return the TuningType that is expected"""
