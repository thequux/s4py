# These tools provide generic human-readable descriptions of the
# contents of various filetypes. They may be fairly slow.

from . import simdata
import yaml

type_registry = {}

def find_inspector(type_id):
    return type_registry.get(type_id, Inspector)

def inspects(type_id):
    def wrapper(cls):
        type_registry[type_id] = cls
        return cls
    return wrapper

class Inspector:
    """An inspector presents various aspects of a Sims4 resource in a
    human-readable way."""
    # Up to eight characters that describe this object type
    type_code = "_UNK"
    smart = False

    def __init__(self, content):
        # Initialize an inspector for a specific type of content
        pass

    def content_name(self):
        """Return a human-readable name for the contents of the file, if
        applicable.  If implemented, the content name should be likely
        to be unique"""
        return None

    def pprint(self, stream):
        stream.write("<binary>")


@inspects(0x545ac67a)
class SimdataInspector(Inspector):
    smart = True
    type_code = 'data'

    def __init__(self, content):
        self.sd = simdata.SimDataReader(content)

    def content_name(self):
        if self.sd.content:
            return ", ".join(self.sd.content)

    def pprint(self, stream):
        yaml.dump(self.sd.content, stream)

class XmlInspector(Inspector):
    type_code = "XML"
