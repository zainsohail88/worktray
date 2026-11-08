# Using worktray

## My work

The page has two tables.

- Work lists your meetings, pull requests, tickets and follow-ups.
- Triage lists items found in meeting notes, Slack and agent sessions. Accept an item to move it to Work, or dismiss it.

In the Work table:

- Needs me shows the items you can act on. Waiting shows the items someone else holds, such as a reviewer, an assignee or a build.
- Star an item to mark it Up next. Snooze it until this afternoon, tomorrow or after your next meeting. Mark it done or dismiss it.
- The strip above the table shows your next meeting and the free time before it. Brief lists the tickets and pull requests that the meeting mentions.
- A Slack ask that mentions one of your tickets or pull requests shows under that item. If it mentions someone else's ticket, the ticket status shows next to it, such as `ABC-123 In Testing · 1 PR merged`.
- Tidy-up suggestions propose merges, links, clearer titles, due dates and items to close. A suggestion changes your items when you accept it.

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

Lists the open tickets under your team's on-call epic, with the ones that need attention first. It also shows your on-call shift from Jira Service Management. worktray finds the epic by a word in its name, set in the On call settings. The default is `KTLO`.

## Team

Recent tickets and pull requests for each person in your team's Jira query. You edit the query on this tab. Hide member removes someone who has left the team.

## History

Closed items by day and a standup note you can copy.

## Connections

The sync status of each source. Each source syncs on its own schedule. If a sync fails, the last good result stays on screen and shows when it went out of date.
