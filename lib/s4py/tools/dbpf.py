import click
import os
import os.path
import sys
from .. import inspect
from .. import package
from .. import tools
from ..resource import ResourceID, ResourceFilter

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

    # TODO: replace with regexes derived from those in resource.py
    group,instance,type = [int(_, 16) if _ else None
                           for _ in s.split(':', 3)]
    if group is not None and instance is not None and type is not None:
        # ResourceID's match function is somewhat faster than
        # ResourceFilter's match function, so we have this small
        # optimization
        return ResourceID(group, instance, type)
    return ResourceFilter(group, instance, type)


@dbpf.command()
@click.option("--decode", "-d", is_flag=True,
              help="Decode the resource")
@click.option("--type", "-t", metavar="TYPE",
              default=None,
              help="""The resource type to decode as (either an int or string; see inspect.py for details)""")
@click.argument("PACKAGE", type=click.Path(exists=True,
                                           dir_okay=False,
                                           readable=True))
@click.argument("item")
def cat(package, item, type, decode):
    """Extract items matching ITEM from PACKAGE"""
    rid = ResourceID.from_string(item)
    dbfile = package.open_package(package, mode="r")
    content = dbfile[rid].content
    if decode:
        if type is None:
            type = rid.type
        else:
            try:
                type = int(type, 16)
            except ValueError:
                pass
        inspector = inspect.find_inspector(type)(content)
        inspector.pprint(sys.stdout)
    else:
        sys.stdout.buffer.write(content)

@dbpf.command(help="extract files from a package")
@click.option("--filter", multiple=True)
@click.option('-o','--outdir', help="Output directory", default="gen")
@click.argument("file", type=click.Path(exists=True,
                                        dir_okay=False,
                                        readable=True))
def extract(file, filter, outdir):
    if filter:
        filters = AnyFilter(parseFilter(f) for f in filter)
    else:
        filters = None
    dbfile = package.open_package(file, mode="r")
    os.makedirs(outdir, exist_ok=True)
    for rid in dbfile.scan_index(filters):
        with open(os.path.join(outdir, rid.as_filename()), "wb") as ofile:
            print(rid)
            ofile.write(dbfile[rid].content)

@dbpf.command(help="list files in a package")
@click.option("--filter", multiple=True)
@click.option("--long", "-l", is_flag=True)
@click.argument("file", type=click.Path(exists=True,
                                        dir_okay=False,
                                        readable=True))
def ls(file, filter, long):
    if filter:
        filters = AnyFilter(parseFilter(f) for f in filter)
    else:
        filters = None
    dbfile = package.open_package(file, mode="r")
    for entry in dbfile.scan_index(filters):
        idx = dbfile[entry]
        if long:
            inspector = inspect.find_inspector(idx.id.type)
            if inspector.smart:
                inspector = inspector(idx.content)
            else:
                inspector = inspector(None)
            desc = inspector.content_name()
            if desc:
                desc = "-- " + desc
            else:
                desc = ""
            print("{id:34s} {type:<8s} {size:>8d} {content_name:s}".format(
                id=str(idx.id),
                type=inspector.type_code,
                size=idx.size,
                content_name=desc))
        else:
            print(idx.id)

# s4py dbpf ls --filter ::545ac67a --filter ::6017E896  ../../docs/Examples/simsmodsquad-novelist.package
