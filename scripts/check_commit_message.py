"""Require docs, bug, feat, or patch prefixes locally and in CI."""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("message_file", nargs="?")
    source.add_argument("--range", dest="revision_range")
    args = parser.parse_args()

    if args.revision_range:
        commits = subprocess.check_output(
            ["git", "log", "--format=%H%x00%s", args.revision_range, "--"],
            text=True, encoding="utf-8",
        )
        subjects = [line.split("\0", 1) for line in commits.splitlines()]
    else:
        message = Path(args.message_file).read_text(encoding="utf-8")
        subjects = [("Commit message", message.split("\n", 1)[0])]

    invalid = False
    for label, subject in subjects:
        if not re.fullmatch(r"(docs|bug|feat|patch): \S[^\r\n]*", subject):
            print(
                f"{label}: use docs|bug|feat|patch, a colon, one space, and a message. "
                "Example: docs: update README",
                file=sys.stderr,
            )
            invalid = True
    return int(invalid)


if __name__ == "__main__":
    sys.exit(main())
