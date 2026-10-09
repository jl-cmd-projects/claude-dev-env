"""Command-line entry point for the jobs tool."""

import argparse
import json
import urllib.request
from pathlib import Path

from jobs.cleanup import remove_old_logs
from jobs.report import finished_jobs

JOBS_FILE = Path("jobs.json")


def main() -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(prog="jobs")
    all_commands = parser.add_subparsers(dest="command", required=True)
    all_commands.add_parser("list")
    report = all_commands.add_parser("report")
    report.add_argument("--days", type=int, default=7)
    cleanup = all_commands.add_parser("cleanup")
    cleanup.add_argument("folder", type=Path)
    cleanup.add_argument("--days", type=int, default=30)
    download = all_commands.add_parser("download")
    download.add_argument("url")
    download.add_argument("path", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "list":
        for each_job in json.loads(JOBS_FILE.read_text()):
            print(each_job["name"], each_job["status"])
    elif arguments.command == "report":
        for each_name, each_status, each_finish in finished_jobs(
            JOBS_FILE, arguments.days
        ):
            print(each_finish.date(), each_name, each_status)
    elif arguments.command == "cleanup":
        for each_path in remove_old_logs(arguments.folder, arguments.days):
            print("deleted", each_path)
    else:
        urllib.request.urlretrieve(arguments.url, arguments.path)


if __name__ == "__main__":
    main()
