"""Behavioral tests for the artifact current page gate's patterns, paths and messages."""

from hooks_constants.artifact_current_page_gate_constants import (
    ARTIFACT_LINK_PATTERN,
    LINK_META_PATTERN,
    PAGE_TITLE_PATTERN,
    REPEAT_RENDERER_SCRIPT_PATH,
    REPEATED_ITEM_LINE_TEMPLATE,
    SECOND_LINK_REASON_TEMPLATE,
)


def test_renderer_path_names_the_packaged_render_script() -> None:
    assert REPEAT_RENDERER_SCRIPT_PATH.is_file()
    assert REPEAT_RENDERER_SCRIPT_PATH.name == "artifact_repeated_item_render.cjs"


def test_link_pattern_matches_both_artifact_link_shapes_and_no_other_page() -> None:
    assert ARTIFACT_LINK_PATTERN.search("see https://claude.ai/artifact/Ab12Cd34 now").group(0) == (
        "https://claude.ai/artifact/Ab12Cd34"
    )
    assert ARTIFACT_LINK_PATTERN.search("https://claude.ai/code/artifact/0e557edc-f0c7.").group(
        0
    ) == ("https://claude.ai/code/artifact/0e557edc-f0c7")
    assert ARTIFACT_LINK_PATTERN.search("https://claude.ai/code/session_01") is None


def test_meta_pattern_reads_the_link_a_page_records() -> None:
    link_meta = '<meta name="artifact-link" content="https://claude.ai/artifact/Ab12Cd34">'
    assert LINK_META_PATTERN.search(link_meta).group(1) == "https://claude.ai/artifact/Ab12Cd34"
    assert LINK_META_PATTERN.search('<meta name="viewport" content="width=device-width">') is None


def test_title_pattern_reads_a_title_that_spans_lines() -> None:
    assert PAGE_TITLE_PATTERN.search("<title>\nSample Run\n</title>").group(1).strip() == (
        "Sample Run"
    )


def test_messages_name_the_item_the_count_and_the_link() -> None:
    assert REPEATED_ITEM_LINE_TEMPLATE.format(item="screens/home.png", times=3) == (
        "- screens/home.png is drawn 3 times\n"
    )
    assert "https://claude.ai/artifact/Ab12Cd34" in SECOND_LINK_REASON_TEMPLATE.format(
        link="https://claude.ai/artifact/Ab12Cd34"
    )
