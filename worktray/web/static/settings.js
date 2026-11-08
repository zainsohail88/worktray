"use strict";
// Settings view: one card per source, built from GET /api/config. Secret values never come back
// from the server; a saved secret shows as "Saved" and is replaced by typing a new one.
let config = null;
const openCards = new Set();

async function loadConfig() {
  config = await api("/api/config");
  renderSourceSettings();
}

// The help text, then the environment variable that can set the field, shown quietly.
function fieldNote(field) {
  const variable = field.locked ? `Set by <code>${esc(field.env)}</code>` : `<code class="env" title="Environment variable">${esc(field.env)}</code>`;
  const problem = field.problem ? `<span class="bad">${esc(field.problem)}</span> ` : "";
  return `${problem}${field.help ? `${esc(field.help)} ` : ""}${variable}`;
}

// A setting that picks which program runs can't be changed from a web page; the terminal sets it.
function settingHtml(source, field) {
  const id = `field-${source.name}-${field.key}`;
  const readOnly = field.locked || field.web === false;
  return `<label for="${id}">${esc(field.label)}<input id="${id}" name="${esc(field.key)}" data-kind="setting" value="${esc(field.value)}" placeholder="${esc(field.placeholder || field.default)}" ${readOnly ? "disabled" : ""} autocomplete="off" spellcheck="false"><small class="muted">${fieldNote(field)}</small></label>`;
}

function secretHtml(source, secret) {
  const id = `field-${source.name}-${secret.key}`;
  const status = secret.problem ? secret.problem : secret.locked ? "Set by an environment variable" : secret.set ? "Saved" : "Not set";
  const tone = secret.problem ? "error" : secret.set ? "ok" : "";
  const placeholder = secret.set ? "Saved · type to replace" : "Paste it here";
  const clear = secret.set && !secret.locked ? `<button type="button" data-clear-secret="${esc(secret.key)}" data-source="${esc(source.name)}">Clear</button>` : "";
  return `<div class="secret-field"><label for="${id}">${esc(secret.label)}<input id="${id}" type="password" name="${esc(secret.key)}" data-kind="secret" placeholder="${esc(placeholder)}" ${secret.locked ? "disabled" : ""} autocomplete="new-password" spellcheck="false"></label><div class="secret-meta"><span class="badge ${tone}">${esc(status)}</span>${clear}</div><small class="muted">${fieldNote(secret)}</small></div>`;
}

function intervalHtml(source) {
  const seconds = state?.refresh_intervals?.[source.name];
  const options = (state?.refresh_choices || []).map(choice => `<option value="${choice}" ${seconds === choice ? "selected" : ""}>Every ${intervalLabel(choice)}</option>`).join("");
  return `<label class="inline">Sync<select data-interval="${esc(source.name)}" aria-label="Sync interval for ${esc(source.label)}"><option value="">Only when I sync</option>${options}</select></label>`;
}

function sourceCard(source) {
  const health = state?.sources?.find(found => found.source === source.name);
  const editable = [...source.settings, ...source.secrets].some(field => !field.locked && field.web !== false);
  const body = [
    source.available ? "" : `<p class="warn">This needs an extra package. Run <code>${esc(source.install)}</code>, then restart worktray.</p>`,
    source.uses ? `<p class="muted">Uses your ${esc(source.uses_label)} sign-in.</p>` : "",
    ...source.settings.map(field => settingHtml(source, field)),
    ...source.secrets.map(secret => secretHtml(source, secret)),
    source.enabled ? intervalHtml(source) : "",
    `<div class="card-actions">${editable ? '<button class="primary">Save</button>' : ""}${source.can_check ? `<button type="button" data-check="${esc(source.name)}">Test connection</button>` : ""}${source.can_connect ? `<button type="button" data-connect="${esc(source.name)}">Sign in</button>` : ""}${source.can_disconnect ? `<button type="button" data-disconnect="${esc(source.name)}">Sign out</button>` : ""}</div>`,
    `<p class="form-result" role="status" data-result="${esc(source.name)}"></p>`,
  ].join("");
  const badge = !source.enabled ? '<span class="badge">off</span>' : health ? `<span class="badge ${esc(health.state)}">${esc(health.state.replaceAll("_", " "))}</span>` : "";
  const lockNote = source.enabled_locked ? ' title="Set by an environment variable"' : "";
  return `<article class="source-card ${source.enabled ? "" : "off"}" data-card="${esc(source.name)}"><div class="card-head"><input type="checkbox" class="switch" data-enable="${esc(source.name)}" ${source.enabled ? "checked" : ""} ${source.enabled_locked ? "disabled" : ""}${lockNote} aria-label="${esc(source.label)} on"><div class="card-title"><strong>${esc(source.label)}</strong><small class="muted">${esc(source.description)}</small></div>${badge}</div><details data-details="${esc(source.name)}" ${openCards.has(source.name) ? "open" : ""}><summary>Configure</summary><form class="source-form" data-source-form="${esc(source.name)}" autocomplete="off">${body}</form></details></article>`;
}

