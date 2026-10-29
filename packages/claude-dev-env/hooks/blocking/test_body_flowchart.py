"""Behavior tests for the mermaid flowchart reader of a pull request description section."""

import sys
from pathlib import Path

import pytest

HOOKS_DIRECTORY = Path(__file__).resolve().parent.parent
if str(HOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIRECTORY))

from blocking.body_flowchart import section_has_flowchart


def _block(*all_lines: str, fence: str = "```") -> str:
    return "\n".join([f"{fence}mermaid", *all_lines, fence])


@pytest.mark.parametrize(
    "block",
    [
        _block("flowchart LR", "    a --> b"),
        _block("flowchart TD", "    a[Start] -->|yes| b[End]"),
        _block("flowchart LR", "    a --> b --> c"),
        _block("flowchart LR", "    a --- b"),
        _block("flowchart LR", "    a -.-> b"),
        _block("flowchart LR", "    a ==> b"),
        _block("flowchart LR; a --> b"),
        "````mermaid\nflowchart LR\n    a --> b\n`````",
        _block("---", "title: Flow", "---", "flowchart LR", "    a --> b"),
        "1. Flow:\n\n    ```mermaid\n    flowchart LR\n    a --> b\n    ```",
        "```js```\n\n" + _block("flowchart LR", "    a --> b"),
        _block("flowchart LR", "    a === b"),
        _block("flowchart LR", "    a -.- b"),
        _block("flowchart LR", "    a -..-> b"),
        _block("flowchart LR", '    a["run --output x"] --> b[End]'),
        _block("flowchart LR", "    subgraph one", "        a --> b", "    end"),
        _block("%% a note", "flowchart LR", "", "    a --> b"),
        _block("flowchart LR", "    a --> b", fence="~~~"),
        "Before the chart.\n\n" + _block("flowchart LR", "    a --> b") + "\n\nAfter it.",
    ],
)
def should_accept_a_closed_mermaid_flowchart_with_an_arrow(block: str) -> None:
    assert section_has_flowchart(block)


@pytest.mark.parametrize(
    "section",
    [
        "",
        "Plain sentences and no chart.",
        _block("sequenceDiagram", "    a->>b: hi"),
        _block("graph LR", "    a --> b"),
        _block("classDiagram", "    a --> b"),
        _block("flowchart LR"),
        _block("---", "title: Flow", "---"),
        _block("---", "flowchart LR", "    a --> b"),
        _block("flowchart LR", "    a %% --> b"),
        _block("flowchart LR", "    only_node"),
        _block("flowchart LR", "    a", "    b"),
        _block("flowchart LR", "    a --> "),
        _block("flowchart LR", "    a -->|label|"),
        _block("flowchart LR", '    a["run --output x"]'),
        _block("flowchart LR", "    a[Start --> End]"),
        _block("a --> b", "flowchart LR"),
        "```text\nflowchart LR\n    a --> b\n```",
        "```mermaid\nflowchart LR\n    a --> b",
        "````text\n```mermaid\nflowchart LR\n    a --> b\n```\n````",
    ],
)
def should_reject_a_section_without_a_closed_mermaid_flowchart_edge(section: str) -> None:
    assert not section_has_flowchart(section)


def should_find_a_flowchart_after_a_block_of_another_diagram_type() -> None:
    section = (
        _block("sequenceDiagram", "    a->>b: hi") + "\n\n" + _block("flowchart LR", "    a --> b")
    )
    assert section_has_flowchart(section)
