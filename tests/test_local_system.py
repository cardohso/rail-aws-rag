import importlib.util
from pathlib import Path

from rail_aws_rag.bedrock import TRANSIENT_ERRORS, error_code

PATH = Path(__file__).resolve().parents[1] / "eval" / "live" / "local_system.py"


def load():
    spec = importlib.util.spec_from_file_location("local_system", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_errors_carry_the_aws_error_code_like_botocore_errors():
    local = load()
    stderr = (
        "An error occurred (ThrottlingException) when calling the Converse operation: Too many "
        "requests"
    )
    error = local.CliError("boom", local.error_code_from(stderr))
    assert error_code(error) == "ThrottlingException"
    assert error_code(error) in TRANSIENT_ERRORS


def test_unrecognised_cli_output_gets_a_generic_code():
    assert load().error_code_from("Unable to locate credentials") == "CliError"
