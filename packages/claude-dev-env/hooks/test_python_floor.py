"""The package's Python floor holds for the hooks, their checkers, and the install prose.

The floor is the ``requires-python`` bound in the package ``pyproject.toml``. Every
other statement of it must name the same version, and every hook module must parse
under that version's grammar, so a hook that cannot start on the floor fails here.
"""

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

HOOKS_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = HOOKS_ROOT.parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent.parent
PACKAGE_PYPROJECT = PACKAGE_ROOT / "pyproject.toml"
HOOKS_PYPROJECT = HOOKS_ROOT / "pyproject.toml"
ALL_SHARED_MYPY_PYPROJECTS = (
    PACKAGE_ROOT / "_shared" / "pr-loop" / "scripts" / "pyproject.toml",
    PACKAGE_ROOT / "_shared" / "process-tree" / "scripts" / "pyproject.toml",
)
README_PATH = REPOSITORY_ROOT / "README.md"
INSTALL_PLAN_PATH = PACKAGE_ROOT / "bin" / "install-plan.mjs"
PYTHON_PROBE_PATH = PACKAGE_ROOT / "bin" / "python-probe.mjs"

REQUIRES_PYTHON_PATTERN = re.compile(r"^>=\s*(\d+)\.(\d+)$")
README_FLOOR_PATTERN = re.compile(r"Python (\d+)\.(\d+)\+")
INSTALLER_FLOOR_PATTERN = re.compile(r"MINIMUM_PYTHON_VERSION = '(\d+)\.(\d+)'")
INSTALLER_MESSAGE_FLOOR_REFERENCE = "Install Python ${MINIMUM_PYTHON_VERSION}+"

TYPE_PARAMETER_SOURCE = "def first[T](all_items: list[T]) -> T:\n    return all_items[0]\n"
NESTED_QUOTE_FSTRING_SOURCE = (
    'all_names = ["first", "second"]\njoined_names = f"{", ".join(all_names)}"\n'
)
NEWER_TARGET_VERSION = "py312"


def _read_toml(toml_path: Path) -> dict:
    with toml_path.open("rb") as toml_file:
        return tomllib.load(toml_file)


def _package_floor() -> tuple[int, int]:
    requires_python = _read_toml(PACKAGE_PYPROJECT)["project"]["requires-python"]
    floor_match = REQUIRES_PYTHON_PATTERN.match(requires_python.strip())
    assert floor_match, f"requires-python must read '>=X.Y', found {requires_python!r}"
    return int(floor_match.group(1)), int(floor_match.group(2))


def _floor_text(floor: tuple[int, int]) -> str:
    return f"{floor[0]}.{floor[1]}"


def _ruff_excluded_entries() -> list[str]:
    return list(_read_toml(HOOKS_PYPROJECT)["tool"]["ruff"]["extend-exclude"])


def _is_excluded(relative_path: Path, all_excluded_entries: list[str]) -> bool:
    relative_text = relative_path.as_posix()
    return any(
        relative_text.startswith(each_entry + "/") or each_entry in relative_path.parts
        for each_entry in all_excluded_entries
    )


def _all_hook_modules() -> list[Path]:
    all_excluded_entries = _ruff_excluded_entries()
    return sorted(
        each_path
        for each_path in HOOKS_ROOT.rglob("*.py")
        if not _is_excluded(each_path.relative_to(HOOKS_ROOT), all_excluded_entries)
    )


def _parse_at_floor(source: str, source_name: str, floor: tuple[int, int]) -> None:
    ast.parse(source, filename=source_name, feature_version=floor)


def _floor_parse_failures(
    all_module_paths: list[Path], modules_root: Path, floor: tuple[int, int]
) -> list[str]:
    all_failures: list[str] = []
    for each_path in all_module_paths:
        try:
            _parse_at_floor(each_path.read_text(encoding="utf-8"), str(each_path), floor)
        except SyntaxError as parse_error:
            relative_path = each_path.relative_to(modules_root).as_posix()
            all_failures.append(f"{relative_path}:{parse_error.lineno}: {parse_error.msg}")
    return all_failures


