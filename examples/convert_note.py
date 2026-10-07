"""Offline example. Run after installing the package."""

import json
from pathlib import Path

from markdown_notion_blocks import Converter

source = Path(__file__).with_name("sample.md")
converter = Converter("examples/sample.md")
print(json.dumps(converter.convert(source.read_text(encoding="utf-8")), indent=2))
