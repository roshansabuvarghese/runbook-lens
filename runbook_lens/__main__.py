"""Run with python3 -m runbook_lens PATH."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .checker import scan_directory
from .impact import compare_directories
from .reporting import render_html, render_text


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check your own Markdown runbooks locally. No network or API key required."
    )
    parser.add_argument("directory", type=Path, help="Folder containing Markdown runbooks")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--format", choices=("text", "json", "html"), default="text")
    parser.add_argument("--output", type=Path, help="Write report to this file instead of stdout")
    parser.add_argument("--baseline", type=Path, help="Compare current documents against this earlier folder")
    parser.add_argument(
        "--fail-on", choices=("error", "warning", "none"), default="error",
        help="Exit 1 for errors (default), warnings or worse, or never for findings",
    )
    args = parser.parse_args(argv)
    try:
        result = scan_directory(args.directory)
        comparison = compare_directories(args.baseline, args.directory) if args.baseline else None
        if args.format == "json":
            payload = result.to_dict()
            if comparison is not None:
                payload["comparison"] = comparison.to_dict()
            report = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        elif args.format == "html":
            report = render_html(result, comparison)
        else:
            report = render_text(result, comparison)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
        else:
            sys.stdout.write(report)
    except (ValueError, OSError) as exc:
        print(f"Runbook Lens: {exc}", file=sys.stderr)
        return 2
    if args.fail_on == "none":
        return 0
    severities = {f.severity for f in result.findings}
    if "error" in severities or (args.fail_on == "warning" and "warning" in severities):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
