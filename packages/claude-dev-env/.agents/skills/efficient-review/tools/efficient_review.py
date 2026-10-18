"""Plan one /efficient-review run from the installed skill."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TextIO

from tools.config import efficient_review_constants as c
from tools.efficient_review_plan import plan_review


def main(all_arguments: list[str], plan_stream: TextIO) -> int:
    """Print the runtime selection for one review.

    Args:
        all_arguments: Command-line arguments, without the program name.
        plan_stream: Where the plan JSON is written.

    Returns:
        Zero when the plan prints.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(c.PLAN_COMMAND)
    parser.parse_args(all_arguments)
    plan_stream.write(json.dumps(plan_review(os.environ), indent=c.JSON_INDENT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdout))
