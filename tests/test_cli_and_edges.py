import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from markdown_notion_blocks import Client, Converter, NotionError, canonical
from markdown_notion_blocks.cli import main


def test_cli_is_offline_and_emits_json(tmp_path, capsys):
    source = tmp_path / "note.md"
    source.write_text("# Example\n\nA paragraph.\n", encoding="utf-8")
    with patch("urllib.request.build_opener", side_effect=AssertionError("network forbidden")):
        assert main([str(source)]) == 0
    captured = capsys.readouterr()
    blocks = json.loads(captured.out)
    assert blocks[0]["type"] == "heading_1"
    assert blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == "A paragraph."


def test_unmapped_links_remain_text_and_mapped_links_resolve():
    converter = Converter("docs/a.md")
    nodes = converter.convert("[Missing](b.md)")
    assert "link" not in nodes[0]["paragraph"]["rich_text"][0]["text"]
    assert converter.warnings
    converter = Converter("docs/a.md", {"docs/b.md": "https://example.com/page"})
    assert converter.link("b.md") == "https://example.com/page"
    assert converter.link("../../outside.md") is None


def test_cli_rejects_bad_page_map_before_writing(tmp_path, capsys):
    source = tmp_path / "note.md"
    source.write_text("Example", encoding="utf-8")
    mapping = tmp_path / "map.json"
    mapping.write_text("[]", encoding="utf-8")
    destination = tmp_path / "output.json"
    assert main([str(source), "--page-map", str(mapping), "--output", str(destination)]) == 2
    assert not destination.exists()
    assert "page-map" in capsys.readouterr().err


def test_rich_text_boundaries_and_no_content_loss():
    content = "sample " * 900
    blocks = Converter("a.md").convert(content)
    text = "".join(span["text"]["content"] for span in blocks[0]["paragraph"]["rich_text"])
    assert text == content.rstrip()
    assert len(blocks[0]["paragraph"]["rich_text"]) > 1


def test_client_does_not_retry_ambiguous_write():
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError(
                "https://api.notion.com/v1/blocks/example/children", 503, "unavailable", {}, None
            )

    with (
        patch("urllib.request.build_opener", return_value=Opener()) as factory,
        patch("time.sleep"),
    ):
        with pytest.raises(NotionError, match="partial"):
            Client("synthetic-not-a-token", "2025-09-03").request(
                "PATCH", "/blocks/example/children", {}
            )
        assert factory.call_count == 1


def test_retry_after_is_not_shortened():
    class Opener:
        def open(self, *args, **kwargs):
            raise HTTPError(
                "https://api.notion.com/v1/blocks/example/children",
                429,
                "limited",
                {"Retry-After": "45"},
                None,
            )

    with (
        patch("urllib.request.build_opener", return_value=Opener()) as factory,
        patch("time.sleep") as sleep,
    ):
        with pytest.raises(NotionError):
            Client("synthetic-not-a-token", "2025-09-03").request(
                "PATCH", "/blocks/example/children", {}
            )
        assert factory.call_count == 5
        assert sum(call.args[0] == 45 for call in sleep.call_args_list) == 4


def test_canonical_comparison_preserves_style_and_text():
    one = Converter("a.md").convert("**bold**")
    other = Converter("a.md").convert("bold")
    assert canonical(one) != canonical(other)