def _run_ruff_on(
    module_path: Path, all_extra_arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--config",
            str(HOOKS_PYPROJECT),
            *all_extra_arguments,
            str(module_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_hooks_ruff_target_should_equal_the_package_floor() -> None:
    floor = _package_floor()
    ruff_target = _read_toml(HOOKS_PYPROJECT)["tool"]["ruff"]["target-version"]
    assert ruff_target == f"py{floor[0]}{floor[1]}"


@pytest.mark.parametrize(
    "mypy_pyproject",
    [HOOKS_PYPROJECT, *ALL_SHARED_MYPY_PYPROJECTS],
    ids=lambda each_path: each_path.parent.relative_to(PACKAGE_ROOT).as_posix(),
)
def test_mypy_python_version_should_equal_the_package_floor(mypy_pyproject: Path) -> None:
    mypy_version = _read_toml(mypy_pyproject)["tool"]["mypy"]["python_version"]
    assert mypy_version == _floor_text(_package_floor())


def test_every_hook_module_should_parse_at_the_package_floor() -> None:
    all_module_paths = _all_hook_modules()
    assert all_module_paths
    all_failures = _floor_parse_failures(all_module_paths, HOOKS_ROOT, _package_floor())
    assert not all_failures, "\n".join(all_failures)


def test_floor_parse_should_reject_a_type_parameter_list() -> None:
    with pytest.raises(SyntaxError):
        _parse_at_floor(TYPE_PARAMETER_SOURCE, "planted_type_parameters.py", _package_floor())


def test_floor_parse_should_name_the_file_and_line_of_a_newer_module(tmp_path: Path) -> None:
    planted_module = tmp_path / "planted_type_parameters.py"
    planted_module.write_text("import os\n\n" + TYPE_PARAMETER_SOURCE, encoding="utf-8")
    all_failures = _floor_parse_failures([planted_module], tmp_path, _package_floor())
    assert len(all_failures) == 1
    assert all_failures[0].startswith("planted_type_parameters.py:3: ")


def test_hooks_ruff_config_should_reject_a_nested_quote_fstring(tmp_path: Path) -> None:
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("the ruff module is not installed")
    planted_module = tmp_path / "planted_nested_quote_fstring.py"
    planted_module.write_text(NESTED_QUOTE_FSTRING_SOURCE, encoding="utf-8")
    newer_target_run = _run_ruff_on(planted_module, ["--target-version", NEWER_TARGET_VERSION])
    assert newer_target_run.returncode == 0, newer_target_run.stdout + newer_target_run.stderr
    floor_run = _run_ruff_on(planted_module, [])
    assert floor_run.returncode != 0
    assert "syntax was added in Python 3.12" in floor_run.stdout + floor_run.stderr


def test_hooks_should_compile_under_the_floor_interpreter(tmp_path: Path) -> None:
    floor_interpreter = shutil.which(f"python{_floor_text(_package_floor())}")
    if floor_interpreter is None:
        pytest.skip("no interpreter for the floor version on PATH")
    compile_environment = {**os.environ, "PYTHONPYCACHEPREFIX": str(tmp_path)}
    compile_run = subprocess.run(
        [floor_interpreter, "-m", "compileall", "-q", str(HOOKS_ROOT)],
        capture_output=True,
        text=True,
        check=False,
        env=compile_environment,
    )
    assert compile_run.returncode == 0, compile_run.stdout + compile_run.stderr


def test_readme_should_name_the_package_floor() -> None:
    all_readme_floors = README_FLOOR_PATTERN.findall(README_PATH.read_text(encoding="utf-8"))
    assert all_readme_floors
    floor = _package_floor()
    assert {(int(major), int(minor)) for major, minor in all_readme_floors} == {floor}


def test_installer_should_name_the_package_floor() -> None:
    python_probe_source = PYTHON_PROBE_PATH.read_text(encoding="utf-8")
    installer_floor_match = INSTALLER_FLOOR_PATTERN.search(python_probe_source)
    assert installer_floor_match, "python-probe.mjs must export MINIMUM_PYTHON_VERSION"
    install_plan_source = INSTALL_PLAN_PATH.read_text(encoding="utf-8")
    installer_floor = (int(installer_floor_match.group(1)), int(installer_floor_match.group(2)))
    assert installer_floor == _package_floor()
    assert INSTALLER_MESSAGE_FLOOR_REFERENCE in install_plan_source
