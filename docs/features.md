# Using worktray

## My work

Two tables:

- **Work**: meetings, pull requests, tickets and follow-ups that are yours.
- **Triage**: items found in meeting notes, Slack and agent sessions. Accept one to move it to Work, or dismiss it.

In the Work table:

- **Needs me** shows items you can act on. **Waiting** shows items held by someone else, such as a reviewer, an assignee or a build.
- Star an item to mark it **Up next**. Snooze it until this afternoon, tomorrow or after your next meeting. Mark it done or dismiss it.
- The strip above the table shows your next meeting and the free time before it. **Brief** lists the tickets and pull requests that the meeting mentions.
- A Slack ask that mentions one of your tickets or pull requests is shown under that item. If it mentions someone else's ticket, the ticket's status is shown next to it, such as `ABC-123 In Testing · 1 PR merged`.
- **Tidy-up suggestions** propose merges, links, clearer titles, due dates and items to close. Nothing changes until you accept a suggestion.

### Keyboard

| Key | Action |
|---|---|
| `j` / `k` | Move down / up |
| `s` | Star |
| `a` | Accept |
| `d` | Done |
| `x` | Dismiss |
| `z` | Snooze |
| `e` | Edit |
| `b` | Brief |
| `/` | Search |
| `?` | Show all shortcuts |

## On call

Lists the open tickets under your team's on-call epic, with the ones that need attention first, and shows your on-call shift from Jira Service Management. The epic is found by a word in its name, set in the On call settings (default `KTLO`).

## Team

Recent tickets and pull requests per person, for the people in your team's Jira query. Edit the query on this tab. Use **Hide member** to remove someone who has left the team.

## History

Closed items grouped by day, and a standup note you can copy.

## Connections

Each source syncs on its own schedule. If a sync fails, the last good result stays on screen, marked with when it went out of date.
