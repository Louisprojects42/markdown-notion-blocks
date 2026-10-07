"""Export a single Markdown file to Notion block JSON without network access."""

import argparse
import json
import sys
from pathlib import Path

from .converter import Converter


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", help="Repository-relative source identity for resolving links")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--reference", default="main")
    parser.add_argument(
        "--page-map",
        type=Path,
        help="JSON object mapping relative document paths to destination URLs",
    )
    args = parser.parse_args(argv)
    try:
        pages = json.loads(args.page_map.read_text(encoding="utf-8")) if args.page_map else {}
        if not isinstance(pages, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in pages.items()
        ):
            raise ValueError("page-map must be an object of string paths and URLs")
        converter = Converter(
            args.source or args.input.name, pages, args.repository_url, args.reference
        )
        blocks = converter.convert(
            args.input.read_text(encoding="utf-8-sig"), args.input.suffix.lstrip(".").lower()
        )
        output = json.dumps(blocks, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        for warning in converter.warnings:
            print("Warning: " + warning, file=sys.stderr)
        return 0
    except (OSError, ValueError) as error:
        print("Conversion failed: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
