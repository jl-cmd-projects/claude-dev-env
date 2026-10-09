"""Command-line entry point for the jobs tool."""

import argparse
import json
import urllib.request
from pathlib import Path

from jobs.cleanup import remove_old_logs
from jobs.config.constants import DEFAULT_CLEANUP_DAYS, DEFAULT_REPORT_DAYS, JOBS_FILE
from jobs.report import finished_jobs


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jobs")
    all_commands = parser.add_subparsers(dest="command", required=True)
    all_commands.add_parser("list")
    report = all_commands.add_parser("report")
    report.add_argument("--days", type=int, default=DEFAULT_REPORT_DAYS)
    cleanup = all_commands.add_parser("cleanup")
    cleanup.add_argument("folder", type=Path)
    cleanup.add_argument("--days", type=int, default=DEFAULT_CLEANUP_DAYS)
    download = all_commands.add_parser("download")
    download.add_argument("url")
    download.add_argument("path", type=Path)
    return parser.parse_args()


def _list_jobs(arguments: argparse.Namespace) -> None:
    for each_job in json.loads(JOBS_FILE.read_text()):
        print(each_job["name"], each_job["status"])


def _report_jobs(arguments: argparse.Namespace) -> None:
    for each_name, each_status, each_finish in finished_jobs(JOBS_FILE, arguments.days):
        print(each_finish.date(), each_name, each_status)


def _clean_up_logs(arguments: argparse.Namespace) -> None:
    for each_path in remove_old_logs(arguments.folder, arguments.days):
        print("deleted", each_path)


def _download_artifact(arguments: argparse.Namespace) -> None:
    urllib.request.urlretrieve(arguments.url, arguments.path)


def main() -> None:
    """Parse the command line and run the chosen command."""
    arguments = _parse_arguments()
    command_by_name = {
        "list": _list_jobs,
        "report": _report_jobs,
        "cleanup": _clean_up_logs,
    }
    command_by_name.get(arguments.command, _download_artifact)(arguments)


if __name__ == "__main__":
    main()
