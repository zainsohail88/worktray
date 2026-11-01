"use strict";
const $ = (id) => document.getElementById(id);
// Source labels come from the server's source registry, so a new source needs no change here.
const label = (source) => state?.source_labels?.[source] || source;
// Sources declare a group on the server; items of one group share a Type label, icon and colour.
const GROUP_LABELS = {meeting:"Meeting", pr:"PR", jira:"Jira", slack:"Slack", notes:"Notes", confluence:"Confluence", agent:"Agent", manual:"Manual", other:"Other"};
const ICONS = {
  "meeting": "M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Zm0 16H5V10h14v10Zm0-12H5V6h14v2Z",
  "pr": "M6 3a3 3 0 0 0-1 5.83v6.34a3 3 0 1 0 2 0V8.83A3 3 0 0 0 6 3Zm0 2a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm0 14a1 1 0 1 1 0-2 1 1 0 0 1 0 2Zm12-3.83V9a3 3 0 0 0-3-3h-2V3l-4 4 4 4V8h2a1 1 0 0 1 1 1v6.17a3 3 0 1 0 2 0ZM18 19a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
  "jira": "M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2Zm-9 14-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9Z",
  "slack": "M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Zm0 14H5.17L4 17.17V4h16v12Z",
  "notes": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm2 16H8v-2h8v2Zm0-4H8v-2h8v2Zm-3-5V3.5L18.5 9H13Z",
  "agent": "M12 2l1.8 4.7L18.5 8.5l-4.7 1.8L12 15l-1.8-4.7L5.5 8.5l4.7-1.8L12 2Zm7 10 .9 2.1L22 15l-2.1.9L19 18l-.9-2.1L16 15l2.1-.9L19 12ZM5 14l.9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14Z",
  "manual": "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25ZM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83Z",
  "done": "M9 16.17 4.83 12l-1.41 1.41L9 19 21 7l-1.41-1.41L9 16.17Z",
  "snooze": "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2ZM12 20a8 8 0 1 1 0-16 8 8 0 0 1 0 16Zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7Z",
  "dismiss": "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41Z",
  "brief": "M3 13h2v-2H3v2Zm0 4h2v-2H3v2Zm0-8h2V7H3v2Zm4 4h14v-2H7v2Zm0 4h14v-2H7v2ZM7 7v2h14V7H7Z"
};
const TYPE_ICON = {meeting: "meeting", pr: "pr", jira: "jira", slack: "slack", notes: "notes", confluence: "notes", agent: "agent", manual: "manual"};
const icon = (name) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name] || ICONS.manual}"/></svg>`;
const typeOf = (item) => item.source === "manual" ? "manual" : state?.source_groups?.[item.source] || "other";
const groupLabel = (group) => GROUP_LABELS[group] || group.charAt(0).toUpperCase() + group.slice(1);
const typeLabel = (item) => groupLabel(typeOf(item));
const esc = (text) => String(text ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const stamp = (item) => item.opened_at || item.first_seen;
const ageMs = (item) => Date.now() - new Date(stamp(item)).getTime();
const age = (item) => Math.max(0, Math.floor(ageMs(item) / 86400000));
const date = (value) => value ? new Date(value).toLocaleString() : "Never";
const clock = (value) => new Date(value).toLocaleTimeString(undefined, {hour:"numeric", minute:"2-digit"});
const snoozed = (item) => Boolean(item.snoozed_until) && new Date(item.snoozed_until).getTime() > Date.now();
const WEEK = 7 * 86400000;
function ageLabel(item) {
  const hours = Math.max(0, Math.floor(ageMs(item) / 3600000));
  return hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`;
}
function until(value) {
  const minutes = Math.round((new Date(value).getTime() - Date.now()) / 60000);
  if (minutes <= 0) return "now";
  if (minutes < 60) return `in ${minutes}m`;
  return minutes < 48 * 60 ? `in ${Math.round(minutes / 60)}h` : `in ${Math.round(minutes / 1440)}d`;
}
function ago(value) {
  const minutes = Math.floor((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  return minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`;
}
const intervalLabel = (seconds) => seconds % 3600 === 0 ? `${seconds / 3600}h` : `${seconds / 60}m`;
function duration(milliseconds) {
  const minutes = Math.max(1, Math.round(milliseconds / 60000));
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h${minutes % 60 ? ` ${minutes % 60}m` : ""}`;
}
function eventTime(item) {
  const start = new Date(item.starts_at);
  const end = new Date(item.ends_at);
  if (item.all_day) {
    const day = value => new Date(value.slice(0,10) + "T12:00:00").toLocaleDateString(undefined, {month:"short",day:"numeric"});
    const lastDay = new Date(item.ends_at.slice(0,10) + "T12:00:00");
    lastDay.setDate(lastDay.getDate() - 1);
    const last = lastDay.toLocaleDateString(undefined, {month:"short",day:"numeric"});
    return `${day(item.starts_at)}${day(item.starts_at) === last ? "" : ` - ${last}`} · All day`;
  }
  return `${start.toLocaleString(undefined, {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})} - ${end.toLocaleString(undefined, {month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"})}`;
}
const WORK_PAGE = 50;
const TRIAGE_PAGE = 25;
const ONCALL_PAGE = 25;
let oncallAll = false;
let state = null;
let view = "mine";
let editing = null;
let newKey = null;
let noticeTimer = null;
let signature = "";
let chip = "";
let workSort = null;
// Null keeps triage on the default order, newest first like the work table.
const DEFAULT_TRIAGE_SORT = null;
let triageSort = DEFAULT_TRIAGE_SORT;
let workAll = false;
let triageAll = false;
let snoozeOpen = null;
let briefOpen = null;
const briefs = new Map();
let focusHint = null;
let teamSort = "active";
let teamForceOpen = null;
const teamFocus = new Map();
const teamLimits = new Map();
const ALERT_REASONS = /review requested|failing checks|ready to merge/i;
const MEETING_WARNING_MINUTES = 10;
let alertBaseline = null;
let notified = new Set();
try { notified = new Set(JSON.parse(localStorage.getItem("worktray-notified") || "[]")); }
catch (error) { if (!(error instanceof DOMException || error instanceof SyntaxError)) throw error; }

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const next = theme === "dark" ? "light" : "dark";
  $("theme-toggle").setAttribute("aria-label", `Switch to ${next} mode`);
  $("theme-toggle").title = `Switch to ${next} mode`;
  document.querySelector('meta[name="theme-color"]').content = theme === "dark" ? "#121b29" : "#edf1f6";
}

try { applyTheme(localStorage.getItem("worktray-theme") === "light" ? "light" : "dark"); }
catch (error) { if (!(error instanceof DOMException)) throw error; }
$("theme-toggle").onclick = () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(theme);
  try { localStorage.setItem("worktray-theme", theme); }
  catch (error) {
    if (!(error instanceof DOMException)) throw error;
    notice("Your browser blocked saving the theme. It will reset next time.");
  }
};

async function api(path, method = "GET", body) {
  const response = await fetch(path, {method, headers: body ? {"Content-Type":"application/json"} : {}, body: body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Something in the form is not right. Check it and try again.");
  return data;
}

function notice(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 15000);
}

function alertsEnabled() {
  try { return "Notification" in window && Notification.permission === "granted" && localStorage.getItem("worktray-alerts") === "on"; }
  catch (error) { if (!(error instanceof DOMException)) throw error; return false; }
}

function announce(id, title, body) {
  notified.add(id);
  try { localStorage.setItem("worktray-notified", JSON.stringify([...notified].slice(-500))); }
  catch (error) { if (!(error instanceof DOMException)) throw error; }
  try { new Notification(title, {body, tag: id}); }
  catch (error) { if (!(error instanceof TypeError)) throw error; }
}

// Work that was already waiting when the page opened is not news; only later arrivals and upcoming meetings alert.
function notifyArrivals() {
  const arrivals = state.items.filter(item => item.status === "open" && !snoozed(item) && item.lane === "needs_me" && ALERT_REASONS.test(item.reason))
    .map(item => [`${item.key}|${item.reason}`, item]);
  if (alertBaseline === null) alertBaseline = new Set(arrivals.map(([id]) => id));
  if (!alertsEnabled()) return;
  for (const [id, item] of arrivals) if (!alertBaseline.has(id) && !notified.has(id)) announce(id, item.reason, item.title);
  for (const item of timedMeetings()) {
    const minutes = (new Date(item.starts_at).getTime() - Date.now()) / 60000;
    const id = `meeting|${item.key}|${item.starts_at}`;
    if (minutes > 0 && minutes <= MEETING_WARNING_MINUTES && !notified.has(id)) announce(id, `${item.title} starts ${until(item.starts_at)}`, eventTime(item));
  }
}

async function load() {
  try {
    const next = await api("/api/state");
    const nextSignature = JSON.stringify(next);
    state = next;
    if (signature !== nextSignature) { signature = nextSignature; render(); }
    notifyArrivals();
  } catch (error) { if (state) notice(error.message); }
}

function showView(name) {
  view = name;
  if (name === "settings") loadConfig().catch(error => notice(error.message));
  document.querySelectorAll(".view").forEach(section => { section.hidden = section.id !== `view-${name}`; });
  document.querySelectorAll("nav button").forEach(button => button.classList.toggle("selected", button.dataset.view === name));
}

function reasonTone(reason) {
  if (/failing|changes requested/i.test(reason)) return "bad";
  if (/ready to merge/i.test(reason)) return "good";
  if (/review requested|need a reply|rsvp|groom a ticket|^(highest|high|critical|blocker)$/i.test(reason)) return "act";
  return "";
}

function dueCell(item) {
  if (!item.due_date) return "";
  const msLeft = new Date(`${item.due_date}T23:59:59`).getTime() - Date.now();
  const tone = msLeft < 0 ? "late" : msLeft < 2 * 86400000 ? "soon" : "";
  const day = new Date(`${item.due_date}T12:00:00`).toLocaleDateString(undefined, {month:"short", day:"numeric"});
  return `<span class="due ${tone}" title="Due ${esc(item.due_date)}">${esc(day)}</span>`;
}

function timedMeetings() {
  return state.items.filter(item => item.source === "calendar" && item.status === "open" && !item.all_day && new Date(item.ends_at).getTime() > Date.now())
    .sort((a,b) => new Date(a.starts_at) - new Date(b.starts_at));
}

function snoozeOptions() {
  const now = new Date();
  const at = (day, hour) => { const value = new Date(day); value.setHours(hour, 0, 0, 0); return value; };
  const options = [];
  if (now < at(now, 13)) options.push(["This afternoon", at(now, 13)]);
  else if (now < at(now, 16)) options.push(["Later this afternoon", at(now, 16)]);
  const next = new Date(now);
  do { next.setDate(next.getDate() + 1); } while ([0, 6].includes(next.getDay()));
  const isTomorrow = Math.round((at(next, 0) - at(now, 0)) / 86400000) === 1;
  options.push([isTomorrow ? "Tomorrow" : next.toLocaleDateString(undefined, {weekday:"long"}), at(next, 9)]);
  const meeting = timedMeetings()[0];
  if (meeting) options.push([`After ${meeting.title.slice(0, 28)}`, new Date(meeting.ends_at)]);
  return options;
}

function snoozeMenu() {
  return `<div class="snooze-menu" role="group" aria-label="Snooze until"><span class="muted">Snooze until</span>${snoozeOptions().map(([label, when]) => `<button data-snooze-until="${esc(when.toISOString())}">${esc(label)}</button>`).join("")}</div>`;
}

function briefList(heading, items) {
  return items.length ? `<h4>${heading}</h4><ul>${sortItems([...items], null).slice(0, 8).map(item => `<li>${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a>` : esc(item.title)}${item.reason || item.source_status ? ` <span class="muted">${esc(item.source_status || item.reason)}</span>` : ""}</li>`).join("")}${items.length > 8 ? `<li class="muted">${items.length - 8} more</li>` : ""}</ul>` : "";
}

function briefHtml(brief) {
  const body = briefList("Tickets", brief.tickets) + briefList("Pull requests", brief.pull_requests) + briefList("Action items", brief.action_items);
  return `<div class="brief">${body || '<span class="muted">Nothing in your list mentions this meeting yet.</span>'}</div>`;
}

async function toggleBrief(key) {
  if (briefOpen === key) briefOpen = null;
  else {
    if (!briefs.has(key)) briefs.set(key, await api(`/api/brief?key=${encodeURIComponent(key)}`));
    briefOpen = key;
  }
  renderMine();
}

// Free time before the next meeting today, so the morning plan shows how long a focused block can run.
function focusGap(meetings) {
  const endOfDay = new Date();
  endOfDay.setHours(23, 59, 59, 999);
  const today = meetings.filter(item => new Date(item.starts_at) <= endOfDay);
  if (!today.length) return "";
  const start = new Date(today[0].starts_at).getTime();
  if (start > Date.now()) return `Free ${duration(start - Date.now())} until ${clock(start)}`;
  let busyUntil = new Date(today[0].ends_at).getTime();
  for (const item of today.slice(1)) if (new Date(item.starts_at).getTime() <= busyUntil) busyUntil = Math.max(busyUntil, new Date(item.ends_at).getTime());
  return `In a meeting until ${clock(busyUntil)}`;
}

function renderNextStrip() {
  const meetings = timedMeetings();
  const meeting = meetings[0];
  if (!meeting) { $("next-strip").innerHTML = onCallStrip() + '<span class="muted">No meetings in the next two weeks</span>'; return; }
  const startsToday = new Date(meeting.starts_at).toDateString() === new Date().toDateString();
  const when = startsToday ? `${until(meeting.starts_at)} · ${clock(meeting.starts_at)} - ${clock(meeting.ends_at)}` : eventTime(meeting);
  const gap = focusGap(meetings);
  $("next-strip").innerHTML = onCallStrip() + `<div class="strip-row" data-key="${esc(meeting.key)}">${icon("meeting")}<span class="strip-label">Next</span><a href="${esc(meeting.url)}" target="_blank" rel="noopener noreferrer">${esc(meeting.title)}</a><span class="muted">${esc(when)}</span>${meeting.source_status ? `<span class="reason act">${esc(meeting.source_status)}</span>` : ""}${gap ? `<span class="gap">${esc(gap)}</span>` : ""}<button data-action="brief" aria-expanded="${briefOpen === meeting.key}">${icon("brief")}Brief</button></div>${briefOpen === meeting.key && briefs.has(meeting.key) ? briefHtml(briefs.get(meeting.key)) : ""}`;
}

function onCallStrip() {
  const shift = state.on_call;
  if (!shift?.current) return "";
  const flagged = (state.oncall || []).filter(item => item.attention.length).length;
  return `<div class="strip-row on-call-strip"><span class="strip-label">On call</span><span>until ${esc(shiftEnd(shift))}</span>${flagged ? `<span class="reason act">${flagged} need${flagged === 1 ? "s" : ""} you</span>` : ""}<button data-view="oncall">Open</button></div>`;
}

const shiftEnd = (shift) => new Date(shift.ends_at).toLocaleString(undefined, {weekday:"short", day:"numeric", month:"short", hour:"numeric", minute:"2-digit"});

function oncallRow(item) {
  const attention = item.attention.map(reason => `<span class="reason ${/overdue|unassigned/i.test(reason) ? "act" : ""}">${esc(reason)}</span>`).join(" ");
  return `<tr class="row" data-key="${esc(item.key)}"><td class="title-cell">${titleCell(item)}</td><td>${attention}</td><td class="muted">${esc(item.source_status)}</td><td><span class="reason ${reasonTone(item.reason)}">${esc(item.reason)}</span></td><td class="muted">${esc(item.owner)}</td><td class="age-cell">${ageCell(item)}</td></tr>`;
}

function renderOnCall() {
  const shift = state.on_call;
  const epic = state.oncall_epic;
  $("oncall-count").textContent = shift?.current ? (state.oncall || []).filter(item => item.attention.length).length || "" : "";
  $("oncall-shift").textContent = !shift ? "You are not on call in the next three weeks."
    : shift.current ? `You are on call until ${shiftEnd(shift)} (${shift.schedule}).`
    : `Your next shift starts ${new Date(shift.starts_at).toLocaleString(undefined, {weekday:"short", day:"numeric", month:"short", hour:"numeric", minute:"2-digit"})} (${shift.schedule}).`;
  $("oncall-epic").innerHTML = epic ? `<a href="${esc(epic.url)}" target="_blank" rel="noopener noreferrer">${esc(epic.key)} ${esc(epic.title)}</a>` : "not found yet. Sync to look for it";
  const items = sortItems([...(state.oncall || [])], null);
  const flagged = items.filter(item => item.attention.length);
  const rest = items.filter(item => !item.attention.length);
  const shownRest = oncallAll ? rest : rest.slice(0, ONCALL_PAGE);
  const columns = '<tr><th scope="col">Title</th><th scope="col">Attention</th><th scope="col">Status</th><th scope="col">Priority</th><th scope="col">Assignee</th><th scope="col">Age</th></tr>';
  $("oncall-attention").querySelector("thead").innerHTML = columns;
  $("oncall-attention").querySelector("tbody").innerHTML = flagged.map(oncallRow).join("") || '<tr class="empty-row"><td colspan="6">Nothing here needs you right now.</td></tr>';
  $("oncall-rest-count").textContent = rest.length;
  $("oncall-rest").querySelector("thead").innerHTML = columns;
  $("oncall-rest").querySelector("tbody").innerHTML = shownRest.map(oncallRow).join("");
  $("oncall-more").innerHTML = rest.length > shownRest.length ? `<button class="more" data-more="oncall">Show all ${rest.length}</button>` : "";
}

const actionable = () => state.items.filter(item => ["open","proposed"].includes(item.status));
const awakeOpen = () => state.items.filter(item => item.status === "open" && !snoozed(item));

const chips = {
  needs: ["Needs me", item => item.lane === "needs_me"],
  waiting: ["Waiting", item => item.lane === "waiting"],
  upnext: ["Up next", item => item.up_next],
  aged: ["Over 7 days", item => item.source !== "calendar" && item.lane !== "waiting" && ageMs(item) > WEEK],
  done: ["Probably done", item => item.close_suggested],
  snoozed: ["Snoozed", snoozed],
};

function renderChips() {
  const open = state.items.filter(item => item.status === "open");
  const counts = Object.fromEntries(Object.entries(chips).map(([key, [, matches]]) => [key, open.filter(item => matches(item) && (key === "snoozed" || !snoozed(item))).length]));
  $("chips").innerHTML = Object.entries(chips).filter(([key]) => counts[key] || chip === key || !["done", "snoozed"].includes(key))
    .map(([key, [label]]) => `<button class="chip ${chip === key ? "active" : ""} chip-${key}" data-chip="${key}" aria-pressed="${chip === key}">${label}<strong>${counts[key]}</strong></button>`).join("");
}

function matchesFilters(item) {
  const query = $("search").value.trim().toLowerCase();
  const type = $("type-filter").value;
  return (!type || typeOf(item) === type) &&
    (!query || `${item.title} ${item.project} ${item.list_name} ${item.parent_title} ${item.note} ${item.reason}`.toLowerCase().includes(query));
}

function whereText(item) {
  if (item.source === "calendar") return "";
  if (item.source === "jira") return item.parent_title ? `${item.list_name} · ${item.parent_title}` : item.project;
  return item.project || item.list_name;
}

function whyCell(item) {
  const parts = [];
  if (item.reason && item.reason !== "Primary calendar") parts.push(`<span class="reason ${reasonTone(item.reason)}">${esc(item.reason)}</span>`);
  const detail = [item.issue_type, item.source_status === "Open" ? "" : item.source_status].filter(Boolean).join(" · ");
  if (detail) parts.push(`<span class="muted">${esc(detail)}</span>`);
  if (item.checks_detail) parts.push(item.checks_url
    ? `<a class="checks" href="${esc(item.checks_url)}" target="_blank" rel="noopener noreferrer">${esc(item.checks_detail)}</a>`
    : `<span class="checks">${esc(item.checks_detail)}</span>`);
  if (item.linked_status && !item.close_suggested) parts.push(`<span class="linked-status">${esc(item.linked_status)}</span>`);
  if (item.close_suggested) parts.push(`<span class="close-signal">${esc(item.close_hint || "You replied")}. Done?</span>`);
  if (snoozed(item)) parts.push(`<span class="back">Back ${esc(new Date(item.snoozed_until).toLocaleString(undefined, {weekday:"short", hour:"numeric", minute:"2-digit"}))}</span>`);
  return parts.join(" ");
}

function titleCell(item) {
  // App links (claude://, codex://, cursor://) hand off to the app; a new tab would stay blank.
  const newTab = /^https?:/.test(item.url) ? ' target="_blank" rel="noopener noreferrer"' : "";
  const title = item.url ? `<a class="item-title" href="${esc(item.url)}"${newTab}>${esc(item.title)}</a>` : `<span class="item-title">${esc(item.title)}</span>`;
  const linked = (state.linked?.[item.key] || []).map(key => state.items.find(found => found.key === key)).filter(Boolean);
  const asks = linked.length ? `<ul class="linked">${linked.map(ask => `<li>${icon(TYPE_ICON[typeOf(ask)])}${ask.url ? `<a href="${esc(ask.url)}" target="_blank" rel="noopener noreferrer">${esc(ask.title)}</a>` : esc(ask.title)}</li>`).join("")}</ul>` : "";
  return title + (item.note ? `<div class="note">${esc(item.note)}</div>` : "") + asks;
}

function typeCell(item) {
  return `<span class="type type-${typeOf(item)}" title="${esc(label(item.source))}">${icon(TYPE_ICON[typeOf(item)])}${esc(typeLabel(item))}</span>`;
}

function ageCell(item) {
  if (item.source === "calendar") return `<span class="age" title="${esc(eventTime(item))}">${until(item.starts_at)}</span>`;
  return `<span class="age ${ageMs(item) > WEEK ? "old" : ""}" title="Since ${esc(date(stamp(item)))}">${ageLabel(item)}</span>`;
}

const iconButton = (action, label, name, extra = "") => `<button class="act" data-action="${action}" aria-label="${label}" title="${label}"${extra}>${icon(name)}</button>`;

// The main action keeps its label; the rest are icons with tooltips so the row stays one line.
function actionButtons(item) {
  const buttons = [];
  if (item.status === "proposed") buttons.push(`<button data-action="open" class="tonal">${icon("done")}Accept</button>`);
  if (item.status === "open" && !item.live) buttons.push(`<button data-action="done" class="tonal">${icon("done")}Done</button>`);
  if (item.source === "calendar") buttons.push(iconButton("brief", "Meeting brief", "brief", ` aria-expanded="${briefOpen === item.key}"`));
  else buttons.push(snoozed(item)
    ? `<button class="act" data-snooze-until="" aria-label="Wake now" title="Wake now">${icon("snooze")}</button>`
    : iconButton("snooze", "Snooze", "snooze"));
  buttons.push(iconButton("dismissed", "Dismiss", "dismiss"), iconButton("edit", "Edit", "manual"));
  return buttons.join("");
}

// The colored stripe shows Needs me or Waiting at a glance.
function rowTone(item) {
  if (item.lane === "waiting") return "wait";
  const tone = reasonTone(item.reason || "");
  return tone === "bad" || tone === "good" || tone === "act" ? tone : item.lane === "needs_me" ? "need" : "";
}

function detailRow(item, columns) {
  const parts = [];
  if (snoozeOpen === item.key) parts.push(snoozeMenu());
  if (briefOpen === item.key && briefs.has(item.key)) parts.push(briefHtml(briefs.get(item.key)));
  return parts.length ? `<tr class="detail" data-detail="${esc(item.key)}"><td colspan="${columns}">${parts.join("")}</td></tr>` : "";
}

function workRow(item) {
  const pin = `<button class="pin ${item.up_next ? "active" : ""}" data-action="pin" aria-label="${item.up_next ? "Remove from" : "Add to"} up next" aria-pressed="${item.up_next}">${item.up_next ? "★" : "☆"}</button>`;
  return `<tr class="row" tabindex="0" data-key="${esc(item.key)}" data-source="${esc(item.source)}" data-tone="${rowTone(item)}"><td class="star">${pin}</td><td class="type-cell">${typeCell(item)}</td><td class="title-cell">${titleCell(item)}</td><td class="why">${whyCell(item)}</td><td class="where">${esc(whereText(item))}</td><td class="due-cell">${dueCell(item)}</td><td class="age-cell">${ageCell(item)}</td><td class="actions">${actionButtons(item)}</td></tr>${detailRow(item, 8)}`;
}

// Triage has no Why column, so only reasons worth a highlight and linked status ride under the title.
function triageSignals(item) {
  const tone = reasonTone(item.reason || "");
  return (tone ? `<span class="reason ${tone}">${esc(item.reason)}</span>` : "") + (item.linked_status ? `<span class="linked-status">${esc(item.linked_status)}</span>` : "");
}

const quoted = (key) => `“${esc(state.items.find(item => item.key === key)?.title || key)}”`;
const targetTitle = (reference) => state.items.find(item => item.key === `jira:${reference}` || item.url === reference)?.title || "";

function describeSuggestion(suggestion) {
  const [first, ...rest] = suggestion.keys;
  const others = rest.length ? `<ul class="linked">${rest.map(key => `<li>${quoted(key)}</li>`).join("")}</ul>` : "";
  if (suggestion.kind === "merge") return `Merge ${suggestion.keys.length} items into ${suggestion.title ? `“${esc(suggestion.title)}”` : quoted(first)}<ul class="linked"><li>${quoted(first)}</li></ul>${others}`;
  if (suggestion.kind === "link") return `Fold ${quoted(first)} under ${esc(suggestion.reference)}${targetTitle(suggestion.reference) ? ` ${esc(targetTitle(suggestion.reference))}` : ""}`;
  if (suggestion.kind === "retitle") return `Rename ${quoted(first)} to “${esc(suggestion.title)}”`;
  if (suggestion.kind === "due") return `Set ${quoted(first)} due ${esc(new Date(`${suggestion.due_date}T12:00:00`).toLocaleDateString(undefined, {weekday:"short", month:"short", day:"numeric"}))}`;
  return `Close ${quoted(first)}${others}`;
}

function renderCleanup() {
  const suggestions = state.suggestions || [];
  $("cleanup-section").hidden = !suggestions.length;
  $("cleanup-count").textContent = suggestions.length;
  $("cleanup").innerHTML = suggestions.map(suggestion => `<div class="suggestion"><span class="reason">${esc(suggestion.kind)}</span><div class="suggestion-main">${describeSuggestion(suggestion)}<span class="muted">${esc(suggestion.why)}</span></div><div class="suggestion-actions"><button data-suggestion="${esc(suggestion.id)}" data-accept="true">Accept</button><button data-suggestion="${esc(suggestion.id)}" data-accept="false">Reject</button></div></div>`).join("");
}

// Sequential, because a merge and a close can touch items another suggestion was checked against.
async function acceptAllSuggestions() {
  let failed = 0;
  for (const suggestion of state.suggestions || []) {
    try { await api("/api/suggestions", "POST", {id: suggestion.id, accept: true}); }
    catch (error) { failed += 1; }
  }
  await load();
  if (failed) notice(`Could not apply ${failed} suggestion${failed === 1 ? "" : "s"}.`);
}

function triageRow(item) {
  return `<tr class="row" tabindex="0" data-key="${esc(item.key)}" data-source="${esc(item.source)}"><td class="type-cell">${typeCell(item)}</td><td class="title-cell">${titleCell(item)}${triageSignals(item)}</td><td class="where">${esc(whereText(item))}</td><td class="age-cell">${ageCell(item)}</td><td class="actions always">${actionButtons(item)}</td></tr>${detailRow(item, 5)}`;
}

// A meeting's age is negative: how long until it starts.
const ageValue = (item) => item.source === "calendar" ? Date.now() - new Date(item.starts_at).getTime() : ageMs(item);
const sortValues = {
  type: item => typeLabel(item),
  title: item => item.title.toLowerCase(),
  why: item => (item.reason || "").toLowerCase(),
  where: item => whereText(item).toLowerCase(),
  due: item => item.due_date || "9999",
  age: ageValue,
};

// With no column chosen: starred, then Needs me, then everything else, then Waiting.
// Within each, most urgent first, then meetings soonest first, then everything else newest first.
const rank = (item) => item.up_next ? 0 : item.lane === "needs_me" ? 1 : item.lane === "waiting" ? 3 : 2;
// Jira puts the priority name in reason; other sources put their own signal there, read through reasonTone.
const JIRA_PRIORITY = {blocker: 0, critical: 0, highest: 0, high: 1, medium: 2, low: 3, lowest: 4};
const urgency = (item) => JIRA_PRIORITY[(item.reason || "").toLowerCase()] ?? {bad: 0, act: 1}[reasonTone(item.reason || "")] ?? 2;
const isMeeting = (item) => item.source === "calendar";
function defaultOrder(a, b) {
  return rank(a) - rank(b) || urgency(a) - urgency(b) || isMeeting(b) - isMeeting(a)
    || (isMeeting(a) ? new Date(a.starts_at) - new Date(b.starts_at) : new Date(stamp(b)) - new Date(stamp(a)));
}

function sortItems(items, sort) {
  if (!sort) return items.sort(defaultOrder);
  const value = sortValues[sort.column];
  const sign = sort.direction === "asc" ? 1 : -1;
  return items.sort((a, b) => {
    const [x, y] = [value(a), value(b)];
    return (x < y ? -1 : x > y ? 1 : 0) * sign || defaultOrder(a, b);
  });
}

// A column key sorts; "" is the star column, which restores the default order; null is the actions column.
function headerRow(columns, sort) {
  return `<tr>${columns.map(([key, label]) => {
    if (key === null) return '<th scope="col" class="actions-head"><span class="visually-hidden">Actions</span></th>';
    if (key === "") return '<th scope="col"><button class="sort reset" data-sort="" title="Default order">★</button></th>';
    const direction = sort?.column === key ? (sort.direction === "asc" ? "ascending" : "descending") : "none";
    return `<th scope="col" aria-sort="${direction}"><button class="sort" data-sort="${key}">${label}${direction === "none" ? "" : `<span class="arrow">${sort.direction === "asc" ? "▲" : "▼"}</span>`}</button></th>`;
  }).join("")}</tr>`;
}

const visibleRows = (scope = "#view-mine") => [...document.querySelectorAll(`${scope} tr.row`)];

// Remember the table too: an accepted proposal moves to the work table, but the cursor should stay in triage.
function captureFocus(node) {
  const found = node?.closest?.("#view-mine tr.row");
  const table = found?.closest("table").id;
  return found ? {key: found.dataset.key, table, index: visibleRows(`#${table}`).indexOf(found)} : null;
}

function renderMine() {
  if (!state) return;
  const hint = focusHint || captureFocus(document.activeElement);
  focusHint = null;
  renderNextStrip();
  renderChips();
  renderCleanup();
  // Asks folded under the ticket or pull request they name show inside that row instead of their own.
  const folded = new Set(Object.values(state.linked || {}).flat());
  const matching = actionable().filter(item => !folded.has(item.key) && matchesFilters(item));
  const chipMatches = chip ? chips[chip][1] : item => !snoozed(item);
  const work = sortItems(matching.filter(item => item.status === "open" && chipMatches(item)), workSort);
  const shownWork = workAll ? work : work.slice(0, WORK_PAGE);
  $("work").querySelector("thead").innerHTML = headerRow([["", ""], ["type", "Type"], ["title", "Title"], ["why", "Why"], ["where", "Where"], ["due", "Due"], ["age", "Age"], [null, ""]], workSort);
  $("work").querySelector("tbody").innerHTML = shownWork.map(workRow).join("") || `<tr class="empty-row"><td colspan="8">${chip || $("search").value || $("type-filter").value ? "Nothing matches these filters." : !state.sources.length ? 'Nothing is switched on yet. Pick the sources you use in <button class="link" data-view="settings">Settings</button>, or add an item yourself.' : 'You are all caught up. Add an item or turn on another source in <button class="link" data-view="settings">Settings</button>.'}</td></tr>`;
  $("work-more").innerHTML = work.length > shownWork.length ? `<button class="more" data-more="work">Show all ${work.length}</button>` : "";
  const triage = sortItems(matching.filter(item => item.status === "proposed" && !snoozed(item)), triageSort);
  const shownTriage = triageAll ? triage : triage.slice(0, TRIAGE_PAGE);
  $("triage-section").hidden = !triage.length;
  $("triage-count").textContent = triage.length;
  $("triage").querySelector("thead").innerHTML = headerRow([["type", "Type"], ["title", "Title"], ["where", "From"], ["age", "Age"], [null, ""]], triageSort);
  $("triage").querySelector("tbody").innerHTML = shownTriage.map(triageRow).join("");
  $("triage-more").innerHTML = triage.length > shownTriage.length ? `<button class="more" data-more="triage">Show all ${triage.length}</button>` : "";
  document.querySelectorAll("[data-bulk]").forEach(button => { button.disabled = !shownTriage.length; button.dataset.count = shownTriage.length; });
  if (hint) {
    const rows = visibleRows(`#${hint.table}`);
    (rows.find(node => node.dataset.key === hint.key) || rows[Math.min(hint.index, rows.length - 1)])?.focus({preventScroll: true});
  }
}

function row(item, actions = true, team = false) {
  const terminal = ["done","dismissed"].includes(item.status);
  const newTab = /^https?:/.test(item.url) ? ' target="_blank" rel="noopener noreferrer"' : "";
  const title = item.url ? `<a class="item-title" href="${esc(item.url)}"${newTab}>${esc(item.title)}</a>` : `<span class="item-title">${esc(item.title)}</span>`;
  const activityDate = item.source === "jira" ? item.updated_at : item.opened_at;
  const activity = team && activityDate ? `<span title="${esc(date(activityDate))}">${item.source === "jira" ? "Updated" : "Created"} ${esc(new Date(activityDate).toLocaleDateString(undefined, {month:"short", day:"numeric", year:"numeric"}))}</span>` : "";
  const meta = [
    typeCell(item),
    item.reason ? `<span class="reason ${reasonTone(item.reason)}">${esc(item.reason)}</span>` : "",
    item.source_status ? `<span>${esc(item.source_status)}</span>` : "",
    whereText(item) ? `<span>${esc(whereText(item))}</span>` : "",
    terminal ? `<span>Closed ${esc(date(item.closed_at))}</span>` : "",
    activity,
  ].join("");
  const ageText = `<span class="age ${ageMs(item) > WEEK && !terminal ? "old" : ""}" title="Since ${esc(date(stamp(item)))}">${ageLabel(item)}</span>`;
  return `<article class="item-row" data-key="${esc(item.key)}" data-source="${esc(item.source)}"><div class="item-main">${title}<div class="item-meta">${meta}</div>${item.note ? `<div class="item-meta">${esc(item.note)}</div>` : ""}</div>${ageText}</article>`;
}

const teamMatches = {
  jira: ["Tickets", item => item.source === "jira"],
  prs: ["Pull requests", item => ["github", "bitbucket"].includes(item.source)],
  aged: ["Over 7 days", item => ageMs(item) > WEEK],
};
const teamSorts = {
  active: () => 0,
  jira: (a, b) => b.jira - a.jira,
  prs: (a, b) => b.prs - a.prs,
  aged: (a, b) => b.aged - a.aged,
};

function teamGroups(owner) {
  const focus = teamFocus.get(owner.id);
  const groups = [
    ["progress", "Jira in progress", item => item.source === "jira" && item.source_category === "indeterminate"],
    ["other", "Other Jira work", item => item.source === "jira" && item.source_category !== "indeterminate"],
    ["prs", "Pull requests", item => ["github", "bitbucket"].includes(item.source)],
  ];
  const focusBar = focus ? `<div class="team-focus">Showing ${teamMatches[focus][0].toLowerCase()} only<button data-team-clear="${esc(owner.id)}">Show all</button></div>` : "";
  return focusBar + groups.map(([key, title, matches]) => {
    const items = owner.items.filter(item => matches(item) && (!focus || teamMatches[focus][1](item))).sort((first, second) =>
      (second.updated_at || second.opened_at || second.first_seen).localeCompare(first.updated_at || first.opened_at || first.first_seen));
    if (!items.length) return "";
    const limitKey = `${owner.id}:${key}`;
    const limit = teamLimits.get(limitKey) || 6;
    return `<section class="team-work-group" data-team-group="${key}"><h3>${title}<span class="group-count">${items.length}</span></h3>${items.slice(0,limit).map(item => row(item,false,true)).join("")}${items.length > limit ? `<button class="team-more" data-team-more="${esc(limitKey)}">Show ${Math.min(6,items.length-limit)} more (${items.length-limit} remaining)</button>` : ""}</section>`;
  }).join("");
}

function renderTeam() {
  const open = new Set([...$("team").querySelectorAll("details[open]")].map(node => node.dataset.owner));
  if (teamForceOpen) open.add(teamForceOpen);
  const team = [...state.team].sort(teamSorts[teamSort]);
  const maximum = Math.max(1,...team.map(owner => owner.items.length));
  const count = (owner, kind, value, label) => `<button class="number work-${kind === "jira" ? "tickets" : kind === "prs" ? "prs" : "aged"} ${teamFocus.get(owner.id) === kind ? "active" : ""}" data-team-focus="${kind}" data-owner="${esc(owner.id)}" aria-pressed="${teamFocus.get(owner.id) === kind}" aria-label="Show ${label} for ${esc(owner.name)}">${value}<small>${label}</small></button>`;
  document.querySelectorAll("[data-team-sort]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.teamSort === teamSort)));
  $("team").innerHTML = team.map(owner => `<details class="team-row" data-owner="${esc(owner.id)}" ${open.has(owner.id) ? "open" : ""}><summary><span class="team-name">${esc(owner.name)}<small>${owner.active} Jira in progress · ${owner.items.length} work items</small></span><span class="workbar" aria-hidden="true"><span></span><span class="pr"></span></span>${count(owner, "jira", owner.jira, "Tickets")}${count(owner, "prs", owner.prs, "PRs")}${count(owner, "aged", owner.aged, "Over 7d")}</summary><div class="team-details">${teamGroups(owner)}<div class="team-roster-action"><button data-team-hide="${esc(owner.id)}" data-team-name="${esc(owner.name)}">Hide member</button></div></div></details>`).join("") || '<div class="empty">No recent work for this team yet. Check the Jira scope above, or whether anyone is hidden.</div>';
  // Widths are assigned as DOM properties under the restrictive page CSP.
  $("team").querySelectorAll(".workbar").forEach((bar,index) => {
    bar.children[0].style.width = `${team[index].jira/maximum*100}%`;
    bar.children[1].style.width = `${team[index].prs/maximum*100}%`;
  });
  if (teamForceOpen) {
    $("team").querySelector(`details[data-owner="${CSS.escape(teamForceOpen)}"]`)?.scrollIntoView({block: "nearest"});
    teamForceOpen = null;
  }
  const exclusions = state.team_exclusions || [];
  $("team-exclusions").hidden = !exclusions.length;
  $("team-exclusion-count").textContent = exclusions.length;
  $("team-exclusion-list").innerHTML = exclusions.map(owner => `<div class="excluded-member"><span>${esc(owner.name)}</span><button data-team-restore="${esc(owner.id)}" data-team-name="${esc(owner.name)}">Restore member</button></div>`).join("");
  $("team-coverage").textContent = state.coverage;
  $("scope-label").textContent = state.team_jql || "Waiting for Jira";
  $("scope-origin").textContent = state.team_scope_origin;
  if (document.activeElement !== $("team-jql")) $("team-jql").value = state.team_jql;
}

function renderHistory() {
  if (!state) return;
  const items = state.items.filter(item => item.status === $("history-status").value && item.title.toLowerCase().includes($("history-search").value.toLowerCase()));
  items.sort((a,b) => b.closed_at.localeCompare(a.closed_at));
  const days = Map.groupBy(items, item => new Date(item.closed_at).toLocaleDateString(undefined, {weekday:"long", month:"short", day:"numeric", year:"numeric"}));
  $("history").innerHTML = [...days].map(([day, found]) => `<h3 class="day">${esc(day)}<span class="group-count">${found.length}</span></h3>${found.map(item => row(item,false)).join("")}`).join("") || '<div class="empty">Nothing here yet.</div>';
}

const NO_SCHEDULE_STALE_SECONDS = 3600;

// Saved results are only worth a warning when they are behind: the last sync failed, or the data
// is older than twice the source's own schedule (an hour when it has none).
function renderSnapshotNotice() {
  const paused = state.auto_refresh === false;
  const behind = Object.entries(state.snapshots || {}).flatMap(([source, snapshot]) => {
    const health = state.sources.find(candidate => candidate.source === source);
    if (!snapshot.saved_at || health?.state === "refreshing") return [];
    const failed = health?.state === "error";
    const interval = paused ? null : state.refresh_intervals?.[source];
    const staleAfter = (interval ? interval * 2 : NO_SCHEDULE_STALE_SECONDS) * 1000;
    return failed || Date.now() - new Date(snapshot.saved_at).getTime() > staleAfter
      ? [`${label(source)} (${failed ? "sync failed, " : ""}${ago(snapshot.saved_at)})`] : [];
  });
  $("snapshot-notice").hidden = behind.length === 0;
  if (behind.length) $("snapshot-notice").textContent = `Some results are out of date: ${behind.join(", ")}. Sync to refresh them.`;
}

function renderSettings() {
  $("auto-toggle").checked = state.auto_refresh !== false;
  $("alerts-toggle").checked = alertsEnabled();
  $("alerts-toggle").disabled = !("Notification" in window);
  $("alerts-note").textContent = !("Notification" in window) ? "This browser does not support notifications."
    : Notification.permission === "denied" ? "Your browser is blocking notifications for this page. Allow them in the site settings, then turn this on." : "Notifications only arrive while worktray is open in a tab.";
}

function render() {
  const unhealthy = state.sources.filter(source => source.state === "error");
  $("mine-count").textContent = awakeOpen().filter(item => item.lane !== "waiting").length || "";
  $("connection-count").textContent = unhealthy.length || "";
  const latest = state.sources.map(source => source.last_success).filter(Boolean).sort().at(-1);
  $("refresh-label").textContent = state.refreshing ? "Syncing" : "Sync";
  $("refresh").classList.toggle("syncing", state.refreshing);
  $("refresh").disabled = state.refreshing;
  $("refresh").title = (latest ? `Synced ${ago(latest)} · ` : "") + (state.auto_refresh === false ? "Background sync is off · " : "") + "Sync all your sources now";
  const selectedType = $("type-filter").value;
  const groups = new Set([...state.sources.map(source => state.source_groups?.[source.source]).filter(Boolean), "manual"]);
  $("type-filter").innerHTML = '<option value="">All types</option>' + [...groups].map(group => `<option value="${esc(group)}">${esc(groupLabel(group))}</option>`).join("");
  document.querySelector('nav [data-view="oncall"]').hidden = !state.views?.oncall;
  document.querySelector('nav [data-view="team"]').hidden = !state.views?.team;
  $("type-filter").value = selectedType;
  renderMine(); renderTeam(); renderOnCall(); renderHistory(); renderSnapshotNotice(); renderSettings();
  $("sources").innerHTML = (state.sources.length ? "" : '<p class="muted">No sources are on yet. Pick the ones you use in <button class="link" data-view="settings">Settings</button>.</p>') + state.sources.map(source => `<div class="source-row"><strong>${esc(label(source.source))}</strong><span class="badge ${esc(source.state)}">${esc(source.state.replaceAll("_"," "))}</span><div class="source-detail">${esc(source.detail)}<time>${source.last_success ? `Last synced ${esc(date(source.last_success))}` : "Not synced yet"}${source.stale_since && source.last_success ? ` · Out of date since ${esc(date(source.stale_since))}` : ""}${state.refresh_intervals?.[source.source] ? ` · Every ${intervalLabel(state.refresh_intervals[source.source])}` : " · Only when you sync"}</time></div><button data-refresh="${esc(source.source)}" ${source.state === "refreshing" ? "disabled" : ""}>Sync now</button></div>`).join("");
  $("metrics").innerHTML = Object.entries(state.metrics).map(([source,counts]) => `<div class="metrics-row"><strong>${esc(label(source))}</strong><span>${counts.accepted} accepted</span><span>${counts.dismissed} dismissed</span><span>${Math.round(counts.accepted/(counts.accepted+counts.dismissed)*100)}% accepted</span></div>`).join("") || '<p class="muted">Accept or dismiss a few suggestions and you will see how useful each source is.</p>';
}

function openEditor(item = null) {
  editing = item; newKey = crypto.randomUUID();
  $("item-heading").textContent = item ? "Edit item" : "Add an item";
  $("item-title").value = item?.title || ""; $("item-title").disabled = Boolean(item?.live);
  $("item-list").value = item?.list_name || ""; $("item-note").value = item?.note || "";
  $("item-dialog").showModal();
}

async function refresh(sources) {
  await api("/api/refresh","POST",{sources: sources || null});
  await load();
}

async function patchItem(item, patch) {
  await api("/api/items","PATCH",{key:item.key,...patch});
}

// The server has no bulk route, so send a handful at a time and reload once at the end.
async function bulkTriage(status) {
  const shown = [...$("triage").querySelectorAll("tbody tr.row")].map(node => state.items.find(item => item.key === node.dataset.key)).filter(Boolean);
  if (!shown.length || !confirm(`${status === "open" ? "Accept" : "Dismiss"} all ${shown.length} shown?`)) return;
  let failed = 0;
  for (let index = 0; index < shown.length; index += 8) {
    const results = await Promise.allSettled(shown.slice(index, index + 8).map(item => patchItem(item, {status})));
    failed += results.filter(result => result.status === "rejected").length;
  }
  await load();
  if (failed) notice(`Could not update ${failed} of ${shown.length}.`);
}

document.addEventListener("click", async event => {
  const button = event.target.closest("button");
  if (!button) return;
  try {
    if (button.dataset.view) { showView(button.dataset.view); return; }
    if (button.id === "help-open") { $("help-dialog").showModal(); return; }
    if (button.dataset.chip !== undefined) {
      chip = chip === button.dataset.chip ? "" : button.dataset.chip;
      workAll = false;
      renderMine();
      return;
    }
    if (button.dataset.sort !== undefined) {
      const inTriage = Boolean(button.closest("#triage"));
      const current = inTriage ? triageSort : workSort;
      const next = !button.dataset.sort ? null
        : current?.column === button.dataset.sort ? {column: current.column, direction: current.direction === "asc" ? "desc" : "asc"}
        : {column: button.dataset.sort, direction: button.dataset.sort === "age" ? "desc" : "asc"};
      if (inTriage) triageSort = next || DEFAULT_TRIAGE_SORT; else workSort = next;
      renderMine();
      return;
    }
    if (button.dataset.more === "oncall") { oncallAll = true; renderOnCall(); return; }
    if (button.dataset.more) { if (button.dataset.more === "work") workAll = true; else triageAll = true; renderMine(); return; }
    if (button.dataset.bulk) { await bulkTriage(button.dataset.bulk); return; }
    if (button.dataset.suggestion) {
      button.disabled = true;
      await api("/api/suggestions", "POST", {id: button.dataset.suggestion, accept: button.dataset.accept === "true"});
      await load();
      return;
    }
    if (button.hasAttribute("data-cleanup-all")) { button.disabled = true; await acceptAllSuggestions(); return; }
    if (button.dataset.close) $(button.dataset.close).close();
    if (button.dataset.refresh) await refresh([button.dataset.refresh]);
    if (button.dataset.teamSort) { teamSort = button.dataset.teamSort; renderTeam(); return; }
    if (button.dataset.teamFocus) {
      const owner = button.dataset.owner;
      if (teamFocus.get(owner) === button.dataset.teamFocus) teamFocus.delete(owner);
      else teamFocus.set(owner, button.dataset.teamFocus);
      teamForceOpen = owner;
      renderTeam();
      return;
    }
    if (button.dataset.teamClear) { teamFocus.delete(button.dataset.teamClear); teamForceOpen = button.dataset.teamClear; renderTeam(); return; }
    if (button.dataset.teamMore) {
      teamLimits.set(button.dataset.teamMore, (teamLimits.get(button.dataset.teamMore) || 6) + 6);
      renderTeam();
    }
    if (button.dataset.teamHide || button.dataset.teamRestore) {
      button.disabled = true;
      await api("/api/team/exclusions", "POST", {owner_id:button.dataset.teamHide || button.dataset.teamRestore, name:button.dataset.teamName, excluded:Boolean(button.dataset.teamHide)});
      await load();
    }
    if (button.dataset.action || button.dataset.snoozeUntil !== undefined) {
      const key = button.closest("[data-key]")?.dataset.key || button.closest("[data-detail]")?.dataset.detail;
      const item = state.items.find(item => item.key === key);
      const action = button.dataset.action;
      // A keyboard-triggered click has no pointer, so keep the cursor on the table after the row changes.
      if (event.detail === 0) focusHint = captureFocus(button);
      if (action === "edit") { openEditor(item); return; }
      if (action === "brief") { await toggleBrief(item.key); return; }
      if (action === "snooze") { snoozeOpen = snoozeOpen === item.key ? null : item.key; renderMine(); return; }
      button.disabled = true;
      let patch;
      if (action === "pin") patch = {up_next:!item.up_next};
      else if (action) patch = {status:action};
      else patch = {snoozed_until:button.dataset.snoozeUntil};
      snoozeOpen = null;
      await patchItem(item, patch);
      await load();
    }
  } catch (error) { focusHint = null; button.disabled = false; notice(error.message); }
});

document.addEventListener("keydown", event => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "Escape" && snoozeOpen) { snoozeOpen = null; renderMine(); return; }
  if (event.target.closest?.("input, select, textarea") || document.querySelector("dialog[open]")) return;
  if (event.key === "?") { event.preventDefault(); $("help-dialog").showModal(); return; }
  if (event.key === "/") {
    event.preventDefault();
    (view === "history" ? $("history-search") : $("search")).focus();
    return;
  }
  if (view !== "mine") return;
  const rows = visibleRows();
  const current = document.activeElement?.closest?.("#view-mine tr.row");
  if (event.key === "j" || event.key === "k") {
    event.preventDefault();
    const index = current ? rows.indexOf(current) : -1;
    rows[event.key === "j" ? Math.min(index + 1, rows.length - 1) : Math.max(index - 1, 0)]?.focus();
    return;
  }
  const action = {s:"pin", a:"open", d:"done", x:"dismissed", z:"snooze", e:"edit", b:"brief"}[event.key];
  if (!action || !current) return;
  event.preventDefault();
  current.querySelector(`[data-action="${action}"]`)?.click();
});
document.addEventListener("change", async event => {
  const select = event.target.closest("select[data-interval]");
  if (!select) return;
  try {
    await api("/api/settings/refresh-interval", "POST", {source: select.dataset.interval, seconds: select.value ? Number(select.value) : null});
    await load();
  } catch (error) { notice(error.message); }
});
$("auto-toggle").onchange = async () => {
  try { await api("/api/settings/auto-refresh", "POST", {enabled: $("auto-toggle").checked}); await load(); }
  catch (error) { notice(error.message); }
};
$("alerts-toggle").onchange = async () => {
  try {
    if (!$("alerts-toggle").checked) localStorage.setItem("worktray-alerts", "off");
    else if (await Notification.requestPermission() === "granted") localStorage.setItem("worktray-alerts", "on");
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
    notice("Your browser blocked saving the alert setting.");
  }
  renderSettings();
};
$("copy-standup").onclick = async () => {
  try {
    const note = await api("/api/standup");
    $("standup-text").textContent = note.text;
    $("standup-text").hidden = false;
    await navigator.clipboard.writeText(note.text);
    notice("Standup note copied.");
  } catch (error) { notice(error instanceof DOMException ? "Copy was blocked. Select the note below instead." : error.message); }
};
$("add").onclick = () => openEditor();
$("refresh").onclick = () => refresh().catch(error => notice(error.message));
for (const id of ["search","type-filter"]) $(id).addEventListener("input", () => { workAll = false; triageAll = false; renderMine(); });
for (const id of ["history-search","history-status"]) $(id).addEventListener("input",renderHistory);
$("item-form").onsubmit = async event => {
  event.preventDefault();
  const body = {list_name:$("item-list").value,note:$("item-note").value};
  if (!editing?.live) body.title = $("item-title").value.trim();
  try {
    await api("/api/items",editing ? "PATCH" : "POST",{...body,key:editing?.key || newKey});
    $("item-dialog").close(); await load();
  } catch (error) { $("item-dialog").close(); notice(error.message); }
};
$("scope-form").onsubmit = async event => {
  event.preventDefault();
  try { await api("/api/settings","POST",{team_jql:$("team-jql").value}); await load(); }
  catch (error) { notice(error.message); }
};
new ResizeObserver(() => document.documentElement.style.setProperty("--header-height", `${document.querySelector("header").offsetHeight}px`)).observe(document.querySelector("header"));
load();
setInterval(load, 2500);
// Relative times and snooze expiry change without any new server state.
setInterval(() => { if (state && view === "mine") renderMine(); }, 60000);
