import re
from uuid import UUID

import pytest
import yaml

from prefect.infrastructure.kubernetes import KubernetesJob
from prefect.infrastructure.submission import _prepare_infrastructure
from prefect.orion.schemas.core import FlowRun
from prefect.testing.cli import invoke_and_assert


@pytest.fixture
def example_deployments(tests_dir):
    return tests_dir / "deployments" / "examples"


def test_preview_error_messaging_with_deployments(example_deployments):
    """If there are no deployments at all in the file, warn the user"""
    invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "single_flow_in_file.py"),
        ],
        expected_code=1,
        expected_output_contains="No deployments found!",
    )


def test_preview_multiple_deployments(example_deployments):
    """If there are multiple deployments in the file, they are all rendered"""
    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "multiple_kubernetes_deployments.py"),
        ],
        expected_output_contains="kind: Job",
    )
    assert "Preview for 'hello-world-daily'" in result.stdout
    assert "Preview for 'hello-world-weekly'" in result.stdout


def test_preview_works_for_unnamed_deployments(example_deployments):
    """Even if the deployments are unnamed, we can still get a preview for a single
    one"""
    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "unnamed_kubernetes_deployment.py"),
        ],
        expected_output_contains="kind: Job",
    )
    assert "Preview for <unnamed deployment>" in result.stdout


def test_previewing_single_kubernetes_deployment_from_python(example_deployments):
    """`prefect deployment preview my-flow-file.py` should render a single
    Kubernetes Job that will be applied to the cluster"""

    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "single_kubernetes_deployment.py"),
        ],
        expected_output_contains="kind: Job",
    )
    assert result.stdout.endswith("\n")

    previews = [p.strip() for p in re.split("Preview for .+:", result.stdout) if p]
    assert len(previews) == 1

    manifest = yaml.load(previews[0], yaml.SafeLoader)
    assert (
        manifest
        == _prepare_infrastructure(
            FlowRun(
                id=UUID(int=0),
                flow_id=UUID(int=0),
                name="cool-name",
            ),
            KubernetesJob(),
        ).build_job()
    )


def test_previewing_multiple_kubernetes_deployments_from_python(example_deployments):
    """`prefect deployment preview my-flow-file.py` should render multiple
    Kubernetes Jobs from a deployment file"""

    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "multiple_kubernetes_deployments.py"),
        ],
        expected_output_contains="kind: Job",
    )
    assert result.stdout.endswith("\n")

    previews = [p.strip() for p in re.split("Preview for .+:", result.stdout) if p]
    assert len(previews) == 4  # there should be 3 K8s and 1 non-K8s in the file

    # spot-check a few attributes of the first one
    manifest = yaml.load(previews[0], yaml.SafeLoader)
    assert manifest["apiVersion"] == "batch/v1"
    assert manifest["kind"] == "Job"
    assert manifest["metadata"]["generateName"] == "cool-name"

    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert "PREFECT_TEST_MODE" in [variable["name"] for variable in container["env"]]

    # spot-check a few attributes of the third one, which is customized
    manifest = yaml.load(previews[2], yaml.SafeLoader)
    assert manifest["apiVersion"] == "batch/v1"
    assert manifest["kind"] == "Job"
    assert manifest["metadata"]["generateName"] == "cool-name"

    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert "MY_ENV_VAR" in [variable["name"] for variable in container["env"]]


def test_previewing_docker_deployment(example_deployments):
    """`prefect deployment preview my-flow-file.py` should render the
    Docker API values for the container it will create"""

    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "single_docker_deployment.py"),
        ],
        expected_output_contains="prefect.engine",
    )
    assert result.stdout.endswith("\n")

    preview = result.stdout.strip()

    # TODO: this is an unsophisticated JSON representation and can be much better,
    # perhaps translated into a shell command like the SubprocessFlowRunner

    # spot-check some variables and the command-line
    assert "PREFECT_TEST_MODE" in preview
    assert "PREFECT_LOGGING_LEVEL" in preview
    assert "PREFECT__FLOW_RUN_ID" in preview
    assert '["python", "-m", "prefect.engine"]' in preview


def test_previewing_process_deployment(example_deployments):
    """`prefect deployment preview my-flow-file.py` should render the
    shell command that will be run for the subprocess"""

    result = invoke_and_assert(
        [
            "deployment",
            "preview",
            str(example_deployments / "single_subprocess_deployment.py"),
        ],
        expected_output_contains="prefect.engine",
    )
    assert result.stdout.endswith("\n")

    preview = result.stdout.strip()

    # spot-check some variables and the command-line
    assert "\nPREFECT_TEST_MODE=True \\" in preview
    assert "\nPREFECT_LOGGING_LEVEL=DEBUG \\" in preview
    assert "\nPREFECT__FLOW_RUN_ID=00000000000000000000000000000000 \\" in preview
    assert preview.endswith(" -m prefect.engine")