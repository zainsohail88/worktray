# worktray design notes

worktray is a single-user FastAPI dashboard on `127.0.0.1`. It reads work from many sources into one SQLite-backed queue, and coding agents reach the same queue through a stdio MCP server. Installation and configuration are in the [README](../README.md).

- [Technical vision](technical-vision.md): why it is shaped this way
- [Architecture](architecture.md): processes, modules, refresh flow and entry points
- [Boundaries](boundaries.md): HTTP routes, MCP tools, CLI commands, external calls and local files
- [Data model](data-model.md): items, SQLite tables and their invariants
- [Conventions](conventions.md): rules for sources, the store, settings and tests
- [Glossary](glossary.md): live and stream items, asks, decisions, sources, settings
- [Writing a source plugin](plugins.md): the plugin contract with a worked example
- [Adding a built-in source](patterns/add-a-source.md)