function renderSourceSettings() {
  if (!config) return;
  $("source-settings").innerHTML = (config.demo ? '<p class="muted">Settings cannot be changed in the demo.</p>' : "") + config.sources.map(sourceCard).join("");
  // The demo uses made-up accounts, so its source cards are read-only.
  if (config.demo) $("source-settings").querySelectorAll("input, select, button").forEach(node => { node.disabled = true; });
}

function showResult(name, outcome) {
  const node = document.querySelector(`[data-result="${CSS.escape(name)}"]`);
  if (!node) return;
  node.textContent = outcome.detail;
  node.className = `form-result ${outcome.ok ? "good" : outcome.not_connected ? "" : "bad"}`;
}

async function runAction(name, action, waiting) {
  showResult(name, {ok: true, detail: waiting});
  const outcome = await api(`/api/config/${encodeURIComponent(name)}/${action}`, "POST");
  await loadConfig();
  showResult(name, outcome);
  if (outcome.ok && action !== "disconnect" && config.sources.find(source => source.name === name)?.enabled) await refresh([name]);
  return outcome;
}

// The server cannot assume it has a screen, so it hands the sign-in link back and the page offers it.
async function connect(name) {
  showResult(name, {ok: true, detail: "Getting the sign-in page ready"});
  let done = false;
  const running = runAction(name, "connect", "Getting the sign-in page ready").finally(() => { done = true; });
  while (!done) {
    await new Promise(resolve => setTimeout(resolve, 800));
    if (done) break;
    const {url} = await api(`/api/config/${encodeURIComponent(name)}/sign-in-link`);
    const node = document.querySelector(`[data-result="${CSS.escape(name)}"]`);
    if (url && node && /^https:\/\//.test(url) && !node.querySelector("a")) {
      node.className = "form-result";
      node.innerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open the sign-in page</a>, approve access, then come back here.`;
    }
  }
  return running;
}

document.addEventListener("toggle", event => {
  const name = event.target.dataset?.details;
  if (!name) return;
  if (event.target.open) openCards.add(name); else openCards.delete(name);
}, true);

document.addEventListener("change", async event => {
  const toggle = event.target.closest("input[data-enable]");
  if (!toggle) return;
  try {
    await api(`/api/config/${encodeURIComponent(toggle.dataset.enable)}`, "POST", {enabled: toggle.checked});
    await loadConfig();
    await load();
  } catch (error) { toggle.checked = !toggle.checked; notice(error.message); }
});

document.addEventListener("submit", async event => {
  const form = event.target.closest("form[data-source-form]");
  if (!form) return;
  event.preventDefault();
  const name = form.dataset.sourceForm;
  const settings = {};
  const secrets = {};
  for (const input of form.querySelectorAll("input[data-kind]:not(:disabled)")) {
    if (input.dataset.kind === "setting") settings[input.name] = input.value;
    else if (input.value.trim()) secrets[input.name] = input.value;
  }
  const button = form.querySelector("button.primary");
  if (button) button.disabled = true;
  try {
    await api(`/api/config/${encodeURIComponent(name)}`, "POST", {settings, secrets});
    await loadConfig();
    const source = config.sources.find(found => found.name === name);
    if (source?.can_check && source.enabled) await runAction(name, "check", "Saved. Checking");
    else showResult(name, {ok: true, detail: "Saved."});
  } catch (error) { showResult(name, {ok: false, detail: error.message}); }
  finally { if (button) button.disabled = false; }
});

document.addEventListener("click", async event => {
  const button = event.target.closest("button[data-check], button[data-connect], button[data-disconnect], button[data-clear-secret]");
  if (!button) return;
  button.disabled = true;
  try {
    if (button.dataset.check) await runAction(button.dataset.check, "check", "Checking");
    else if (button.dataset.connect) await connect(button.dataset.connect);
    else if (button.dataset.disconnect) await runAction(button.dataset.disconnect, "disconnect", "Signing out");
    else if (confirm("Remove this saved token?")) {
      await api(`/api/config/${encodeURIComponent(button.dataset.source)}`, "POST", {clear: [button.dataset.clearSecret]});
      await loadConfig();
      showResult(button.dataset.source, {ok: true, detail: "Cleared."});
    }
  } catch (error) { notice(error.message); }
  finally { button.disabled = false; }
});
