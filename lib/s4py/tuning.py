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
        """Return an function that insert all of the objects in val_list into
        a binary stream

        """
        pass

    @abc.abstractmethod
    def represent_yaml(self, dumper, obj):
        """Convert obj to YAML nodes"""

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

# TODO: Implement list, tuple, and atomic types
