"""Offline Markdown conversion and optional Notion block client."""

from .client import Client, NotionError, canonical
from .converter import Converter, block, rich_text

__all__ = ["Converter", "block", "rich_text", "Client", "NotionError", "canonical"]
__version__ = "0.1.0"
