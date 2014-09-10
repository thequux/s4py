import click
import s4py.dbpf
import os, os.path
from .. import tools

@tools.main.group()
def dbpf():
    pass

class AnyFilter:
    def __init__(self, filters):
        self.filters = list(filters)
    def add(self, filter):
        self.filters.append(filter)
        return self
    def match(self, target):
        for filter in self.filters:
            if filter.match(target):
                return True
        return False
    def __str__(self):
        return "(%s)" % (" | ".join(str(x) for x in self.filters))

def parseFilter(s):
    """Parse a filter from a string. The format is
    <group>:<instance>:<type> where any of the fields can be blank.
    Group, instance, and type are specified as hex strings; leading
    0's and the initial 0x are optional."""

    group,instance,type = [int(_, 16) if _ else None
                           for _ in s.split(':', 3)]
    if group is not None and instance is not None and type is not None:
        # ResourceID's match function is somewhat faster than
        # ResourceFilter's match function, so we have this small
        # optimization
        return s4py.dbpf.ResourceID(group, instance, type)
    return s4py.dbpf.ResourceFilter(group, instance, type)    

    
@dbpf.command(help="extract files from a package")
@click.option("--filter", multiple=True)
@click.option('-o','--outdir', help="Output directory", default="gen")
@click.argument("file")
def extract(file, filter, outdir):
    if filter:
        filters = AnyFilter(parseFilter(f) for f in filter)
    else:
        filters = None
    dbfile = s4py.dbpf.DBPFFile(file)
    os.makedirs(outdir, exist_ok=True)
    for idx in dbfile.scan_index(filters, full_entries=True):
        rid = idx.id
        with open(os.path.join(outdir, rid.as_filename()), "wb") as ofile:
            print(rid)
            ofile.write(dbfile[idx])
        

@dbpf.command(help="list files in a package")
@click.option("--filter", multiple=True)
@click.argument("file")
def ls(file, filter):
    if filter:
        filters = AnyFilter(parseFilter(f) for f in filter)
    else:
        filters = None
    dbfile = s4py.dbpf.DBPFFile(file, prescan_index=True)
    for idx in dbfile.scan_index(filters):
        print(idx)

# s4py dbpf ls --filter ::545ac67a --filter ::6017E896  ../../docs/Examples/simsmodsquad-novelist.package