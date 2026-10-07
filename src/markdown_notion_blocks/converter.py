"""Convert Markdown to Notion blocks without replacing technical content."""

import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt


def rich_text(text, annotations=None, url=None):
    result = []
    for offset in range(0, len(text), 1800):
        item = {"type": "text", "text": {"content": text[offset : offset + 1800]}}
        if url:
            item["text"]["link"] = {"url": url}
        if annotations:
            item["annotations"] = dict(annotations)
        result.append(item)
    if len(result) > 100:
        raise ValueError("Text exceeds a Notion rich-text array; split the source section.")
    return result


def block(kind, text="", children=None, rich=None, **attributes):
    data = attributes
    if kind not in {
        "divider",
        "table_of_contents",
        "image",
        "equation",
        "table",
        "table_row",
    }:
        data["rich_text"] = rich if rich is not None else rich_text(text)
    if children:
        data["children"] = children
    return {"object": "block", "type": kind, kind: data}


class Converter:
    def __init__(self, source, page_urls=None, repository_url="", reference="main"):
        self.source = source
        self.pages = page_urls or {}
        self.repository = repository_url.rstrip("/")
        self.reference = reference or "main"
        self.warnings = []
        self.math = []
        self.parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])

    def link(self, url):
        parsed = urlsplit(url)
        if parsed.scheme in {"https", "http", "mailto"}:
            return url
        if parsed.scheme or url.startswith("//"):
            self.warnings.append(f"Unsupported link retained as text: {url}")
            return None
        if url.startswith("#"):
            self.warnings.append(f"Section anchor retained as text: {url}")
            return None
        parts = list(Path(self.source).parent.parts)
        for part in unquote(parsed.path).replace("\\", "/").split("/"):
            if part == "..":
                if not parts:
                    self.warnings.append(f"Link escapes repository: {url}")
                    return None
                parts.pop()
            elif part and part != ".":
                parts.append(part)
        target = "/".join(parts)
        if target in self.pages:
            if parsed.fragment:
                self.warnings.append(
                    f"Notion page linked without unsupported section anchor: {url}"
                )
            return self.pages[target]
        if not self.repository:
            self.warnings.append(f"Unmapped local reference retained as text: {url}")
            return None
        self.warnings.append(
            f"Local reference uses repository fallback (may be unpublished): {url}"
        )
        return (
            self.repository
            + "/blob/"
            + quote(self.reference, safe="")
            + "/"
            + quote(target, safe="/")
            + ("#" + parsed.fragment if parsed.fragment else "")
        )

    def math_markers(self, text):
        # Do not turn equations inside fenced code into rendered mathematics.
        def replace(match):
            expression = next(g for g in match.groups() if g is not None).strip()
            index = len(self.math)
            self.math.append(expression)
            return f"NOTIONMATH{index}END"

        sections = re.split(
            r"(^```[^\n]*\n.*?^```\s*$|^~~~[^\n]*\n.*?^~~~\s*$|`+[^`\n]*`+)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        return "".join(
            piece
            if i % 2
            else re.sub(
                r"\\\[(.*?)\\\]|\$\$(.*?)\$\$|\\\((.*?)\\\)|(?<!\\)\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)",
                replace,
                piece,
                flags=re.DOTALL,
            )
            for i, piece in enumerate(sections)
        )

    def inline(self, tokens):
        result, annotations, stack, url = [], {}, [], None
        for token in tokens or []:
            kind = token.type
            if kind in {"strong_open", "em_open", "s_open"}:
                stack.append(dict(annotations))
                annotations[
                    {
                        "strong_open": "bold",
                        "em_open": "italic",
                        "s_open": "strikethrough",
                    }[kind]
                ] = True
            elif kind in {"strong_close", "em_close", "s_close"}:
                annotations = stack.pop()
            elif kind == "link_open":
                url = self.link(token.attrGet("href"))
            elif kind == "link_close":
                url = None
            elif kind == "image":
                target = self.link(token.attrGet("src"))
                result.extend(rich_text("[Image: " + token.content + "]", annotations, target))
            elif kind in {"softbreak", "hardbreak"}:
                result.extend(rich_text("\n", annotations, url))
            elif kind == "code_inline":
                result.extend(rich_text(token.content, {**annotations, "code": True}, url))
            elif kind == "text":
                for piece in re.split(r"(NOTIONMATH\d+END)", token.content):
                    math = re.fullmatch(r"NOTIONMATH(\d+)END", piece)
                    if math:
                        expression = self.math[int(math[1])]
                        if len(expression) <= 1000:
                            result.append(
                                {
                                    "type": "equation",
                                    "equation": {"expression": expression},
                                }
                            )
                        else:
                            self.warnings.append("Long equation preserved as code text.")
                            result.extend(rich_text(expression, {"code": True}))
                    else:
                        result.extend(rich_text(piece, annotations, url))
            else:
                result.extend(rich_text(token.content, annotations, url))
        if len(result) > 100:
            raise ValueError("Inline formatting exceeds 100 rich-text spans; split the paragraph.")
        return result

    def convert(self, text, kind="md"):
        if kind in {"yaml", "yml", "txt", "rst"}:
            return [
                block(
                    "code",
                    text=text or "(Empty document)",
                    language="yaml" if kind in {"yaml", "yml"} else "plain text",
                )
            ]
        tokens = self.parser.parse(self.math_markers(text))
        index = 0

        def parse(stop=None, list_kind=None):
            nonlocal index
            output = []
            while index < len(tokens):
                token = tokens[index]
                index += 1
                if token.type == stop:
                    break
                if token.type in {"heading_open", "paragraph_open"}:
                    inline = tokens[index]
                    index += 2
                    content = self.inline(inline.children)
                    if token.type == "heading_open":
                        level = min(int(token.tag[1]), 3)
                        output.append(block(f"heading_{level}", rich=content))
                    elif inline.content == "[[TOC]]":
                        output.append(block("table_of_contents", color="default"))
                    elif len(content) == 1 and content[0]["type"] == "equation":
                        output.append(
                            block(
                                "equation",
                                expression=content[0]["equation"]["expression"],
                            )
                        )
                    else:
                        output.append(block("paragraph", rich=content))
                elif token.type in {"bullet_list_open", "ordered_list_open"}:
                    item_kind = (
                        "bulleted_list_item"
                        if token.type == "bullet_list_open"
                        else "numbered_list_item"
                    )
                    output.extend(parse(token.type.replace("_open", "_close"), item_kind))
                elif token.type == "list_item_open":
                    children = parse("list_item_close")
                    content = (
                        children.pop(0)["paragraph"]["rich_text"]
                        if children and children[0]["type"] == "paragraph"
                        else []
                    )
                    item_type, extra = list_kind or "bulleted_list_item", {}
                    if content and content[0]["type"] == "text":
                        check = re.match(r"^\[([ xX])\]\s*", content[0]["text"]["content"])
                        if check:
                            content[0]["text"]["content"] = content[0]["text"]["content"][
                                check.end() :
                            ]
                            item_type, extra = (
                                "to_do",
                                {"checked": check[1].lower() == "x"},
                            )
                    output.append(block(item_type, rich=content, children=children, **extra))
                elif token.type == "blockquote_open":
                    children = parse("blockquote_close")
                    content = (
                        children.pop(0)["paragraph"]["rich_text"]
                        if children and children[0]["type"] == "paragraph"
                        else []
                    )
                    output.append(block("quote", rich=content, children=children))
                elif token.type == "table_open":
                    rows, cells = [], []
                    while tokens[index].type != "table_close":
                        item = tokens[index]
                        index += 1
                        if item.type == "tr_open":
                            cells = []
                        elif item.type == "inline":
                            cells.append(self.inline(item.children))
                        elif item.type == "tr_close":
                            rows.append(block("table_row", cells=cells))
                    index += 1
                    if rows:
                        width = len(rows[0]["table_row"]["cells"])
                        output.append(
                            block(
                                "table",
                                children=rows,
                                table_width=width,
                                has_column_header=True,
                                has_row_header=False,
                            )
                        )
                elif token.type in {"fence", "code_block"}:
                    language = token.info.strip().split()[0] if token.info.strip() else "plain text"
                    language = {
                        "ps1": "powershell",
                        "py": "python",
                        "sh": "bash",
                        "text": "plain text",
                    }.get(language, language)
                    if language not in {
                        "python",
                        "powershell",
                        "bash",
                        "yaml",
                        "json",
                        "markdown",
                        "html",
                        "javascript",
                        "typescript",
                        "plain text",
                        "latex",
                        "sql",
                        "css",
                        "c",
                        "c++",
                        "r",
                        "toml",
                        "xml",
                    }:
                        language = "plain text"
                    output.append(block("code", text=token.content, language=language))
                elif token.type == "hr":
                    output.append(block("divider"))
                elif token.type in {"html_block", "html_inline"}:
                    output.append(block("code", text=token.content, language="html"))
                else:
                    if token.content:
                        output.append(block("paragraph", text=token.content))
            return output

        result = parse()
        return result or [block("paragraph", text="Empty source placeholder; no content invented.")]
