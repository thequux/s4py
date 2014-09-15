import abc
import click

from .. import resource

@click.group()
@click.option("--idformat",
              type=click.Choice(tuple(resource.ResourceID.FORMATTERS)),
              default="colon")
def main(idformat):
    resource.ResourceID.DEFAULT_FMT=idformat

