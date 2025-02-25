from dagster import (
    Failure,
    Field,
    IOManager,
    InputDefinition,
    Int,
    ModeDefinition,
    OutputDefinition,
    PresetDefinition,
    ResourceDefinition,
    RetryRequested,
    String,
    execute_pipeline,
    io_manager,
    pipeline,
)
from dagster.legacy import solid
from dagster.utils import segfault


class ExampleException(Exception):
    pass


class ErrorableIOManager(IOManager):
    def __init__(self, throw_input, throw_output):
        self._values = {}
        self._throw_input = throw_input
        self._throw_output = throw_output

    def handle_output(self, context, obj):
        if self._throw_output:
            raise ExampleException("throwing up trying to handle output")

        keys = tuple(context.get_identifier())
        self._values[keys] = obj

    def load_input(self, context):
        if self._throw_input:
            raise ExampleException("throwing up trying to load input")

        keys = tuple(context.upstream_output.get_identifier())
        return self._values[keys]


@io_manager(
    config_schema={
        "throw_in_load_input": Field(bool, is_required=False, default_value=False),
        "throw_in_handle_output": Field(bool, is_required=False, default_value=False),
    }
)
def errorable_io_manager(init_context):
    return ErrorableIOManager(
        init_context.resource_config["throw_in_load_input"],
        init_context.resource_config["throw_in_handle_output"],
    )


class ErrorableResource:
    pass


def resource_init(init_context):
    if init_context.resource_config["throw_on_resource_init"]:
        raise Exception("throwing from in resource_fn")
    return ErrorableResource()


def define_errorable_resource():
    return ResourceDefinition(
        resource_fn=resource_init,
        config_schema={
            "throw_on_resource_init": Field(bool, is_required=False, default_value=False)
        },
    )


solid_throw_config = {
    "throw_in_solid": Field(bool, is_required=False, default_value=False),
    "failure_in_solid": Field(bool, is_required=False, default_value=False),
    "crash_in_solid": Field(bool, is_required=False, default_value=False),
    "return_wrong_type": Field(bool, is_required=False, default_value=False),
    "request_retry": Field(bool, is_required=False, default_value=False),
}


def _act_on_config(solid_config):
    if solid_config["crash_in_solid"]:
        segfault()
    if solid_config["failure_in_solid"]:
        try:
            raise ExampleException("sample cause exception")
        except ExampleException as e:
            raise Failure(
                description="I'm a Failure",
                metadata={
                    "metadata_label": "I am metadata text",
                },
            ) from e
    elif solid_config["throw_in_solid"]:
        raise ExampleException("I threw up")
    elif solid_config["request_retry"]:
        raise RetryRequested()


@solid(
    output_defs=[OutputDefinition(Int)],
    config_schema=solid_throw_config,
    required_resource_keys={"errorable_resource"},
)
def emit_num(context):
    _act_on_config(context.solid_config)

    if context.solid_config["return_wrong_type"]:
        return "wow"

    return 13


@solid(
    input_defs=[InputDefinition("num", Int)],
    output_defs=[OutputDefinition(String)],
    config_schema=solid_throw_config,
    required_resource_keys={"errorable_resource"},
)
def num_to_str(context, num):
    _act_on_config(context.solid_config)

    if context.solid_config["return_wrong_type"]:
        return num + num

    return str(num)


@solid(
    input_defs=[InputDefinition("string", String)],
    output_defs=[OutputDefinition(Int)],
    config_schema=solid_throw_config,
    required_resource_keys={"errorable_resource"},
)
def str_to_num(context, string):
    _act_on_config(context.solid_config)

    if context.solid_config["return_wrong_type"]:
        return string + string

    return int(string)


@pipeline(
    description=(
        "Demo pipeline that enables configurable types of errors thrown during pipeline execution, "
        "including solid execution errors, type errors, and resource initialization errors."
    ),
    mode_defs=[
        ModeDefinition(
            name="errorable_mode",
            resource_defs={
                "errorable_resource": define_errorable_resource(),
                "io_manager": errorable_io_manager,
            },
        ),
    ],
    preset_defs=[
        PresetDefinition.from_pkg_resources(
            "passing",
            pkg_resource_defs=[("dagster_test.toys.environments", "error.yaml")],
            mode="errorable_mode",
        )
    ],
    tags={"monster": "error"},
)
def error_monster():
    start = emit_num.alias("start")()
    middle = num_to_str.alias("middle")(num=start)
    str_to_num.alias("end")(string=middle)


if __name__ == "__main__":
    result = execute_pipeline(
        error_monster,
        {
            "solids": {
                "start": {"config": {"throw_in_solid": False, "return_wrong_type": False}},
                "middle": {"config": {"throw_in_solid": False, "return_wrong_type": True}},
                "end": {"config": {"throw_in_solid": False, "return_wrong_type": False}},
            },
            "resources": {"errorable_resource": {"config": {"throw_on_resource_init": False}}},
        },
    )
