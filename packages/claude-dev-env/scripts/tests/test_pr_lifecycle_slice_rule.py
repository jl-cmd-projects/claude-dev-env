"""The pr-lifecycle skill points at the slice rule, and the reference carries the four tests, the size bar, and the retro-split steps."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIRECTORY = PACKAGE_ROOT / ".agents" / "skills" / "pr-lifecycle"
PR_LIFECYCLE_PATH = SKILL_DIRECTORY / "SKILL.md"
SLICE_REFERENCE_PATH = SKILL_DIRECTORY / "reference" / "split-a-pull-request.md"


def _decision_tree(skill_text: str) -> str:
    return skill_text.split("### Workflow decision tree", 1)[1].split("\n### ", 1)[0]


def test_the_decision_tree_points_at_the_slice_reference() -> None:
    decision_tree = _decision_tree(PR_LIFECYCLE_PATH.read_text(encoding="utf-8"))
    assert "(reference/split-a-pull-request.md)" in decision_tree
    assert "how large a pull request may be" in decision_tree


def test_the_reference_lists_the_four_slice_tests_in_order() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    all_test_markers = (
        "1. It merges alone and leaves the trunk working.",
        "2. It has its own proof: a test or command that fails without the slice and passes with it.",
        "3. It reverts alone.",
        "4. One sentence states its purpose, and a reviewer can judge it without reading later levels.",
    )
    all_positions = [
        reference_text.index(each_marker) for each_marker in all_test_markers
    ]
    assert all_positions == sorted(all_positions)
    assert "A slice that needs two sentences is usually two slices." in reference_text


def test_the_reference_merges_cosmetic_cuts_back_and_allows_one_pull_request() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    assert (
        "A cut by folder, file count, or line cap that fails these tests is cosmetic. Merge it back."
        in reference_text
    )
    assert (
        "Fewer slices is a valid answer, and so is one pull request with a stated reason."
        in reference_text
    )


def test_the_reference_says_when_to_split_and_what_to_try_first() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    assert "the change carries more than one purpose" in reference_text
    assert (
        "Isolate the part that switches the behaviour on, so its revert is small."
        in reference_text
    )
    assert "`linguist-generated`" in reference_text
    assert "Decide the slices when you write the plan." in reference_text


def test_the_retro_split_pins_the_head_and_posts_the_plan_before_building() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    assert "## Split a pull request that is already open" in reference_text
    assert "Pin the head SHA" in reference_text
    assert (
        "Never rewrite or push to a branch another session or person owns."
        in reference_text
    )
    assert "map each open finding to the slice it lands in" in reference_text
    plan_position = reference_text.index("get the owner's go before you build")
    no_code_position = reference_text.index("Change no code during the split.")
    assert plan_position < no_code_position


def test_the_retro_split_keeps_the_tree_and_names_the_approvals_each_slice_needs() -> (
    None
):
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    assert "`git diff <pinned-sha> <tip> --stat` prints nothing" in reference_text
    assert "Approvals do not carry over" in reference_text
    assert "links the original pull request" in reference_text


def test_the_retro_split_links_the_stack_level_proof_and_does_not_copy_it() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    assert "(../SKILL.md#each-stack-level-stands-on-its-own)" in reference_text
    assert "A symbol belongs at the level that first" not in reference_text
    assert "CI runs only on the stack tip" in reference_text


def test_the_reference_sets_a_size_bar_after_the_four_tests() -> None:
    reference_text = SLICE_REFERENCE_PATH.read_text(encoding="utf-8")
    fourth_test_position = reference_text.index("4. One sentence states its purpose")
    size_bar_position = reference_text.index("## Size bar")
    assert fourth_test_position < size_bar_position
    retro_split_position = reference_text.index(
        "## Split a pull request that is already open"
    )
    assert size_bar_position < retro_split_position
    size_bar = reference_text[size_bar_position:retro_split_position]
    all_required_phrases = (
        "Apply the bar to each pull request, including each stack level.",
        "A renamed or moved file counts only its edited lines.",
        "Every cut still passes the four tests.",
        "Count added plus deleted lines, tests included, without lockfiles",
        "without files marked `linguist-generated`",
        "Up to 400 lines fits one review, and about 100 lines reads best.",
        "Over 400 lines, look for another seam that passes the four tests.",
        "When none passes, keep the slice whole and state the reason in the pull request body.",
        "Over 1,000 lines, put that reason under a `## Why one pull request` heading.",
        "google.github.io/eng-practices/review/developer/small-cls.html",
        "smartbear.com/learn/code-review/best-practices-for-peer-code-review",
    )
    for each_phrase in all_required_phrases:
        assert each_phrase in size_bar
