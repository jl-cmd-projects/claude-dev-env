"""Tests for restore_dev_null — SessionStart hook that restores the /dev/null device node."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import restore_dev_null as restore


POSIX_DEVICE_NUMBERS_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="device numbers come from POSIX os.makedev and os.major",
)


def _char_device_status(major: int, minor: int) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=stat.S_IFCHR | 0o666,
        st_rdev=os.makedev(major, minor),
    )


def _regular_file_status() -> SimpleNamespace:
    return SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_rdev=0)


def _completed_mknod(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")


class TestIsDevNullDevice:
    @POSIX_DEVICE_NUMBERS_ONLY
    def test_character_device_1_3_is_healthy(self) -> None:
        assert restore.is_dev_null_device(
            "/unused", read_status=lambda _path: _char_device_status(1, 3)
        )

    @POSIX_DEVICE_NUMBERS_ONLY
    def test_character_device_with_other_numbers_is_unhealthy(self) -> None:
        assert not restore.is_dev_null_device(
            "/unused", read_status=lambda _path: _char_device_status(1, 5)
        )

    def test_regular_file_is_unhealthy(self) -> None:
        assert not restore.is_dev_null_device(
            "/unused", read_status=lambda _path: _regular_file_status()
        )

    def test_missing_path_is_unhealthy(self) -> None:
        def missing(_path: str) -> SimpleNamespace:
            raise FileNotFoundError(_path)

        assert not restore.is_dev_null_device("/unused", read_status=missing)


class TestRestoreDevNull:
    @POSIX_DEVICE_NUMBERS_ONLY
    def test_healthy_path_runs_no_mknod(self, tmp_path: Path) -> None:
        device_path = tmp_path / "null"
        with patch.object(restore.subprocess, "run") as run_mock:
            result_line = restore.restore_dev_null(
                str(device_path),
                read_status=lambda _path: _char_device_status(1, 3),
            )
        run_mock.assert_not_called()
        assert "no change" in result_line

    def test_missing_path_runs_mknod_with_expected_arguments(self, tmp_path: Path) -> None:
        device_path = tmp_path / "null"
        with patch.object(restore.subprocess, "run", side_effect=_completed_mknod) as run_mock:
            result_line = restore.restore_dev_null(str(device_path))
        run_mock.assert_called_once()
        called_argv = run_mock.call_args.args[0]
        assert called_argv == ["mknod", "-m", "666", str(device_path), "c", "1", "3"]
        assert result_line == f"restored {device_path} as character device 1:3."

    def test_clobbered_regular_file_is_removed_before_mknod(self, tmp_path: Path) -> None:
        device_path = tmp_path / "null"
        device_path.write_text("clobbered", encoding="utf-8")
        existed_at_mknod_call: list[bool] = []

        def record_then_complete(
            argv: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            existed_at_mknod_call.append(os.path.lexists(device_path))
            return _completed_mknod(argv, **kwargs)

        with patch.object(restore.subprocess, "run", side_effect=record_then_complete):
            restore.restore_dev_null(str(device_path))
        assert existed_at_mknod_call == [False]

    def test_symlink_at_path_is_replaced_and_target_is_kept(self, tmp_path: Path) -> None:
        target_path = tmp_path / "target"
        target_path.write_text("keep", encoding="utf-8")
        device_path = tmp_path / "null"
        device_path.symlink_to(target_path)
        with patch.object(restore.subprocess, "run", side_effect=_completed_mknod) as run_mock:
            restore.restore_dev_null(str(device_path))
        run_mock.assert_called_once()
        assert not os.path.islink(device_path)
        assert target_path.read_text(encoding="utf-8") == "keep"

    def test_mknod_failure_returns_stderr_without_raising(self, tmp_path: Path) -> None:
        device_path = tmp_path / "null"
        failure = subprocess.CalledProcessError(
            1,
            ["mknod"],
            stderr=b"mknod: /dev/null: Operation not permitted",
        )
        with patch.object(restore.subprocess, "run", side_effect=failure):
            result_line = restore.restore_dev_null(str(device_path))
        assert result_line == (
            f"could not restore {device_path}: mknod: /dev/null: Operation not permitted"
        )

    def test_missing_mknod_binary_returns_message_without_raising(self, tmp_path: Path) -> None:
        device_path = tmp_path / "null"
        with patch.object(restore.subprocess, "run", side_effect=FileNotFoundError("mknod")):
            result_line = restore.restore_dev_null(str(device_path))
        assert result_line.startswith(f"could not restore {device_path}:")


class TestMain:
    def test_main_prints_the_restore_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch.object(restore.sys, "platform", "linux"),
            patch.object(restore, "restore_dev_null", return_value="sample line"),
        ):
            restore.main()
        assert capsys.readouterr().out == "sample line\n"

    @pytest.mark.parametrize("non_linux_platform", ["win32", "darwin"])
    def test_main_prints_skip_line_off_linux(
        self, capsys: pytest.CaptureFixture[str], non_linux_platform: str
    ) -> None:
        with (
            patch.object(restore.sys, "platform", non_linux_platform),
            patch.object(restore, "restore_dev_null") as restore_mock,
        ):
            restore.main()
        restore_mock.assert_not_called()
        assert capsys.readouterr().out == restore.NON_LINUX_SKIP_LINE + "\n"
