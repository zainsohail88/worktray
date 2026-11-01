# Data Model

Rows store Pydantic JSON in a `payload` column. Each `Store` method opens its own connection; writes that must not interleave use `BEGIN IMMEDIATE` (`worktray/store.py::Store`).

## Entities

### Item

- **Source**: `worktray/models.py::Item`
- **Key fields**: `key` (`<source>:<stable id>`, or the PR URL for GitHub and Bitbucket), `status` (`proposed`, `open`, `done`, `dismissed`), `live`, `personal`, `up_next`, `list_name`, `close_suggested`, `lane` (`needs_me` or `waiting` on live items, empty otherwise), `issue_type`, `due_date`, `parent_title`, `checks_url`, `checks_detail`, `snoozed_until`, `close_hint`, `attention` (on-call signals), `references` (Jira keys and PR links the source saw, merged on each ingest), `linked_status` (where those stand, written by the upstream source)
- **Relationships**: stream items live in `items`; live items live in `live_snapshots` with user overlays in `annotations`
- **Invariants**:
  - `url` must start with `https://`, `http://localhost`, `claude://`, `codex://` or `cursor://file/` (`worktray/models.py::Item.safe_url`)
  - A done or dismissed item cannot move to another status (`worktray/store.py::Store.edit`)
  - `ingest` never overwrites a row; it only replaces the link, adds new `references` and sets `close_suggested` on still-open items, and rejects live items (`worktray/store.py::Store.ingest`)
  - A live item accepts only `dismissed`, note, list, up-next and snooze changes; titles are source-owned (`worktray/store.py::Store.annotate`)
  - `snoozed_until` needs a timezone; an empty string wakes the item, and closing an item clears it (`worktray/models.py::ItemEdit.aware_timestamp`)

### Tables

| Table | Key | Holds | Written by |
|---|---|---|---|
| items | key | Stream items | `ingest`, `edit`, `merge_import`, `reconcile_meeting_proposals` |
| decisions | key | First triage of a proposed item (accepted or dismissed) | `edit`, `merge_import` |
| annotations | key | User fields on live items | `annotate` |
| live_snapshots | source | Last good live items and the scope they were read under | `save_snapshot` |
| health | source | `SourceState` per source | `save_snapshot`, `save_health` |
| settings | key | `team_jql`, `team_scope_origin`, `team_exclusions`, `refresh_intervals`, `auto_refresh`, `display_name`, `jira_account_id`, `slack_user_id`, `oncall_current_epic`, `on_call_shift`, meeting folder, aliases and backfill time, every source `Setting` by its key, and `source_<name>_enabled` switches. Secrets are never stored here | `save_setting` |
| suggestions | id | Cleanup `Suggestion` payloads, `pending`, `accepted` or `rejected`; the id hashes the content so a rejected one stays hidden when an agent repeats it | `replace_suggestions`, `decide_suggestion` |
| aliases | alias | Old key to canonical key after a Codex import merge | `merge_import` |
| sightings | key | First time a live item was seen | `current_live`, `annotated`, `save_snapshot` |

- A decision row is written only when a `proposed` item first changes status, so metrics count each ask once (`worktray/store.py::Store.edit`).
- `save_snapshot` strips note, up-next, snooze and close fields from incoming items so user state stays in `annotations` (`worktray/store.py::Store.save_snapshot`).
- A snapshot records the source's own settings it was read under, plus `team_jql` for Jira. It is hidden when any of them changes, such as a different Jira site or GitHub organisation, and dropped when the source is no longer connected (`worktray/engine.py::Engine._invalidate_changed_scopes`).
- Gemini proposals are replaced only while untouched: still proposed, no note, not starred, list "Follow-ups" (`worktray/store.py::Store.reconcile_meeting_proposals`).
