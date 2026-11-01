# worktray documentation

Install and run: see the [README](../README.md).

## Using worktray

- [Using worktray](features.md): the tabs and keyboard shortcuts
- [Sources](sources.md): what each source reads and what it needs
- [Configuration](configuration.md): settings, environment variables and data
- [Commands](commands.md): the command line, background service and coding agents

## Design notes

worktray is a FastAPI app on `127.0.0.1` with a SQLite database. Coding agents use the same data through an MCP server over stdio.

- [Technical vision](technical-vision.md): why it is shaped this way
- [Architecture](architecture.md): processes, modules, refresh flow and entry points
- [Boundaries](boundaries.md): HTTP routes, MCP tools, CLI commands, external calls and local files
- [Data model](data-model.md): items, SQLite tables and their invariants
- [Conventions](conventions.md): rules for sources, the store, settings and tests
- [Glossary](glossary.md): live and stream items, asks, decisions, sources, settings
- [Writing a source plugin](plugins.md): the plugin contract with a worked example
- [Adding a built-in source](patterns/add-a-source.md)
