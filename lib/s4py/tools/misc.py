import click
from .. import tools
from .. import fnv1

@tools.main.command()
@click.option("--bits", type=int, help="Hash size in bits. Must be 32 or 64")
@click.argument("string")
def hash(bits, string):
    string = string.encode('utf-8')
    if bits not in (32, 64, None):
        click.echo("Invalid hash size", err=True)
        return
    if bits is not None:
        click.echo(("%%0%dx" % (bits / 4,)) % fnv1.fnv1(string, bits))
    else:
        for bits in 32, 64:
            click.echo(("FNV1-%-3d:  %%0%dx" % (bits, bits / 4,)) % fnv1.fnv1(string, bits))
