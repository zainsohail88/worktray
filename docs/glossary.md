# Glossary

| Term | Meaning | Where it shows | Code |
|------|---------|----------------|------|
| Ask | A proposed item from Slack, in the list "Asks" | Triage | `worktray/sources/codex_slack.py` |
| Batch | What a reader returns: items and a one-line detail | Every `read_*` function | `worktray/models.py::Batch` |
| Decision | The first accept or dismiss of a proposed item | Connections, suggestion metrics | `worktray/store.py::Store.edit` |
| Live item | An item the source owns, such as a Jira issue, pull request or meeting. It is replaced on every successful sync | `live=True` | `worktray/engine.py::Engine.refresh` |
| Profile | A renewable OAuth grant. The only one is `google` | Auth | `worktray/auth/oauth.py::Profile` |
| Scope | The source settings, plus `team_jql` for Jira, that a saved result was read under. A result whose scope changed is hidden | Connections | `worktray/engine.py::Engine._scopes` |
| Secret | A token declared by a source, kept in the system keyring | Settings | `worktray/config.py::Secret` |
| Setting | A preference such as `github_orgs`, read from `WORKTRAY_<KEY>` first, then the settings table | Settings | `worktray/config.py::Setting` |
| Source | A registry row with name, label, reader, settings, secrets, schedule and checks, built in or from a plugin | Engine, Settings, CLI | `worktray/sources/registry.py::Source` |
| Switched off | A source that is not on, which is how every source starts. The scheduler skips it and its live items are hidden. Stored items, proposals included, stay | Settings | `worktray/config.py::source_enabled` |
| Sighting | The first time a live item key appeared, used as its `first_seen` | `/api/state` | `worktray/store.py::Store.current_live` |
| Stale | A source whose last sync failed, showing its previous result | `SourceState.stale_since` | `worktray/engine.py::Engine.refresh` |
| Stream item | An item the user owns, kept in the `items` table with a triage lifecycle | `live=False` | `worktray/store.py::Store.ingest` |
| Up next | Starred items, pinned to the top of My work | `up_next` | `worktray/models.py::Item` |
| Work window | The last 90 days. Older GitHub and Bitbucket pull requests are hidden | My work, Team | `worktray/models.py::within_work_window` |
