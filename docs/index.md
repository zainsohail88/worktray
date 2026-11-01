# Design notes

worktray is a FastAPI app on `127.0.0.1` with a SQLite database. Coding agents use the same data through an MCP server over stdio.

- [Technical vision](technical-vision.md): why it is built this way
- [Architecture](architecture.md): processes, modules, the sync flow and entry points
- [Boundaries](boundaries.md): HTTP routes, MCP tools, CLI commands, external calls and local files
- [Data model](data-model.md): items, SQLite tables and their rules
- [Conventions](conventions.md): rules for sources, the store, settings and tests
- [Glossary](glossary.md): the terms used in the code and the app

To add a source, see [Adding a source](../CONTRIBUTING.md#adding-a-source).
