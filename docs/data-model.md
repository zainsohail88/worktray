# Data model

Each row stores Pydantic JSON in a `payload` column. Each `Store` method opens its own connection. Writes that must not interleave use `BEGIN IMMEDIATE` (`worktray/store.py::Store`).

## Item

Defined in `worktray/models.py::Item`. Stream items live in the `items` table. Live items live in `live_snapshots`, with your changes kept separately in `annotations`.

| Field | Meaning |
|---|---|
| `key` | `<source>:<stable id>`, or the pull request URL for GitHub and Bitbucket |
| `status` | `proposed`, `open`, `done` or `dismissed` |
| `live` | Owned by the source and replaced on each sync |
| `personal` | Shown in My work, not only in the team view |
| `up_next`, `list_name`, `snoozed_until`, `due_date` | Your own changes |
| `lane` | `needs_me` or `waiting` on live items, empty otherwise |
| `close_suggested`, `close_hint` | Set when the tickets or pull requests an item names are done |
| `issue_type`, `parent_title` | Jira details |
| `checks_url`, `checks_detail` | The first failing check on a pull request |
| `attention` | On-call signals |
| `references` | Jira keys and pull request links the source saw, merged on each ingest |
| `linked_status` | Where those references stand, written by the upstream source |

Rules:

- `url` and `checks_url` must be `https://`, `http://` to `localhost`, `127.0.0.1` or `::1`, or start with `claude://`, `codex://` or `cursor://file/`. The host is parsed and a URL with a user name is refused (`worktray/models.py::Item.safe_url`).
- A done or dismissed item cannot change status (`worktray/store.py::Store.edit`).
- `ingest` never overwrites a row. It only replaces the link, adds new `references` and sets `close_suggested` on items that are still open. It rejects live items (`worktray/store.py::Store.ingest`).
- A live item accepts only dismissal and changes to note, list, up next, due date and snooze. The title belongs to the source (`worktray/store.py::Store.annotate`).
- `snoozed_until` needs a time zone. An empty string wakes the item and closing an item clears it (`worktray/models.py::ItemEdit.aware_timestamp`).

## Tables

| Table | Key | Holds | Written by |
|---|---|---|---|
| items | key | Stream items | `ingest`, `edit`, `merge_import`, `reconcile_meeting_proposals` |
| decisions | key | The first triage decision on a proposed item, accepted or dismissed | `edit`, `merge_import` |
| annotations | key | Your changes to live items | `annotate` |
| live_snapshots | source | The last good live items and the settings they were read under | `save_snapshot`, `drop_snapshot` |
| health | source | `SourceState` per source | `save_snapshot`, `save_health`, `drop_snapshot` |
| settings | key | Every source `Setting` by its key, the `source_<name>_enabled` switches, plus `team_jql`, `team_scope_origin`, `team_exclusions`, `refresh_intervals`, `auto_refresh`, `display_name`, `jira_account_id`, `oncall_current_epic`, `on_call_shift` and `google_meeting_backfilled_at`. Secrets are never stored here | `save_setting` |
| suggestions | id | Tidy-up `Suggestion` payloads, `pending`, `accepted` or `rejected`. The id is a hash of the content, so a rejected suggestion stays hidden when an agent repeats it | `replace_suggestions`, `decide_suggestion` |
| aliases | alias | Old key to new key after a Codex import is merged | `merge_import` |
| sightings | key | The first time a live item was seen | `current_live`, `annotated`, `save_snapshot` |

- A decision is written only when a proposed item first changes status, so metrics count each ask once (`worktray/store.py::Store.edit`).
- `save_snapshot` drops note, up next, snooze and close fields from incoming items, so your changes stay in `annotations` (`worktray/store.py::Store.save_snapshot`).
- A snapshot records the source's own settings it was read under, plus `team_jql` for Jira. It is hidden when any of them changes, such as a different Jira site or GitHub organisation (`worktray/engine.py::Engine._invalidate_changed_scopes`). It is dropped when the source is no longer connected.
- Meeting-note proposals are replaced only while untouched: still proposed, never edited, no note, not starred and in the list "Follow-ups" (`worktray/store.py::Store.reconcile_meeting_proposals`).
