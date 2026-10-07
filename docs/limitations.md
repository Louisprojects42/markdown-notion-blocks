# Limitations and API behavior

The converter keeps meaningful text and common structures, but is not a universal Markdown parser. Inline raw HTML, unusual extensions, image uploads, arbitrary heading anchors and embedded diagrams are not promised. Image references may be represented as text links. HTML interpretation follows the configured Markdown parser rather than a browser. Review warnings and output before using it with another system.

No local directory is scanned automatically. Page IDs, URL maps, source identities, repository URL, API version and credentials are entirely caller-controlled. No original project configuration or document layout is supplied.

The optional client targets the official HTTPS Notion API and rejects redirects. It chunks immediate child appends to 50 blocks and uses a conservative payload bound. It surfaces failures rather than silently truncating data. Rate-limited responses have bounded attempts and honor Retry-After; ambiguous server errors on writes are not automatically replayed. No idempotency ledger or interrupted-upload recovery engine is included.

Use an API version supported by the destination account. Reference documentation: [API versioning](https://developers.notion.com/reference/versioning), [request limits](https://developers.notion.com/reference/request-limits) and [append block children](https://developers.notion.com/reference/patch-block-children).

Exported block JSON and fake-endpoint tests are local evidence only. Current live-account compatibility and permissions have not been exercised. Rendered-property normalization compares the supported text/style/tree properties, not every possible Notion block or metadata field.
