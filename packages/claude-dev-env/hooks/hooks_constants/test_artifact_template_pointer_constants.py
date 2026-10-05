"""Behavioral tests for the artifact template pointer's path."""

from hooks_constants.artifact_template_pointer_constants import ARTIFACT_TEMPLATE_PATH


def test_template_path_names_the_packaged_template_file() -> None:
    assert ARTIFACT_TEMPLATE_PATH.is_file()
    assert ARTIFACT_TEMPLATE_PATH.parent.joinpath("README.md").is_file()
