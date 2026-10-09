"""Behavioral tests for the artifact template pointer's path."""

from hooks_constants.artifact_template_pointer_constants import (
    ARTIFACT_TEMPLATE_PATH,
    HTML_PLAN_TEMPLATE_README_PATH,
)


def test_template_path_names_the_packaged_template_file() -> None:
    assert ARTIFACT_TEMPLATE_PATH.is_file()
    assert ARTIFACT_TEMPLATE_PATH.parent.joinpath("README.md").is_file()


def test_html_plan_readme_path_names_the_packaged_readme_and_house_stylesheet() -> None:
    assert HTML_PLAN_TEMPLATE_README_PATH.is_file()
    assert HTML_PLAN_TEMPLATE_README_PATH.parent.joinpath("house.css").is_file()
