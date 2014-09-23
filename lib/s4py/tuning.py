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
    def binary_representer(self, val_list):
        # Emitter is an collector of output tables. 
        
        # TODO: Think about how to collect val_list across all
        # instances of this type and how to return references
        """Return an function that insert all of the objects in val_list into
        a binary stream

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
    def binary_representer(self, val_list):
        pass
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
