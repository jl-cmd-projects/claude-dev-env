"""Parse skill defaults and arguments into one review request."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.config import efficient_review_constants as c


class ReviewRequestRunFatal(ValueError):
    """The /efficient-review arguments or defaults cannot make a review request."""


@dataclass(frozen=True)
class ReviewRequest:
    mode: str
    account: str | None
    model: str
    harness: str
    effort: str
    level: str
    base: str
    prompt: str
    advisor: str
    profile: str
    timeout_minutes: int


@dataclass
class ReviewArgumentSelection:
    mode: str | None
    account: str | None
    settings: dict[str, object]
    overridden_keys: set[str]


def load_defaults(defaults_path: Path = c.DEFAULTS_PATH) -> dict[str, object]:
    """Return skill defaults after checking that all required keys exist.

    Args:
        defaults_path: The JSON file containing the review skill defaults.

    Returns:
        The decoded defaults.

    Raises:
        ReviewRequestRunFatal: The file lacks one or more keys the skill reads.
    """
    all_defaults = json.loads(defaults_path.read_text(encoding=c.JSON_READ_ENCODING))
    all_missing = [each for each in c.ALL_DEFAULT_KEYS if each not in all_defaults]
    if all_missing:
        raise ReviewRequestRunFatal(
            f"{defaults_path} lacks {c.LIST_SEPARATOR.join(all_missing)}"
        )
    if all_defaults["mode"] not in c.ALL_MODE_WORDS:
        raise ReviewRequestRunFatal(
            f"{defaults_path} mode {all_defaults['mode']!r} is not headless or auto"
        )
    return all_defaults


def model_harness(model: str) -> str:
    """Return the harness that runs one model family.

    Args:
        model: A model family name such as haiku or luna.

    Returns:
        The Claude or Codex harness name.

    Raises:
        ReviewRequestRunFatal: The model is a versioned ID or an unknown family.
    """
    if model in c.ALL_CLAUDE_FAMILIES:
        return c.HARNESS_CLAUDE
    if model in c.ALL_CODEX_FAMILIES:
        return c.HARNESS_CODEX
    all_families = c.ALL_CLAUDE_FAMILIES + c.ALL_CODEX_FAMILIES
    raise ReviewRequestRunFatal(
        f"model {model!r} is not a family name; use one of "
        f"{c.LIST_SEPARATOR.join(all_families)}"
    )


def parse_request(
    all_arguments: Sequence[str], all_defaults: Mapping[str, object]
) -> ReviewRequest:
    """Return the request represented by one /efficient-review argument list.

    Args:
        all_arguments: Positional mode, account, and setting overrides.
        all_defaults: Defaults loaded from the review skill.

    Returns:
        The normalized review request.

    Raises:
        ReviewRequestRunFatal: The arguments conflict or name an unsupported model.
    """
    selection = _select_arguments(all_arguments, all_defaults)
    harness = _validate_selection(selection)
    return _build_request(selection, harness)


def _select_arguments(
    all_arguments: Sequence[str], all_defaults: Mapping[str, object]
) -> ReviewArgumentSelection:
    selection = ReviewArgumentSelection(
        mode=None,
        account=None,
        settings={each: all_defaults[each] for each in c.ALL_DEFAULT_KEYS},
        overridden_keys=set(),
    )
    for each_argument in all_arguments:
        _apply_argument(each_argument, selection)
    return selection


def _apply_argument(each_argument: str, selection: ReviewArgumentSelection) -> None:
    if c.OVERRIDE_SEPARATOR in each_argument:
        _apply_override(each_argument, selection)
        return
    if each_argument in c.ALL_MODE_WORDS:
        selection.mode = each_argument
        return
    if c.ACCOUNT_NAME_PATTERN.fullmatch(each_argument):
        _select_account(each_argument, selection)
        return
    raise ReviewRequestRunFatal(f"cannot read argument {each_argument!r}")


def _apply_override(each_argument: str, selection: ReviewArgumentSelection) -> None:
    key, override_text = each_argument.split(c.OVERRIDE_SEPARATOR, 1)
    if key not in c.ALL_OVERRIDE_KEYS:
        raise ReviewRequestRunFatal(
            f"unknown setting {key!r}; use {c.LIST_SEPARATOR.join(c.ALL_OVERRIDE_KEYS)}"
        )
    selection.settings[key] = override_text
    selection.overridden_keys.add(key)


def _select_account(account: str, selection: ReviewArgumentSelection) -> None:
    if selection.account is not None:
        raise ReviewRequestRunFatal(
            f"two accounts named: {selection.account}, {account}"
        )
    selection.account = account


def _validate_selection(selection: ReviewArgumentSelection) -> str:
    if selection.account is not None and selection.mode == c.MODE_AUTO:
        raise ReviewRequestRunFatal(
            "auto lets the broker pick the account; name no account"
        )
    if selection.account is not None:
        selection.mode = c.MODE_HEADLESS
    elif selection.mode is None:
        selection.mode = str(selection.settings["mode"])
    harness = model_harness(str(selection.settings["model"]))
    if harness == c.HARNESS_CODEX and c.LEVEL_KEY in selection.overridden_keys:
        raise ReviewRequestRunFatal(
            "codex review takes no level; drop level= for sol or luna"
        )
    return harness


def _build_request(selection: ReviewArgumentSelection, harness: str) -> ReviewRequest:
    settings = selection.settings
    level = str(settings["level"])
    base = str(settings["base"])
    return ReviewRequest(
        mode=str(selection.mode),
        account=selection.account,
        model=str(settings["model"]),
        harness=harness,
        effort=str(settings["effort"]),
        level=level,
        base=base,
        prompt=str(settings["prompt"]).format(level=level, base=base),
        advisor=str(settings["advisor"]),
        profile=str(settings["profile"]),
        timeout_minutes=int(str(settings["timeout_minutes"])),
    )
