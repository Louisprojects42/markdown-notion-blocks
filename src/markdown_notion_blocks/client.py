"""Small official-API client with bounded retries and no token logging."""

import copy
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request


class NotionError(RuntimeError):
    pass


class Client:
    def __init__(self, token, version):
        self.token = token
        self.version = version
        self.last_request = 0.0

    def request(self, method, path, payload=None):
        # Redirects must not send the bearer token to another host.
        from urllib.request import HTTPRedirectHandler, build_opener

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        for attempt in range(5):
            time.sleep(max(0, 0.36 - (time.monotonic() - self.last_request)))
            data = json.dumps(payload).encode() if payload is not None else None
            request = Request(
                "https://api.notion.com/v1" + path,
                data=data,
                method=method,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Notion-Version": self.version,
                    "Content-Type": "application/json",
                },
            )
            self.last_request = time.monotonic()
            try:
                with build_opener(NoRedirect).open(request, timeout=45) as response:
                    return json.load(response)
            except HTTPError as error:
                # Never log response bodies: they can reflect document text/secrets.
                retry = error.code in {429, 529} or (
                    method == "GET" and error.code in {500, 502, 503, 504}
                )
                if retry and attempt < 4:
                    time.sleep(
                        max(0.0, float(error.headers.get("Retry-After", min(2**attempt, 30))))
                    )
                    continue
                raise NotionError(
                    f"Notion HTTP {error.code} on {method} {path}; "
                    "check access/settings. A failed write may be partial; inspect the destination before retrying."
                ) from None
            except URLError:
                raise NotionError(
                    "Notion network/TLS failure; no insecure TLS fallback. "
                    "A write may have been applied; inspect the destination before retrying."
                ) from None
        raise NotionError("Notion retry limit reached.")

    def children(self, parent):
        result, cursor = [], None
        while True:
            query = urlencode({"page_size": 100, **({"start_cursor": cursor} if cursor else {})})
            response = self.request("GET", f"/blocks/{parent}/children?{query}")
            result.extend(response["results"])
            if not response.get("has_more"):
                return result
            cursor = response["next_cursor"]

    def query(self, source, **body):
        result = []
        while True:
            response = self.request("POST", f"/data_sources/{source}/query", body)
            result.extend(response["results"])
            if not response.get("has_more"):
                return result
            body["start_cursor"] = response["next_cursor"]

    def append(self, parent, blocks):
        """Upload arbitrary-size trees in <=50-block batches, one nesting level at a time."""
        created = []
        for start in range(0, len(blocks), 50):
            original = blocks[start : start + 50]
            shallow, descendants = [], []
            for item in original:
                item = copy.deepcopy(item)
                children = item[item["type"]].pop("children", [])
                if item["type"] == "table" and children:
                    item["table"]["children"] = children[:1]
                    children = children[1:]
                shallow.append(item)
                descendants.append(children)
            if len(json.dumps(shallow).encode()) > 400_000:
                raise NotionError(
                    "Block batch exceeds safe payload size; split the source section."
                )
            response = self.request("PATCH", f"/blocks/{parent}/children", {"children": shallow})
            new = response["results"]
            if len(new) != len(shallow):
                raise NotionError("Notion returned an unexpected append result count.")
            created.extend(new)
            for item, children in zip(new, descendants, strict=True):
                if children:
                    self.append(item["id"], children)
        return created

    def tree(self, parent):
        nodes = self.children(parent)
        for node in nodes:
            if node.get("has_children"):
                node[node["type"]]["children"] = self.tree(node["id"])
        return nodes


def canonical(blocks):
    """Only compare rendered properties; Notion supplies extra server metadata/defaults."""
    result = []
    for node in blocks:
        kind = node["type"]
        data = node[kind]
        entry = {"type": kind}
        for key in (
            "language",
            "checked",
            "table_width",
            "has_column_header",
            "has_row_header",
            "expression",
        ):
            if key in data:
                entry[key] = data[key]

        def normalize(items):
            values = []
            for item in items:
                item_type = item["type"]
                part = {"type": item_type}
                if item_type == "text":
                    part["text"] = item["text"]["content"]
                    if item["text"].get("link"):
                        part["url"] = item["text"]["link"]["url"]
                    true_flags = {k: v for k, v in item.get("annotations", {}).items() if v is True}
                    if true_flags:
                        part["annotations"] = true_flags
                elif item_type == "equation":
                    part["expression"] = item["equation"]["expression"]
                # Notion joins adjacent equally styled spans and discards empty
                # spans. Compare their rendered meaning rather than API boundaries.
                if item_type == "text":
                    if not part["text"]:
                        continue
                    style = {k: v for k, v in part.items() if k != "text"}
                    if (
                        values
                        and values[-1]["type"] == "text"
                        and style == {k: v for k, v in values[-1].items() if k != "text"}
                    ):
                        values[-1]["text"] += part["text"]
                        continue
                values.append(part)
            return values

        if "rich_text" in data:
            entry["rich_text"] = normalize(data["rich_text"])
        if "cells" in data:
            entry["cells"] = [normalize(cell) for cell in data["cells"]]
        if kind == "image":
            entry["url"] = data["external"]["url"]
        if "children" in data:
            entry["children"] = canonical(data["children"])
        result.append(entry)
    return result
