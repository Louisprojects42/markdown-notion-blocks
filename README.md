# Markdown Notion Blocks

Convert Markdown into Notion API block JSON, preserving structured text instead of summarizing it. Extracted from tooling developed while working on personal engineering projects.

The default command is offline. An optional small library client can append block trees to a destination that the caller supplies. This is not a repository sync engine: it does not discover documents, create a knowledge database, track source identity, or manage page updates.

## Install and try

Requires Python 3.11+. From this folder:

```text
python -m pip install .
markdown-notion-blocks examples/sample.md --output blocks.json
```

The output is a JSON array of blocks. Warnings go to stderr. Local links remain text unless mapped explicitly or given a caller-controlled repository fallback.

For library use, see [the offline example](examples/convert_note.py). Converter accepts a repository-relative source path, an optional mapping of local paths to page URLs, an optional repository URL and a reference name. The CLI accepts the same settings through --source, --page-map, --repository-url and --reference. Page maps are plain JSON objects of string paths and URLs.

## Supported content

Headings, paragraphs, basic inline styles, links, nested lists, checkboxes, quotations, tables, fenced code, horizontal rules and common math delimiters are converted. Long text spans are chunked. Unsupported local anchors and link schemes produce warnings rather than invented destinations. Text-like YAML/TXT/RST files can be retained in code blocks.

The block client provides bounded requests, child pagination, batched tree appends and rendered-property comparison. Construct Client with your own token and explicit API version. It does not read environment files or store credentials. Calling client methods is a separate, explicit network action; the export command never does it.

## Limitations and checks

Read [limitations and API behavior](docs/limitations.md). This is a deliberately small converter, not a complete CommonMark/Notion round-trip implementation. Appending is not idempotent, and a partial failed upload needs destination inspection before retrying. No live workspace import is claimed.

```text
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
python -m build
```

Tests use synthetic text and an in-memory endpoint. CI checks Windows/Linux and builds the package. See [provenance](docs/provenance.md), [contribution guidance](CONTRIBUTING.md) and [LICENSE](LICENSE).
