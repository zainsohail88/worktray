# Glossary

| Term | Meaning | Context | Source |
|------|---------|---------|--------|
| Ask | A proposed item summarised from Slack, meeting notes or Confluence | `tracker_propose`, list "Asks" | `worktray/mcp_server.py::tracker_propose` |
| Batch | What an adapter returns: items plus a scope description | Every `read_*` function | `worktray/models.py::Batch` |
| Decision | The first accepted or dismissed triage of a proposed item | Metrics | `worktray/store.py::Store.edit` |
| Live item | Source-owned item (Jira issue, PR, event) replaced on every successful refresh | `live=True` | `worktray/engine.py::Engine.refresh` |
| Profile | The renewable OAuth grant slot; today only `google` | Auth | `worktray/auth/oauth.py::Profile` |
| Scope | The `team_jql` query a Jira snapshot was read under | Team workload | `worktray/engine.py::Engine._scope` |
| Secret | A token declared by a source, kept in the system keyring and never returned to the browser | Settings | `worktray/config.py::Secret` |
| Setting | A non-secret preference such as `github_orgs`, read from `WORKTRAY_<KEY>` first, then from the settings table | Settings | `worktray/config.py::Setting` |
| Source | A registry row: name, label, reader, settings, secrets, schedule and checks; built in or from a plugin | Engine, Settings, CLI | `worktray/sources/registry.py::Source` |
| Switched off | A source that is not on, which is how every source starts: never read and its live items hidden. Items already stored, proposals included, stay | Settings | `worktray/config.py::source_enabled` |
| Sighting | First time a live item key appeared, used as its `first_seen` | `/api/state` | `worktray/store.py::Store.annotated` |
| Stale | A source whose last refresh failed and which is showing its previous snapshot | `SourceState.stale_since` | `worktray/engine.py::Engine.refresh` |
| Stream item | Human-owned item kept in `items` with a triage lifecycle | `live=False` | `worktray/store.py::Store.ingest` |
| Up next | Starred items pinned to the top of My work | `up_next` | `worktray/models.py::Item` |
| Work window | The last 90 days; older GitHub and Bitbucket items are hidden | `Engine.items` | `worktray/engine.py::Engine.items` |
