from dagster import ModeDefinition, 

from dagster.legacy import pipeline resource
from dagster.legacy import solid


@resource
def external_service():
    ...


@solid(required_resource_keys={"external_service"})
def do_something():
    ...


@pipeline(
    mode_defs=[ModeDefinition(resource_defs={"external_service": external_service})]
)
def do_it_all():
    do_something()
