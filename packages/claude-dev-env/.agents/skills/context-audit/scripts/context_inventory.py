"""Walk one checkout and record a row for each file an agent loads.

::

    audit_checkout(Path("repo"), None, None, ())
    -> [ContextRow(path="CLAUDE.md", kind=instructions, trigger=session-start, ...),
        ContextRow(path=".claude/rules/api.md", kind=rule, trigger=path-match, ...)]

Instruction files, rules, skills, saved hook text, linked docs, and module
docstrings each get rows. Links out of each text file are followed in turn.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from context_audit_constants.config import constants
from context_audit_constants.config.constants import CapKey, DepthMode, RowKind, Trigger
from context_sources import (
    ContextRow,
    RowSource,
    find_import_targets,
    find_relative_links,
    list_tracked_files,
    measure_row,
    parse_frontmatter,
    read_text,
)


@dataclass(frozen=True)
class SkillHome:
    """Where a skill folder sits and when its description loads."""

    location: str
    trigger: Trigger
    note: str


class ContextInventory:
    """Collect one row per loaded file through ``collect`` and return them."""

    def __init__(
        self, root: Path, rules_directory: Path | None, skills_directory: Path | None
    ) -> None:
        self.root = root.resolve()
        self.rules_directory = rules_directory
        self.skills_directory = skills_directory
        self.all_rows: list[ContextRow] = []
        self.all_seen_keys: set[tuple[str, RowKind]] = set()
        self.link_queue: deque[tuple[Path, str, int]] = deque()

    def collect(self, all_hook_text_files: tuple[Path, ...]) -> list[ContextRow]:
        """Return the rows for every loaded file in discovery order.

        Args:
            all_hook_text_files: Saved text a SessionStart hook prints.

        Returns:
            The inventory rows.
        """
        all_paths = list_tracked_files(self.root)
        self._add_instructions(all_paths)
        self._add_rules(all_paths)
        self._add_skills(all_paths)
        for each_hook_text_file in all_hook_text_files:
            self._add_hook_text(each_hook_text_file)
        self._follow_links()
        for each_path in all_paths:
            if each_path.suffix == constants.PYTHON_SUFFIX:
                self._add_docstring(each_path, constants.LOADER_DOCSTRING)
        return self.all_rows

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _add(
        self,
        path: Path,
        source: RowSource,
        cap_key: CapKey | None,
        text: str,
        link_depth: int = constants.FIRST_LINK_DEPTH,
    ) -> ContextRow | None:
        key = (source.path, source.kind)
        if key in self.all_seen_keys:
            return None
        self.all_seen_keys.add(key)
        is_markdown = path.suffix in constants.ALL_TEXT_SUFFIXES
        all_links = find_relative_links(path, text, self.root) if is_markdown else []
        cap = constants.ALL_LINE_CAP_BY_KEY[cap_key] if cap_key else None
        row = measure_row(source, text, cap, len(all_links))
        self.all_rows.append(row)
        for each_link in all_links:
            self.link_queue.append((each_link, row.path, link_depth))
        return row

    def _source(
        self, path: Path, kind: RowKind, loader: str, trigger: Trigger, note: str = ""
    ) -> RowSource:
        return RowSource(self._relative(path), kind, loader, trigger, note)

    def _add_instructions(self, all_paths: list[Path]) -> None:
        for each_path in sorted(all_paths):
            if each_path.name not in constants.ALL_INSTRUCTION_FILE_NAMES:
                continue
            folder = each_path.parent
            is_root = folder == self.root or (
                folder.name == constants.CLAUDE_FOLDER_NAME
                and folder.parent == self.root
            )
            trigger = Trigger.SESSION_START if is_root else Trigger.FOLDER_ENTER
            cap_key = (
                CapKey.ROOT_INSTRUCTIONS if is_root else CapKey.NESTED_INSTRUCTIONS
            )
            is_agents_file = each_path.name == constants.AGENTS_FILE_NAME
            note = constants.NOTE_CODEX_AGENTS if is_agents_file else ""
            loader = self._instruction_loader(each_path)
            source = self._source(
                each_path, RowKind.INSTRUCTIONS, loader, trigger, note
            )
            text = read_text(each_path)
            self._add(each_path, source, cap_key, text)
            self._add_imports(each_path, text, trigger, cap_key)

    def _instruction_loader(self, path: Path) -> str:
        if path.name != constants.AGENTS_FILE_NAME:
            return constants.LOADER_HARNESS
        sibling_claude = path.parent / constants.CLAUDE_FILE_NAME
        if not sibling_claude.exists():
            return constants.LOADER_AGENTS_NATIVE
        if constants.AGENTS_IMPORT_LINE in read_text(sibling_claude):
            return constants.LOADER_AGENTS_IMPORTED
        return constants.LOADER_AGENTS_SHADOWED

    def _add_imports(
        self, importer: Path, text: str, trigger: Trigger, cap_key: CapKey
    ) -> None:
        loader = constants.LOADER_IMPORT_TEMPLATE.format(
            source=self._relative(importer)
        )
        for each_import in find_import_targets(importer, text, self.root):
            if each_import.name in constants.ALL_INSTRUCTION_FILE_NAMES:
                continue
            source = self._source(
                each_import, RowKind.IMPORT, loader, trigger, constants.NOTE_IMPORT
            )
            imported_text = read_text(each_import)
            if self._add(each_import, source, cap_key, imported_text) is not None:
                self._add_imports(each_import, imported_text, trigger, cap_key)

    def _add_rules(self, all_paths: list[Path]) -> None:
        for each_path in all_paths:
            is_installed_rule = (
                self.rules_directory is not None
                and self.rules_directory in each_path.parents
            )
            if each_path.suffix != constants.MARKDOWN_SUFFIX or not (
                is_installed_rule or self._is_project_rule(each_path)
            ):
                continue
            text = read_text(each_path)
            is_path_scoped = constants.PATHS_FIELD in parse_frontmatter(text)
            loader = (
                constants.LOADER_RULE_INSTALLED
                if is_installed_rule
                else constants.LOADER_RULE_PROJECT
            )
            is_global = is_installed_rule and not is_path_scoped
            note = constants.NOTE_INSTALLED_RULE if is_global else ""
            trigger = Trigger.PATH_MATCH if is_path_scoped else Trigger.SESSION_START
            source = self._source(each_path, RowKind.RULE, loader, trigger, note)
            self._add(each_path, source, CapKey.RULE, text)

    def _is_project_rule(self, path: Path) -> bool:
        all_prefix_parts = constants.ALL_PROJECT_RULES_PATH_PARTS
        return (
            path.relative_to(self.root).parts[: len(all_prefix_parts)]
            == all_prefix_parts
        )

    def _skill_home(self, skill_path: Path) -> SkillHome | None:
        parts = skill_path.relative_to(self.root).parts
        if len(parts) < constants.MINIMUM_SKILL_PATH_PARTS or any(
            constants.ARCHIVE_FOLDER_MARKER in each_part
            or each_part in constants.ALL_FIXTURE_FOLDER_NAMES
            for each_part in parts
        ):
            return None
        if (
            self.skills_directory is not None
            and self.skills_directory in skill_path.parents
        ):
            return SkillHome(
                constants.LOCATION_INSTALLED_SKILLS, Trigger.SESSION_START, ""
            )
        return _folder_skill_home(parts)

    def _add_skills(self, all_paths: list[Path]) -> None:
        all_resolved_skill_paths: set[Path] = set()
        for each_path in sorted(all_paths):
            if each_path.name != constants.SKILL_FILE_NAME:
                continue
            resolved_path = each_path.resolve()
            home = self._skill_home(each_path)
            if home is None or resolved_path in all_resolved_skill_paths:
                continue
            all_resolved_skill_paths.add(resolved_path)
            text = read_text(each_path)
            self._add_skill_description(each_path, parse_frontmatter(text), home)
            source = self._source(
                each_path,
                RowKind.SKILL_BODY,
                constants.LOADER_SKILL_INVOCATION,
                Trigger.SKILL_INVOKE,
            )
            self._add(each_path, source, CapKey.SKILL_BODY, text)
            self._add_skill_references(each_path)

    def _add_skill_description(
        self, skill_path: Path, field_by_name: dict[str, str], home: SkillHome
    ) -> None:
        disable_text = field_by_name.get(constants.DISABLE_MODEL_INVOCATION_FIELD, "")
        if disable_text.lower() == constants.TRUE_TEXT:
            return
        full_size = _description_size(field_by_name)
        listed_size = min(full_size, constants.DESCRIPTION_LISTING_CHARACTER_LIMIT)
        is_truncated = full_size > constants.DESCRIPTION_LISTING_CHARACTER_LIMIT
        truncation_note = constants.NOTE_DESCRIPTION_TRUNCATED if is_truncated else ""
        is_over_cap = full_size > constants.DESCRIPTION_CHARACTER_CAP
        relative_path = self._relative(skill_path)
        self.all_seen_keys.add((relative_path, RowKind.SKILL_DESCRIPTION))
        self.all_rows.append(
            ContextRow(
                path=relative_path,
                kind=RowKind.SKILL_DESCRIPTION,
                loader=constants.LOADER_SKILL_LISTING_TEMPLATE.format(location=home.location),
                trigger=home.trigger,
                bytes=listed_size,
                lines=constants.DESCRIPTION_LINE_COUNT,
                est_tokens=round(listed_size / constants.BYTES_PER_ESTIMATED_TOKEN),
                links_out=0,
                depth_mode=DepthMode.CARRIES if is_over_cap else DepthMode.POINTS,
                cap=constants.DESCRIPTION_CHARACTER_CAP,
                note=constants.NOTE_SEPARATOR.join(
                    each_note for each_note in (home.note, truncation_note) if each_note
                ),
            )
        )

    def _add_skill_references(self, skill_path: Path) -> None:
        loader = constants.LOADER_SKILL_REFERENCE_TEMPLATE.format(
            source=self._relative(skill_path)
        )
        for each_other in sorted(skill_path.parent.rglob("*")):
            if (
                each_other.is_file()
                and each_other.name != constants.SKILL_FILE_NAME
                and each_other.suffix in constants.ALL_TEXT_SUFFIXES
                and not constants.ALL_SKIPPED_PATH_PARTS.intersection(each_other.parts)
            ):
                source = self._source(
                    each_other, RowKind.SKILL_REFERENCE, loader, Trigger.ON_LINK
                )
                self._add(each_other, source, None, read_text(each_other))

    def _add_hook_text(self, hook_text_file: Path) -> None:
        source = RowSource(
            hook_text_file.name,
            RowKind.HOOK_TEXT,
            constants.LOADER_HOOK_TEXT,
            Trigger.SESSION_START,
            constants.NOTE_HOOK_TEXT,
        )
        cap = constants.ALL_LINE_CAP_BY_KEY[CapKey.ROOT_INSTRUCTIONS]
        self.all_rows.append(measure_row(source, read_text(hook_text_file), cap, 0))

    def _follow_links(self) -> None:
        while self.link_queue:
            each_path, linked_from, depth = self.link_queue.popleft()
            if each_path.suffix == constants.PYTHON_SUFFIX:
                loader = constants.LOADER_LINKED_DOCSTRING_TEMPLATE.format(
                    source=linked_from
                )
                self._add_docstring(each_path, loader)
                continue
            if each_path.suffix not in constants.ALL_TEXT_SUFFIXES or self._is_recorded(
                each_path
            ):
                continue
            source = self._source(
                each_path,
                RowKind.LINKED_DOC,
                constants.LOADER_LINK_TEMPLATE.format(source=linked_from),
                Trigger.ON_LINK,
                constants.NOTE_LINK_DEPTH_TEMPLATE.format(depth=depth),
            )
            self._add(each_path, source, None, read_text(each_path), depth + 1)

    def _is_recorded(self, path: Path) -> bool:
        relative_path = self._relative(path)
        return any(each_key[0] == relative_path for each_key in self.all_seen_keys)

    def _add_docstring(self, path: Path, loader: str) -> None:
        try:
            tree = ast.parse(read_text(path))
        except (SyntaxError, ValueError):
            return
        docstring = ast.get_docstring(tree, clean=False)
        if docstring:
            source = self._source(path, RowKind.DOCSTRING, loader, Trigger.FILE_OPEN)
            self._add(path, source, CapKey.DOCSTRING, docstring)


def _folder_skill_home(all_parts: tuple[str, ...]) -> SkillHome | None:
    has_skills_folder = constants.SKILLS_FOLDER_NAME in all_parts
    if (
        all_parts[0] in constants.ALL_SKILL_HOME_FOLDER_NAMES
        and all_parts[1] == constants.SKILLS_FOLDER_NAME
    ):
        return SkillHome(constants.LOCATION_PROJECT_SKILLS, Trigger.SESSION_START, "")
    if constants.CLAUDE_FOLDER_NAME in all_parts and has_skills_folder:
        return SkillHome(constants.LOCATION_NESTED_SKILLS, Trigger.FOLDER_ENTER, "")
    if all_parts[0] == constants.PLUGINS_FOLDER_NAME and has_skills_folder:
        return SkillHome(
            constants.LOCATION_PLUGIN_SKILLS,
            Trigger.SESSION_START,
            constants.NOTE_PLUGIN_SKILL,
        )
    return None


def _description_size(field_by_name: dict[str, str]) -> int:
    description = constants.DESCRIPTION_JOIN_TEMPLATE.format(
        description=field_by_name.get(constants.DESCRIPTION_FIELD, ""),
        when_to_use=field_by_name.get(constants.WHEN_TO_USE_FIELD, ""),
    )
    return len(description.strip().encode(constants.TEXT_ENCODING))


def audit_checkout(
    root: Path,
    rules_directory: Path | None,
    skills_directory: Path | None,
    all_hook_text_files: tuple[Path, ...],
) -> list[ContextRow]:
    """Return one row for each file an agent loads from the checkout at *root*.

    Args:
        root: A git checkout.
        rules_directory: A tracked folder installed as the user rules folder.
        skills_directory: A tracked folder installed as the user skills folder.
        all_hook_text_files: Saved text a SessionStart hook prints.

    Returns:
        The inventory rows in discovery order.
    """
    inventory = ContextInventory(root, rules_directory, skills_directory)
    return inventory.collect(all_hook_text_files)
