import copy

from markdown_notion_blocks import Client, Converter, block, canonical, rich_text


class FakeNotion(Client):
    """In-memory block endpoint only; never connects to a workspace."""

    def __init__(self):
        self.counter = 0
        self.blocks = {}
        self.child_ids = {}
        self.requests = []

    def new_id(self):
        self.counter += 1
        return f"id-{self.counter}"

    def children(self, parent):
        return [copy.deepcopy(self.blocks[i]) for i in self.child_ids.get(parent, [])]

    def add_block(self, parent, data):
        value = copy.deepcopy(data)
        children = value[value["type"]].pop("children", [])
        value["id"] = self.new_id()
        value["has_children"] = bool(children)
        self.blocks[value["id"]] = value
        self.child_ids.setdefault(parent, []).append(value["id"])
        if parent in self.blocks:
            self.blocks[parent]["has_children"] = True
        for child in children:
            self.add_block(value["id"], child)
        return copy.deepcopy(value)

    def request(self, method, path, payload=None):
        self.requests.append((method, path, copy.deepcopy(payload)))
        if method == "PATCH" and path.startswith("/blocks/"):
            parent = path.split("/")[2]
            return {"results": [self.add_block(parent, item) for item in payload["children"]]}
        raise AssertionError((method, path))


def test_readback_normalizes_span_merging_without_hiding_content_changes():
    sent = [block("paragraph", rich=rich_text("a") + rich_text("\nb") + rich_text(""))]
    merged = [block("paragraph", rich=rich_text("a\nb"))]
    assert canonical(sent) == canonical(merged)
    assert canonical(sent) != canonical([block("paragraph", text="a b")])
    styled = copy.deepcopy(merged)
    styled[0]["paragraph"]["rich_text"][0]["annotations"] = {"bold": True}
    assert canonical(sent) != canonical(styled)
    assert canonical(sent) != canonical(
        [block("paragraph", rich=rich_text("a\nb", url="https://example.com"))]
    )


def test_converter_preserves_structured_notes():
    converter = Converter("docs/a.md", {"docs/b.md": "https://www.notion.so/b"})
    nodes = converter.convert(
        "# Heading\n\n**Strong** [other](b.md) and \\(x=y^2\\).\n\n"
        "- [x] task\n  - nested\n\n> quote\n\n"
        "| Name | Value |\n|---|---|\n| count | 8 |\n\n"
        '```python\nprint("exact")\n```\n\n\\[z=a+b\\]\n'
    )
    assert {n["type"] for n in nodes} >= {
        "heading_1",
        "paragraph",
        "to_do",
        "quote",
        "table",
        "code",
        "equation",
    }
    task = next(n for n in nodes if n["type"] == "to_do")
    assert task["to_do"]["checked"] is True
    assert task["to_do"]["children"][0]["type"] == "bulleted_list_item"
    spans = nodes[1]["paragraph"]["rich_text"]
    assert any(
        s.get("text", {}).get("link", {}).get("url") == "https://www.notion.so/b" for s in spans
    )
    assert any(s["type"] == "equation" for s in spans)
    assert (
        next(n for n in nodes if n["type"] == "code")["code"]["rich_text"][0]["text"]["content"]
        == 'print("exact")\n'
    )


def test_math_code_is_not_changed():
    converter = Converter("a.md")
    nodes = converter.convert("Inline `$x$` and $y^2$.\n\n```latex\n\\(keep\\)\n```")
    spans = nodes[0]["paragraph"]["rich_text"]
    assert any(s.get("text", {}).get("content") == "$x$" for s in spans)
    assert any(s.get("equation", {}).get("expression") == "y^2" for s in spans)
    assert nodes[1]["code"]["rich_text"][0]["text"]["content"] == "\\(keep\\)\n"


def test_not_summarised_and_long_text_chunked():
    text = "Technical detail " * 400
    nodes = Converter("a.md").convert(text)
    spans = nodes[0]["paragraph"]["rich_text"]
    assert "".join(s["text"]["content"] for s in spans) == text.rstrip()
    assert all(len(s["text"]["content"]) <= 1800 for s in spans)


def test_api_batches_tables_and_deep_lists_without_truncation():
    server = FakeNotion()
    nodes = [block("paragraph", text=str(i)) for i in range(130)] + [
        block(
            "table",
            table_width=1,
            has_column_header=True,
            has_row_header=False,
            children=[block("table_row", cells=[rich_text(str(i))]) for i in range(150)],
        ),
        block(
            "bulleted_list_item",
            text="outer",
            children=[
                block(
                    "bulleted_list_item",
                    text="inner",
                    children=[block("paragraph", text="deep")],
                )
            ],
        ),
    ]
    server.append("root", nodes)
    assert canonical(server.tree("root")) == canonical(nodes)
    assert all(
        len(body["children"]) <= 50
        for method, path, body in server.requests
        if method == "PATCH" and path.startswith("/blocks/")
    )
