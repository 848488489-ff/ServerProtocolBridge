"""Web UI HTML templates, split from web.py for file size.

Raw HTML strings only, no application code.  web.py imports both names
back so the reference sites inside create_app are unchanged.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="__LANG__" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP__ · __VERSION__</title>
<style>
:root {
  --bg: #eef1f6; --sidebar: #e3e8f0; --card: #ffffff; --field: #f4f6fa;
  --border: #d8dfe9; --text: #151c26; --muted: #5d6878; --hover: #d7deea;
  --accent: #2f6fed; --accent-hover: #2559c9; --success: #159a63;
  --danger: #d64545; --warn: #c27508; --shadow: 0 8px 24px rgba(20, 30, 50, .08);
  --radius: 14px; --density-gap: 12px; --font-scale: 1;
}
html[data-theme="dark"] {
  --bg: #0d1014; --sidebar: #141920; --card: #1a1f27; --field: #11151b;
  --border: #262d38; --text: #e9eef6; --muted: #8b95a7; --hover: #1e242e;
  --accent: #3b82f6; --accent-hover: #2f6fed; --success: #22b378;
  --danger: #ef5b5b; --warn: #e0a12a; --shadow: 0 8px 24px rgba(0, 0, 0, .35);
}
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] {
    --bg: #0d1014; --sidebar: #141920; --card: #1a1f27; --field: #11151b;
    --border: #262d38; --text: #e9eef6; --muted: #8b95a7; --hover: #1e242e;
    --accent: #3b82f6; --accent-hover: #2f6fed; --success: #22b378;
    --danger: #ef5b5b; --warn: #e0a12a; --shadow: 0 8px 24px rgba(0, 0, 0, .35);
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: calc(13px * var(--font-scale))/1.55 "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
}
button, input, select, textarea { font: inherit; color: inherit; }
a { color: var(--accent); }
.app { display: flex; min-height: 100vh; }
.sidebar {
  width: 228px; flex: 0 0 228px; background: var(--sidebar);
  padding: 22px 10px 18px; position: sticky; top: 0; height: 100vh;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto;
}
.brand { padding: 0 8px 14px; }
.brand strong { display: block; font-size: 17px; line-height: 1.35; font-weight: 700; }
.brand span { color: var(--muted); font-size: 12px; }
.nav { display: flex; flex-direction: column; gap: 2px; }
.nav button {
  border: 0; background: transparent; color: var(--text); text-align: left;
  padding: 9px 12px; border-radius: 8px; cursor: pointer; font-size: 13px;
  height: 38px; box-sizing: border-box;
}
.nav button:hover { background: var(--hover); }
.nav button.active { background: var(--accent); color: #fff; }
.side-foot { margin-top: auto; padding: 14px 10px 0; display: grid; gap: 10px; }
.side-foot label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.side-foot select {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 9px;
}
.main { flex: 1; min-width: 0; padding: 18px 22px 22px; }
.header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 12px; }
.header h1 { margin: 0; font-size: 23px; font-weight: 700; line-height: 1.25; }
.header p { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
.header-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.pill {
  display: inline-flex; align-items: center; justify-content: center;
  width: 96px; height: 26px; border-radius: 11px;
  color: #fff; background: var(--muted); font-size: 13px; font-weight: 700;
}
.pill.running { background: var(--success); }
.pill.starting, .pill.stopping { background: var(--warn); }
.pill.error { background: var(--danger); }
.page { display: none; }
.page.active { display: block; }
/* Settings: a save bar, then every card one after another.  The cards used to
   sit under a tab strip; without it the page is longer but nothing hides the
   fields a user is looking for. */
.savebar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
.savebar .spacer { flex: 1; }
.settings-search { margin: -2px 0 14px; max-width: 480px; }
.settings-search .hint { display: block; margin-top: 4px; }
.settings-search .hint[hidden] { display: none; }
.ports { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.ports input { flex: 1 1 130px; min-width: 0; }
.ports input.port-num { flex: 0 0 96px; }
.ports span { color: var(--muted); font-size: 12px; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 18px; margin-bottom: 16px; box-shadow: var(--shadow);
}
.card h2 { margin: 0 0 12px; font-size: 15px; }
.card h3 { margin: 0 0 8px; font-size: 14px; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.grid2 { display: grid; gap: var(--density-gap) 18px; grid-template-columns: 180px minmax(0, 1fr); align-items: center; }
.grid2[hidden] { display: none; }
.grid2 .hint { grid-column: 1 / -1; color: var(--muted); font-size: 12px; margin: -4px 0 4px; }
.grid2 .hint[hidden] { display: none; }
.routes { display: grid; gap: 8px; align-content: start; }
.routes[hidden] { display: none; }
.grid2 > .routes-label { align-self: start; padding-top: 2px; }
.routes-head[hidden] { display: none; }
.routes-head {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) 34px;
  gap: 8px; color: var(--muted); font-size: 12px; padding-bottom: 2px;
}
.route-row {
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) 34px;
  gap: 8px; align-items: center;
}
.route-row input {
  width: 100%; box-sizing: border-box; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; outline: none;
  font-family: Consolas, monospace; font-size: 13px;
}
.route-row input:focus { border-color: var(--accent); }
.route-remove {
  width: 34px; height: 34px; border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--muted); font-size: 16px; line-height: 1; cursor: pointer;
}
.route-remove:hover { color: var(--danger); border-color: var(--danger); }
.routes-empty { color: var(--muted); font-size: 12px; }
.routes .actions { justify-content: flex-start; }
.grid2 label[for] { cursor: pointer; }
.switch {
  position: relative; display: inline-block; width: 46px; height: 26px;
  justify-self: start; flex: 0 0 auto; cursor: pointer;
}
.switch input {
  position: absolute; inset: 0; width: 100%; height: 100%;
  margin: 0; opacity: 0; cursor: pointer; z-index: 1;
}
.switch .knob {
  position: absolute; inset: 0; border-radius: 999px;
  background: var(--border); transition: background .18s ease;
  pointer-events: none;
}
.switch .knob::after {
  content: ""; position: absolute; top: 3px; left: 3px;
  width: 20px; height: 20px; border-radius: 50%; background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .28);
  transition: transform .18s ease;
}
.switch input:checked + .knob { background: var(--accent); }
.switch input:checked + .knob::after { transform: translateX(20px); }
.switch input:focus-visible + .knob { outline: 2px solid var(--accent); outline-offset: 2px; }
.field, .grid2 input, .grid2 select, .grid2 textarea {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; outline: none;
}
.field:focus, .grid2 input:focus, .grid2 select:focus, .grid2 textarea:focus {
  border-color: var(--accent);
}
/* Native color pickers must not be stretched by the .grid2 input rules above:
   keep them a compact swatch, not a full-width bar. */
.grid2 input[type="color"] {
  width: 100%; max-width: 72px; height: 36px; padding: 2px;
  border: 1px solid var(--border); border-radius: 8px; cursor: pointer;
  background: var(--field);
}
.grid2 input[type="color"]::-webkit-color-swatch-wrapper { padding: 2px; }
.grid2 input[type="color"]::-webkit-color-swatch { border: none; border-radius: 5px; }
textarea { resize: vertical; min-height: 82px; font-family: Consolas, monospace; font-size: 13px; }
.btn {
  border: 1px solid transparent; border-radius: 9px; padding: 9px 16px;
  background: var(--field); color: var(--text); cursor: pointer; font-size: 13px;
}
.btn:hover { filter: brightness(.97); }
.btn.primary { background: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent-hover); }
.btn.success { background: var(--success); color: #fff; }
.btn.danger { background: var(--danger); color: #fff; }
.btn.ghost { border-color: var(--border); background: transparent; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.actions .spacer { flex: 1; }
.stats { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
.stat { background: var(--field); border-radius: 10px; padding: 12px 14px; }
.stat b { display: block; font-size: 20px; line-height: 1.2; }
.stat span { color: var(--muted); font-size: 12px; }
.endpoint {
  display: flex; align-items: center; gap: 10px; background: var(--field);
  border-radius: 10px; padding: 10px 12px; margin: 10px 0;
}
.endpoint code { flex: 1; font-family: Consolas, monospace; font-size: 15px; color: var(--success); word-break: break-all; }
.kv { display: grid; gap: 8px; }
.kv div { display: flex; gap: 12px; font-size: 13px; }
.kv span { color: var(--muted); min-width: 90px; }
.kv b { font-weight: 500; word-break: break-all; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 500; }
tr:last-child td { border-bottom: 0; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--field); color: var(--muted); font-size: 11px; }
.tag.active { background: color-mix(in srgb, var(--success) 18%, transparent); color: var(--success); }
.log-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
.log-toolbar label { color: var(--muted); font-size: 12px; }
.log-box {
  height: calc(100vh - 250px); min-height: 320px; overflow: auto; background: #0f1319;
  border: 1px solid var(--border); border-radius: 12px; padding: 12px;
  font: 12.5px/1.55 Consolas, "Courier New", monospace; color: #cbd5e1;
  scroll-behavior: smooth;
  /* pywebview's window has text selection disabled by default; the shell turns
     it on and these rules keep the log selectable even if a future backend
     resets the document default.  Without this the log could not be copied. */
  user-select: text; -webkit-user-select: text; cursor: text;
}
.log-line {
  white-space: pre-wrap; word-break: break-word;
  user-select: text; -webkit-user-select: text;
}
.log-debug { color: #7c8798; }
.log-info { color: #7fb0ff; }
.log-warn { color: #f0b45a; }
.log-error { color: #ff7b7b; }
.hint { color: var(--muted); font-size: 12px; }
.auto-save-indicator { color: var(--success); font-weight: 600; opacity: 0; transition: opacity .25s; }
.auto-save-indicator.show { opacity: 1; }
.problems { color: var(--warn); font-size: 12px; white-space: pre-line; margin-top: 8px; }
.banner {
  display: none; border: 1px solid var(--warn); background: color-mix(in srgb, var(--warn) 12%, var(--card));
  border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; font-size: 13px;
}
.banner.show { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.banner .spacer { flex: 1; }
.toast {
  position: fixed; top: 18px; right: 18px; z-index: 60; display: grid; gap: 8px;
  max-width: min(420px, calc(100vw - 36px));
}
.toast div {
  background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 10px; padding: 10px 14px; box-shadow: var(--shadow); font-size: 13px;
  animation: slide .18s ease-out;
}
.toast div.ok { border-left-color: var(--success); }
.toast div.warn { border-left-color: var(--warn); }
.toast div.error { border-left-color: var(--danger); }
.toast-persist {
  position: fixed; top: 18px; right: 18px; z-index: 61;
  display: flex; align-items: center; gap: 10px;
  max-width: min(420px, calc(100vw - 36px));
  background: var(--card); border: 1px solid var(--border);
  border-left: 4px solid var(--warn); border-radius: 10px;
  padding: 10px 10px 10px 14px; box-shadow: var(--shadow); font-size: 13px;
  animation: slide .18s ease-out;
}
.toast-persist[hidden] { display: none; }
.toast-persist .icon-btn { font-size: 18px; padding: 2px 6px; }
@keyframes slide { from { transform: translateY(-6px); opacity: 0; } }
dialog {
  border: 1px solid var(--border); border-radius: 14px; background: var(--card);
  color: var(--text); padding: 0; width: min(520px, calc(100vw - 32px)); box-shadow: var(--shadow);
}
dialog::backdrop { background: rgba(0, 0, 0, .42); }
.modal-head { display: flex; align-items: center; gap: 10px; padding: 16px 18px 0; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-head .icon-btn { margin-left: auto; }
.modal-body { padding: 14px 18px; display: grid; gap: 10px; }
.modal-body label { color: var(--muted); font-size: 12px; }
.modal-body input, .modal-body select {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 9px 10px;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 0 18px 16px; flex-wrap: wrap; }
.icon-btn { border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 22px; line-height: 1; padding: 4px 8px; }
.ms-code { font: 700 28px/1.2 Consolas, monospace; letter-spacing: 4px; text-align: center; color: var(--accent); padding: 8px 0; }
.ms-link { font-family: Consolas, monospace; font-size: 12px; }
.list { display: grid; gap: 6px; }
.component { display: flex; gap: 8px; justify-content: space-between; font-size: 13px; padding: 7px 0; border-bottom: 1px solid var(--border); }
.component:last-child { border-bottom: 0; }
.component a { text-decoration: none; }
@media (max-width: 860px) {
  .app { display: block; }
  .sidebar { position: static; width: auto; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; }
  .brand { padding: 0 10px 0 4px; }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .side-foot { margin: 0 0 0 auto; padding: 0; display: flex; gap: 8px; }
  .side-foot label { display: none; }
  .side-foot select { width: auto; }
  .main { padding: 16px; }
  .grid2 { grid-template-columns: 1fr; }
  .log-box { height: 55vh; }
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <strong>__APP__</strong>
      <span>v__VERSION__</span>
    </div>
    <nav class="nav" id="nav">
      <button data-page="dashboard" data-i18n="web.dashboard"></button>
      <button data-page="settings" data-i18n="web.settings"></button>
      <button data-page="accounts" data-i18n="web.accounts"></button>
      <button data-page="certificate" data-i18n="web.certificate"></button>
      <button data-page="logs" data-i18n="web.logs"></button>
      <button data-page="about" data-i18n="web.about"></button>
    </nav>
    <div class="side-foot">
      <div><label data-i18n="gui.label.theme"></label><select id="theme-select"></select></div>
      <div><label data-i18n="gui.language"></label><select id="language-select"></select></div>
    </div>
  </aside>

  <main class="main">
    <header class="header">
      <div>
        <h1 id="page-title"></h1>
        <p id="page-subtitle"></p>
      </div>
      <div class="header-actions">
        <span class="pill" id="status-pill"></span>
        <button class="btn ghost" id="btn-update" data-i18n="gui.update.button_check"></button>
      </div>
    </header>

    <div class="banner" id="update-banner">
      <span id="update-text"></span>
      <span class="spacer"></span>
      <a class="btn primary" id="update-link" target="_blank" rel="noreferrer" data-i18n="web.open_release"></a>
    </div>

    <section class="page" id="page-dashboard">
      <div class="card">
        <h2 data-i18n="gui.section.connection"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.target"></label>
          <input id="target" autocomplete="off">
          <div class="hint" data-i18n="gui.hint.endpoint"></div>
          <label data-i18n="gui.label.listen_host"></label>
          <div class="ports">
            <input id="listen_host" autocomplete="off">
            <span data-i18n="gui.label.wss_port"></span>
            <input id="wss_port" inputmode="numeric" class="port-num">
            <span data-i18n="gui.label.ws_port"></span>
            <input id="ws_port" inputmode="numeric" class="port-num">
          </div>
          <label for="use_srv" data-i18n="gui.label.use_srv"></label>
          <label class="switch"><input type="checkbox" id="use_srv"><span class="knob"></span></label>
        </div>
        <div class="endpoint">
          <code id="endpoint">—</code>
          <button class="btn primary" id="btn-copy-endpoint" data-i18n="gui.button.copy"></button>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.actions"></h2>
        <div class="actions">
          <button class="btn success" id="btn-start" data-i18n="gui.button.start"></button>
          <button class="btn danger" id="btn-stop" data-i18n="gui.button.stop"></button>
          <button class="btn" data-action="save-config" data-i18n="gui.button.save_config"></button>
          <button class="btn ghost" data-action="reset-defaults" data-i18n="gui.button.reset_defaults"></button>
          <span class="spacer"></span>
        </div>
        <div class="kv" style="margin-top:12px">
          <div><span data-i18n="web.webui_url"></span><b><a id="web-url" href="#" target="_blank" rel="noreferrer">—</a></b></div>
          <div><span data-i18n="web.webui"></span><b id="web-bind">—</b></div>
        </div>
        <div class="hint" id="service-hint" style="margin-top:8px"></div>
      </div>

      <div class="card">
        <h2 data-i18n="web.session"></h2>
        <div class="stats">
          <div class="stat"><b id="stat-active">0</b><span data-i18n="gui.stat.active"></span></div>
          <div class="stat"><b id="stat-total">0</b><span data-i18n="gui.stat.total"></span></div>
          <div class="stat"><b id="stat-up">0 B</b><span data-i18n="gui.stat.up"></span></div>
          <div class="stat"><b id="stat-down">0 B</b><span data-i18n="gui.stat.down"></span></div>
          <div class="stat"><b id="stat-uptime">0:00</b><span data-i18n="gui.stat.uptime"></span></div>
        </div>
        <div class="kv" style="margin-top:12px">
          <div><span data-i18n="web.listeners"></span><b id="listeners">—</b></div>
        </div>
      </div>
    </section>

    <section class="page" id="page-settings">
      <div class="savebar">
        <button class="btn primary" data-action="save-config" data-i18n="gui.button.save_config"></button>
        <button class="btn ghost" data-action="reset-defaults" data-i18n="gui.button.reset_defaults"></button>
        <span class="spacer"></span>
        <span class="hint auto-save-indicator" id="auto-save-indicator" hidden></span>
        <span class="hint" data-i18n="gui.hint.endpoint"></span>
      </div>

      <div class="settings-search" data-no-autosave>
        <input type="search" id="settings-search" class="field"
               data-i18n-placeholder="web.settings_search" autocomplete="off">
        <span class="hint" id="settings-search-empty" data-i18n="web.settings_no_match" hidden></span>
      </div>

      <div class="tabpane card" data-pane="appearance" data-no-autosave>
        <h2 data-i18n="gui.section.appearance"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.appearance_preset"></label>
          <select id="ap-preset">
            <option value="default" data-i18n="gui.label.appearance_preset_default">Default</option>
            <option value="ocean" data-i18n="gui.label.appearance_preset_ocean">Ocean</option>
            <option value="forest" data-i18n="gui.label.appearance_preset_forest">Forest</option>
            <option value="sunset" data-i18n="gui.label.appearance_preset_sunset">Sunset</option>
            <option value="mono" data-i18n="gui.label.appearance_preset_mono">Monochrome</option>
            <option value="custom" data-i18n="gui.label.appearance_preset_custom">Custom</option>
          </select>
          <label data-i18n="gui.label.appearance_accent"></label>
          <input type="color" id="ap-accent" value="#2f6fed">
          <label data-i18n="gui.label.appearance_bg_color"></label>
          <input type="color" id="ap-bgcolor" value="#eef1f6">
          <label data-i18n="gui.label.appearance_radius"></label>
          <input type="range" id="ap-radius" min="0" max="24" value="14">
          <label data-i18n="gui.label.appearance_density"></label>
          <select id="ap-density">
            <option value="compact" data-i18n="gui.label.appearance_density_compact">Compact</option>
            <option value="comfortable" selected data-i18n="gui.label.appearance_density_comfortable">Comfortable</option>
            <option value="spacious" data-i18n="gui.label.appearance_density_spacious">Spacious</option>
          </select>
          <label data-i18n="gui.label.appearance_font_scale"></label>
          <input type="range" id="ap-font-scale" min="80" max="130" value="100">
        </div>
        <div class="card" style="margin-top:12px;padding:12px">
          <div id="ap-preview" style="min-height:80px;border-radius:8px;padding:12px;background:var(--card);border:1px solid var(--border)">
            <strong data-i18n="gui.label.appearance_preview">Preview</strong> · <span style="color:var(--muted)" data-i18n="gui.label.appearance_preview_muted">muted text</span>
            <div style="margin-top:8px"><button class="btn primary" data-i18n="gui.button.preview_primary">Primary</button> <button class="btn ghost" data-i18n="gui.button.preview_ghost">Ghost</button></div>
          </div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button type="button" class="btn primary" id="ap-save" data-i18n="gui.button.save">Save</button>
          <button type="button" class="btn ghost" id="ap-reset" data-i18n="gui.button.reset">Reset</button>
        </div>
      </div>

      <div class="tabpane card" data-pane="forward">
        <h2 data-i18n="gui.section.forwarding"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.server_brand"></label>
          <input id="server_brand" autocomplete="off">
          <label data-i18n="gui.label.server_brand_version"></label>
          <input id="server_brand_version" autocomplete="off">
          <label data-i18n="gui.label.spoof_client"></label>
          <select id="spoof_client"></select>
          <label data-i18n="gui.label.spoof_brand" id="spoof-brand-label" data-spoof-brand="1"></label>
          <input id="spoof_brand" autocomplete="off" data-spoof-brand="1">
          <div class="hint" data-i18n="gui.hint.spoof_brand" id="spoof-brand-hint" data-spoof-brand="1"></div>
          <label for="suffix_route" data-i18n="gui.label.suffix_route"></label>
          <label class="switch"><input type="checkbox" id="suffix_route"><span class="knob"></span></label>
          <div class="hint" data-i18n="gui.hint.suffix_route"></div>
          <label class="routes-label" data-i18n="gui.label.routes"></label>
          <div class="routes">
            <div class="routes-head" id="routes-head">
              <span data-i18n="web.route_path"></span>
              <span data-i18n="web.route_target"></span>
              <span></span>
            </div>
            <div id="routes-list"></div>
            <div id="routes-empty" class="routes-empty" data-i18n="web.route_empty"></div>
            <div class="actions">
              <button type="button" class="btn ghost" id="btn-route-add" data-i18n="web.route_add"></button>
            </div>
          </div>
          <div class="hint" data-i18n="gui.hint.routes"></div>
        </div>
      </div>

      <div class="tabpane card" data-pane="protocol">
        <h2 data-i18n="gui.section.protocol"></h2>
        <div class="grid2">
          <label for="rewrite_handshake_host" data-i18n="gui.label.rewrite_host"></label>
          <label class="switch"><input type="checkbox" id="rewrite_handshake_host"><span class="knob"></span></label>
          <label for="eagler_translate" data-i18n="gui.label.eagler_translate"></label>
          <label class="switch"><input type="checkbox" id="eagler_translate"><span class="knob"></span></label>
          <label for="login_ack" data-i18n="gui.label.login_ack"></label>
          <label class="switch"><input type="checkbox" id="login_ack"><span class="knob"></span></label>
          <label for="packet_timing" data-i18n="gui.label.packet_timing"></label>
          <label class="switch"><input type="checkbox" id="packet_timing"><span class="knob"></span></label>
          <div class="hint" data-i18n="gui.hint.packet_timing"></div>
          <label data-i18n="gui.label.resource_pack_mode"></label>
          <select id="resource_pack_mode"></select>
          <label for="auto_exit" data-i18n="gui.label.auto_exit"></label>
          <label class="switch"><input type="checkbox" id="auto_exit"><span class="knob"></span></label>
        </div>
      </div>

      <div class="tabpane card" data-pane="runtime">
        <h2 data-i18n="gui.section.runtime"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.log_level"></label>
          <select id="log_level"></select>
          <label data-i18n="gui.label.log_max_lines"></label>
          <select id="log_max_lines"></select>
          <label data-i18n="gui.label.heartbeat"></label>
          <input id="heartbeat_sec" inputmode="numeric">
          <label data-i18n="gui.label.connect_timeout"></label>
          <input id="connect_timeout" inputmode="decimal">
          <label data-i18n="gui.label.max_payload"></label>
          <input id="max_payload_mb" inputmode="numeric">
          <label for="update_check" data-i18n="gui.label.update_check"></label>
          <label class="switch"><input type="checkbox" id="update_check"><span class="knob"></span></label>
        </div>
        <div class="hint" data-i18n="gui.hint.log_max_lines"></div>
      </div>

      <div class="tabpane card" data-pane="web" data-no-autosave>
        <h2 data-i18n="gui.section.web"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.web_host"></label>
          <input id="web_host" autocomplete="off">
          <label data-i18n="gui.label.web_port"></label>
          <input id="web_port" inputmode="numeric">
          <div class="hint" data-i18n="gui.hint.web_bind"></div>
          <label for="auth-enabled" data-i18n="web.require_password"></label>
          <label class="switch"><input type="checkbox" id="auth-enabled"><span class="knob"></span></label>
          <label data-i18n="web.new_password"></label>
          <input id="auth-password" type="password" autocomplete="new-password">
          <label data-i18n="web.confirm_password"></label>
          <input id="auth-confirm" type="password" autocomplete="new-password">
          <div class="hint" data-i18n="web.password_hint"></div>
          <div class="hint" id="auth-loopback-note" data-i18n="web.password_loopback_note" hidden></div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn primary" id="btn-save-auth" data-i18n="gui.button.web_auth_apply"></button>
          <button class="btn ghost" id="btn-clear-auth" data-i18n="web.password_clear" hidden></button>
          <button class="btn ghost" id="btn-web-restart" data-i18n="gui.button.web_restart"></button>
          <span class="hint" id="auth-status"></span>
          <span class="hint" data-i18n="web.bind_hint"></span>
        </div>
      </div>

      <div class="tabpane card" data-pane="mcp" data-no-autosave>
        <h2 data-i18n="web.mcp_section"></h2>
        <div class="grid2">
          <label data-i18n="web.mcp_endpoint"></label>
          <input id="mcp-endpoint" readonly>
          <label data-i18n="web.mcp_key"></label>
          <input id="mcp-key" type="password" autocomplete="new-password">
          <div class="hint" id="mcp-status" data-i18n="web.mcp_status_unset"></div>
          <div class="hint" data-i18n="web.mcp_key_hint"></div>
          <div class="hint" id="mcp-loopback-note" data-i18n="web.mcp_loopback_no_key" hidden></div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn ghost" id="btn-copy-mcp" data-i18n="web.mcp_copy"></button>
          <button class="btn primary" id="btn-save-mcp" data-i18n="web.mcp_save"></button>
          <button class="btn ghost" id="btn-clear-mcp" data-i18n="web.mcp_clear" hidden></button>
          <span class="hint" id="mcp-msg"></span>
        </div>
      </div>

      <div class="tabpane card" data-pane="api" data-no-autosave>
        <h2 data-i18n="web.api_section"></h2>
        <div class="grid2">
          <label data-i18n="web.api_endpoint"></label>
          <input id="api-endpoint" readonly>
          <label data-i18n="web.api_docs_label"></label>
          <a class="btn ghost" id="btn-api-docs" target="_blank" rel="noreferrer"></a>
          <div class="hint" data-i18n="web.api_auth_hint"></div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn ghost" id="btn-copy-api" data-i18n="web.api_copy"></button>
          <span class="hint" id="api-msg"></span>
        </div>
      </div>

      <div class="tabpane card" data-pane="cert">
        <h2 data-i18n="gui.section.certificate"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.cert_dir"></label>
          <input id="cert_dir" autocomplete="off">
          <label data-i18n="gui.label.cert_cn"></label>
          <input id="cert_common_name" autocomplete="off">
          <label data-i18n="gui.label.cert_extra"></label>
          <input id="cert_extra_names" autocomplete="off">
          <label data-i18n="gui.label.cert_days"></label>
          <input id="cert_days" inputmode="numeric">
          <label data-i18n="gui.label.cert_generator"></label>
          <select id="cert_generator"></select>
        </div>
      </div>

      <div class="problems" id="config-problems" style="margin-top:14px"></div>
    </section>

    <section class="page" id="page-accounts">
      <div class="card">
        <h2 data-i18n="web.accounts"></h2>
        <div class="actions">
          <button class="btn primary" id="btn-add-offline" data-i18n="gui.accounts.add.offline"></button>
          <button class="btn ghost" id="btn-add-thirdparty" data-i18n="gui.accounts.add.thirdparty"></button>
          <button class="btn ghost" id="btn-add-microsoft" data-i18n="gui.accounts.add.microsoft"></button>
          <span class="spacer"></span>
          <button class="btn ghost" id="btn-use-none" data-i18n="gui.accounts.button.clear" disabled></button>
        </div>
        <div style="overflow:auto;margin-top:12px">
          <table>
            <thead><tr>
              <th></th>
              <th data-i18n="gui.accounts.col.name"></th>
              <th data-i18n="gui.accounts.col.kind"></th>
              <th data-i18n="gui.accounts.col.uuid"></th>
              <th></th>
            </tr></thead>
            <tbody id="accounts-body"></tbody>
          </table>
        </div>
        <p class="hint" data-i18n="gui.accounts.hint"></p>
      </div>
    </section>

    <section class="page" id="page-certificate">
      <div class="card">
        <h2 data-i18n="gui.section.certificate"></h2>
        <div class="kv" id="cert-info"></div>
        <div class="actions" style="margin-top:14px">
          <button class="btn primary" id="btn-generate-cert" data-i18n="gui.button.regen_cert"></button>
          <button class="btn ghost" id="btn-install-cert" data-i18n="gui.button.install_cert"></button>
        </div>
        <p class="hint" data-i18n="gui.cert.hint"></p>
      </div>
      <div class="card">
        <h2 data-i18n="gui.label.cert_generator"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.cert_cn"></label>
          <input id="cert_cn_page" autocomplete="off">
          <label data-i18n="gui.label.cert_extra"></label>
          <input id="cert_extra_page" autocomplete="off">
          <label data-i18n="gui.label.cert_days"></label>
          <input id="cert_days_page" inputmode="numeric">
          <label data-i18n="gui.label.cert_generator"></label>
          <select id="cert_generator_page"></select>
        </div>
      </div>
    </section>

    <section class="page" id="page-logs">
      <div class="card">
        <div class="log-toolbar">
          <button class="btn ghost" id="btn-clear-log" data-i18n="gui.log.clear"></button>
          <button class="btn ghost" id="btn-copy-log" data-i18n="web.log_copy"></button>
          <button class="btn ghost" id="btn-export-log" data-i18n="web.log_export"></button>
          <label><input type="checkbox" id="log-autoscroll" checked> <span data-i18n="gui.log.auto_scroll"></span></label>
          <label for="log-level" data-i18n="gui.label.log_level"></label>
          <select id="log-level" class="field" style="width:auto"></select>
          <input type="search" id="log-search" class="field" style="width:auto"
                 data-i18n-placeholder="web.log_search" autocomplete="off">
          <span class="hint" data-i18n="gui.log.hint"></span>
        </div>
        <div class="log-box" id="log-box"></div>
      </div>
    </section>

    <section class="page" id="page-about">
      <div class="card">
        <h2 id="about-title"></h2>
        <p id="about-blurb"></p>
        <p class="hint" id="about-license"></p>
      </div>
      <div class="card">
        <h2 data-i18n="gui.about.components"></h2>
        <div class="list" id="about-components"></div>
        <h2 data-i18n="gui.about.stdlib"></h2>
        <div class="list" id="about-stdlib"></div>
        <p class="hint" data-i18n="gui.about.hint"></p>
        <div class="actions">
          <button type="button" class="btn ghost" id="btn-copy-about"
                  data-i18n="gui.about.copy"></button>
        </div>
      </div>
    </section>
  </main>
</div>

<div class="toast" id="toast"></div>

<!-- Persistent top-right notification: some settings only apply after the
     service is restarted.  Shown by renderServiceRestart, dismissed by the
     close button or by starting the service. -->
<div class="toast-persist warn" id="service-restart-toast" hidden role="status">
  <span class="toast-persist-msg" data-i18n="web.service_restart_hint"></span>
  <button type="button" class="icon-btn" id="btn-service-restart-close"
          aria-label="Dismiss" title="Dismiss">&times;</button>
</div>
<dialog id="modal"></dialog>

<script>
const I18N = __I18N__;
const state = {
  config: null, status: null, accounts: [], about: null, logSeq: 0, language: '__LANG__',
  theme: '__THEME__', update: null, page: 'dashboard', seenRevision: undefined,
  auth: { enabled: false, has_password: false },
  mcp: { enabled: false, has_key: false, endpoint: '', loopback_bind: false },
  loopbackBind: true, appearance: {}
};

function t(key, vars) {
  let text = I18N[key] || key;
  if (vars) {
    text = text.replace(/%\((\w+)\)s/g, (m, k) => (k in vars ? vars[k] : m))
               .replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  }
  return text;
}
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

/* renderStatus runs on every 1.2 s poll, so a page that has been moved around
   and no longer contains an element must not take the rest of the refresh with
   it.  A null element used to abort the whole function. */
function setText(sel, value) {
  const el = $(sel);
  if (el) el.textContent = value;
}
function setAttr(sel, attr, value) {
  const el = $(sel);
  if (el) el.setAttribute(attr, value);
}
function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[ch]);
}
function fmt(value, fallback) { return value == null || value === '' ? (fallback || '—') : value; }

/* This browser profile's stable id.  The server binds the session to it
   (ip + user agent + this), so a copied session cookie fails when replayed
   from another machine, browser or profile.  Stored in localStorage only. */
function deviceId() {
  var KEY = 'spb-device-id';
  var value = '';
  try { value = localStorage.getItem(KEY) || ''; } catch (err) { value = ''; }
  if (!value) {
    value = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
      : 'd-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
    // Storage may be unavailable (private window, storage blocked).  Keep using
    // the id for this page instead of falling back to an empty one, which the
    // server cannot distinguish from a different client.
    try { localStorage.setItem(KEY, value); } catch (err) { }
  }
  return value;
}

async function api(path, options) {
  options = options || {};
  const init = { method: options.method || 'GET', headers: {} };
  const id = deviceId();
  if (id) init.headers['X-Device-Id'] = id;
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  let data = null;
  try { data = await response.json(); } catch (err) { data = null; }
  if (response.status === 401 && data && data.login) {
    location.href = '/login';
    throw new Error(data.error || 'HTTP 401');
  }
  if (!response.ok || (data && data.ok === false)) {
    throw new Error((data && data.error) || response.statusText || ('HTTP ' + response.status));
  }
  return data || {};
}

function toast(message, kind, timeout) {
  const box = $('#toast');
  const item = document.createElement('div');
  item.className = kind || '';
  item.textContent = message;
  box.appendChild(item);
  setTimeout(() => item.remove(), timeout || 4200);
}

function applyI18n() {
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.title = t('core.app_name') + ' · ' + t('web.subtitle');
}

function fillSelect(selector, options, selected) {
  const select = $(selector);
  if (!select) return;
  select.innerHTML = '';
  (options || []).forEach(option => {
    const item = document.createElement('option');
    item.value = option.code !== undefined ? option.code : option;
    item.textContent = option.label !== undefined ? option.label : option;
    select.appendChild(item);
  });
  if (selected !== undefined && selected !== null) select.value = String(selected);
}

function setPage(name) {
  const pages = ['dashboard', 'settings', 'accounts', 'certificate', 'logs', 'about'];
  if (!pages.includes(name)) name = 'dashboard';
  state.page = name;
  $$('.nav button').forEach(btn => btn.classList.toggle('active', btn.dataset.page === name));
  pages.forEach(page => $('#page-' + page).classList.toggle('active', page === name));
  const titles = {
    dashboard: ['web.dashboard', 'gui.page.control.subtitle'],
    settings: ['web.settings', 'gui.page.settings.subtitle'],
    accounts: ['web.accounts', 'gui.page.accounts.subtitle'],
    certificate: ['web.certificate', 'gui.page.cert.subtitle'],
    logs: ['web.logs', 'gui.page.log.subtitle'],
    about: ['web.about', 'gui.page.about.subtitle']
  };
  $('#page-title').textContent = t(titles[name][0]);
  $('#page-subtitle').textContent = t(titles[name][1]);
  if (history.replaceState) history.replaceState(null, '', '#' + name);
  if (name === 'accounts') loadAccounts();
  if (name === 'certificate') loadCert();
  if (name === 'about') loadAbout();
}

/* ---------- status ---------- */
function renderStatus(data) {
  state.status = data;
  const pill = $('#status-pill');
  const map = {
    stopped: ['gui.status.stopped', ''], starting: ['gui.status.starting', 'starting'],
    running: ['gui.status.running', 'running'], stopping: ['gui.status.stopping', 'stopping'],
    error: ['gui.status.start_failed', 'error']
  };
  const entry = map[data.state] || map.stopped;
  pill.textContent = t(entry[0]);
  pill.className = 'pill ' + entry[1];
  const busy = ['starting', 'running', 'stopping'].includes(data.state);
  $('#btn-start').disabled = busy;
  $('#btn-stop').disabled = !['starting', 'running'].includes(data.state);
  setText('#service-hint', data.error || '');
  const stats = data.stats || {};
  setText('#stat-active', fmt(stats.active, '0'));
  setText('#stat-total', fmt(stats.total, '0'));
  setText('#stat-up', fmt(stats.bytes_to_server_human, '0 B'));
  setText('#stat-down', fmt(stats.bytes_to_client_human, '0 B'));
  setText('#stat-uptime', fmt(stats.uptime_human, '0:00'));
  setText('#endpoint', data.endpoint || '—');
  setText('#listeners', (data.listeners || []).join('  ·  ') || '—');
  const web = data.web || {};
  if (web.url) {
    setText('#web-url', web.url);
    setAttr('#web-url', 'href', web.url);
  }
  let bindHost = web.host || '';
  if (bindHost.indexOf(':') !== -1 && bindHost.charAt(0) !== '[') bindHost = '[' + bindHost + ']';
  setText('#web-bind', bindHost + ':' + (web.port || ''));
  if (data.auth) {
    state.auth = data.auth;
    updateAuthVisibility();
  }
  if (data.loopback_bind !== undefined) state.loopbackBind = !!data.loopback_bind;
  updateAuthAvailability();
  syncConfigFromStatus(data);
}

async function loadStatus() {
  try {
    renderStatus(await api('/api/status'));
  } catch (err) {
    $('#status-pill').textContent = t('gui.status.start_failed');
    $('#status-pill').className = 'pill error';
    setText('#service-hint', t('web.connection_failed', { error: err.message }));
  }
}

/* ---------- configuration ---------- */
function addRouteRow(path, target) {
  const row = document.createElement('div');
  row.className = 'route-row';
  const pathInput = document.createElement('input');
  pathInput.className = 'route-path';
  pathInput.value = path || '';
  pathInput.placeholder = t('web.route_path_example');
  pathInput.autocomplete = 'off';
  pathInput.spellcheck = false;
  const targetInput = document.createElement('input');
  targetInput.className = 'route-target';
  targetInput.value = target || '';
  targetInput.placeholder = t('web.route_target_example');
  targetInput.autocomplete = 'off';
  targetInput.spellcheck = false;
  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'route-remove';
  remove.textContent = '×';
  remove.title = t('web.route_remove');
  remove.setAttribute('aria-label', t('web.route_remove'));
  remove.addEventListener('click', () => { row.remove(); refreshRoutes(); });
  row.append(pathInput, targetInput, remove);
  $('#routes-list').appendChild(row);
  refreshRoutes();
}

function renderRoutes(routes) {
  const list = $('#routes-list');
  list.innerHTML = '';
  Object.entries(routes || {}).forEach(pair => addRouteRow(pair[0], pair[1]));
  refreshRoutes();
}

function refreshRoutes() {
  const has = $('#routes-list').children.length > 0;
  const empty = $('#routes-empty');
  if (empty) empty.hidden = has;
  const head = $('#routes-head');
  if (head) head.hidden = !has;
  updateSuffixRouteState();
}

/* Suffix routing and the path-route table cannot be used together.  The
   checkbox is locked while route rows exist; the route editor is locked
   while the checkbox is on.  The server enforces the same rule; this only
   keeps the page from offering a state that cannot be saved. */
function updateSuffixRouteState() {
  const suffix = $('#suffix_route');
  if (!suffix) return;
  const hasRoutes = $$('#routes-list .route-row').length > 0;
  suffix.disabled = hasRoutes && !suffix.checked;
  suffix.title = suffix.disabled ? t('gui.hint.suffix_route_disabled') : '';
  const lock = suffix.checked;
  $$('#routes-list .route-path, #routes-list .route-target, #routes-list .route-remove')
    .forEach(el => { el.disabled = lock; });
  const addBtn = $('#btn-route-add');
  if (addBtn) addBtn.disabled = lock;
}

/* Read the editor back into the "path=target" text the server parses.
   A row with exactly one side filled is invalid and is reported instead of
   dropped: skipping it silently meant the entry vanished without a message and
   the route was never applied.  A fully blank row is still ignored. */
function routeText() {
  const lines = [];
  for (const row of $$('#routes-list .route-row')) {
    const path = row.querySelector('.route-path').value.trim();
    const target = row.querySelector('.route-target').value.trim();
    if (!path && !target) continue;
    if (!path) return { text: '', error: t('core.config.route_missing_path') };
    if (!target) return { text: '', error: t('core.config.route_missing_target', { path }) };
    lines.push(path + '=' + target);
  }
  return { text: lines.join('\n'), error: '' };
}

function renderConfig(data) {
  if (data.revision !== undefined) state.seenRevision = data.revision;
  fillConfig(data.config, data.options || {}, data.problems || []);
  if (data.auth) renderAuth(data.auth);
  if (data.mcp) renderMcp(data.mcp);
  if (data.api) renderApi(data.api);
}

/* The spoof brand is only meaningful for the "custom" client-identity preset:
   every other preset supplies its own default brand.  Hiding the field keeps
   the preset list the single control, with "自定义" revealing the brand box. */
function updateSpoofBrandVisibility() {
  const select = $('#spoof_client');
  const custom = (select && select.value) === 'custom';
  ['spoof-brand-label', 'spoof_brand', 'spoof-brand-hint'].forEach(id => {
    const el = $('#' + id);
    if (el) el.hidden = !custom;
  });
}

/* ---------- settings search ----------
   The settings page no longer hides its cards behind tabs, so it is long
   enough to want a filter.  Each grid2 row (label + field) is matched against
   the query by its label text or the field's current value; rows that do not
   match are hidden, and a card with nothing left is hidden too.  The spoof
   brand row is owned by updateSpoofBrandVisibility and is skipped here. */
let settingsQuery = '';

function settingsGridRows(grid) {
  const kids = Array.from(grid.children);
  const rows = [];
  let i = 0;
  while (i < kids.length) {
    const el = kids[i];
    if (el.tagName === 'LABEL' && i + 1 < kids.length) {
      rows.push([el, kids[i + 1]]);
      i += 2;
    } else {
      rows.push([el]);
      i += 1;
    }
  }
  return rows;
}

function applySettingsFilter() {
  const query = settingsQuery;
  const empty = $('#settings-search-empty');
  if (!query) {
    $$('#page-settings .tabpane').forEach(card => {
      card.hidden = false;
      card.querySelectorAll('.grid2').forEach(grid => {
        grid.hidden = false;
        Array.from(grid.children).forEach(el => { el.hidden = false; });
      });
    });
    if (empty) empty.hidden = true;
    refreshRoutes();
    updateSpoofBrandVisibility();
    updateAuthAvailability();
    return;
  }
  let anyVisible = false;
  $$('#page-settings .tabpane').forEach(card => {
    let cardVisible = false;
    card.querySelectorAll('.grid2').forEach(grid => {
      let gridVisible = false;
      settingsGridRows(grid).forEach(row => {
        if (row.some(el => el.hasAttribute && el.hasAttribute('data-spoof-brand'))) {
          return;  // updateSpoofBrandVisibility owns these
        }
        const text = row.map(el =>
          ((el.textContent || '') + ' ' + (el.value || '')).toLowerCase()).join(' ');
        const match = !query || text.indexOf(query) !== -1;
        row.forEach(el => { el.hidden = !match; });
        if (match) gridVisible = true;
      });
      grid.hidden = !gridVisible;
      if (gridVisible) cardVisible = true;
    });
    card.hidden = !cardVisible;
    if (!card.hidden) anyVisible = true;
  });
  if (empty) empty.hidden = anyVisible;
}

/* Appearance / personalization: these run at module scope so fillConfig can
   apply the saved look on load, and the settings controls can preview live.
   The preset list lives here too so both the controls and the auto-"custom"
   detection share one source of truth. */
const AP_PRESETS = {
  default: { accent: '#2f6fed', bgColor: '#eef1f6' },
  ocean:   { accent: '#0ea5e9', bgColor: '#e0f2fe' },
  forest:  { accent: '#16a34a', bgColor: '#dcfce7' },
  sunset:  { accent: '#f97316', bgColor: '#ffedd5' },
  mono:    { accent: '#525252', bgColor: '#f5f5f5' },
};
function applyAppearance(a) {
  a = a || {};
  const root = document.documentElement;
  if (a.accent) root.style.setProperty('--accent', a.accent);
  if (a.bgColor) root.style.setProperty('--bg', a.bgColor);
  if (a.radius != null) root.style.setProperty('--radius', a.radius + 'px');
  const density = a.density || 'comfortable';
  const gap = density === 'compact' ? '6px' : density === 'spacious' ? '18px' : '12px';
  root.style.setProperty('--density-gap', gap);
  if (a.fontScale != null) root.style.setProperty('--font-scale', (a.fontScale / 100));
}
function loadAppearanceControls(a) {
  a = a || {};
  const setVal = (id, v) => { const el = $(id); if (el && v != null) el.value = v; };
  setVal('#ap-preset', a.preset || 'default');
  setVal('#ap-accent', a.accent || '#2f6fed');
  setVal('#ap-bgcolor', a.bgColor || '#eef1f6');
  setVal('#ap-radius', a.radius != null ? a.radius : 14);
  setVal('#ap-density', a.density || 'comfortable');
  setVal('#ap-font-scale', a.fontScale != null ? a.fontScale : 100);
}
/* Match the current accent/bgColor against a preset; if no preset matches, the
   user has made a custom look, so the preset select flips to "custom". */
function matchAppearancePreset(accent, bgColor) {
  for (const key in AP_PRESETS) {
    const p = AP_PRESETS[key];
    if (p.accent === accent && p.bgColor === bgColor) return key;
  }
  return 'custom';
}

/* Push one config into the settings form.  options is only needed to rebuild
   the <select> lists, which never change after the first load: a sync call
   passes {} and sets .value in place, which neither rebuilds a select nor
   steals the cursor. */
function fillConfig(config, options, problems) {
  state.config = config;
  [['spoof_client', '#spoof_client', options.spoof_clients],
   ['resource_pack_mode', '#resource_pack_mode', options.resource_pack_modes],
   ['log_level', '#log_level', options.log_levels],
   ['log_max_lines', '#log_max_lines', options.log_limits],
   ['cert_generator', '#cert_generator', options.cert_generators],
   ['cert_generator', '#cert_generator_page', options.cert_generators],
   ['theme', '#theme-select', options.themes],
   ['language', '#language-select', options.languages]].forEach(item => {
    const el = $(item[1]);
    if (!el) return;
    if (options && item[2]) fillSelect(item[1], item[2], config[item[0]]);
    else el.value = config[item[0]] ?? el.value;
  });
  const logFilter = $('#log-level');
  if (options) fillSelect('#log-level', [{ code: 'all', label: t('web.all_levels') }]
    .concat(options.log_levels || []), logFilter.value || 'all');
  state.theme = config.theme;
  state.language = config.language;
  document.documentElement.dataset.theme = config.theme;
  state.appearance = config.appearance || {};
  applyAppearance(state.appearance);
  loadAppearanceControls(state.appearance);
  const fields = ['target', 'listen_host', 'wss_port', 'ws_port', 'server_brand',
    'server_brand_version', 'spoof_brand', 'log_level', 'heartbeat_sec',
    'connect_timeout', 'max_payload_mb', 'cert_dir',
    'cert_common_name', 'cert_extra_names', 'cert_days', 'cert_generator',
    'web_host', 'web_port'];
  fields.forEach(id => { const el = $('#' + id); if (el) el.value = config[id] ?? ''; });
  renderRoutes(config.routes);
  ['use_srv', 'rewrite_handshake_host', 'eagler_translate', 'login_ack',
   'packet_timing', 'auto_exit', 'update_check', 'suffix_route'].forEach(id => {
    const el = $('#' + id); if (el) el.checked = !!config[id];
  });
  updateSuffixRouteState();
  $('#cert_cn_page').value = config.cert_common_name || '';
  $('#cert_extra_page').value = (config.cert_extra_names || []).join(', ');
  $('#cert_days_page').value = config.cert_days || 3650;
  renderProblems(problems);
  updateAuthAvailability();
  updateSpoofBrandVisibility();
}

/* The desktop window and this page edit one config file, so a change on one
   side must reach the other without reopening it.  /api/status carries the
   revision and the whole config; when the revision moves and nothing is being
   typed into, the form is filled from the fresh values.  While a field is
   focused we skip and retry on the next poll, so an edit is never clobbered. */
function syncConfigFromStatus(data) {
  if (state.seenRevision === undefined || !data.config) {
    state.seenRevision = data.revision;
    return;
  }
  if (data.revision === state.seenRevision) return;
  const active = document.activeElement;
  if (active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return;
  state.seenRevision = data.revision;
  fillConfig(data.config, {}, data.config_problems || []);
  if (data.auth) renderAuth(data.auth);
  if (data.mcp) renderMcp(data.mcp);
}

function isLoopbackHost(host) {
  host = String(host == null ? '' : host).trim().toLowerCase();
  if (!host) return true;
  if (host.charAt(0) === '[' && host.charAt(host.length - 1) === ']') {
    host = host.slice(1, -1);
  }
  if (host === 'localhost' || host === '::1' || host.indexOf('::ffff:127.') === 0) {
    return true;
  }
  return /^127\./.test(host);
}

function currentBindHost() {
  const field = $('#web_host');
  if (field) return field.value;
  return state.config ? state.config.web_host : '';
}

/* A password only protects clients that can reach the page over the network.
   When the listener is bound to loopback there is no such client, so the
   controls are disabled instead of pretending to add security. */
function updateAuthAvailability() {
  const loopback = isLoopbackHost(currentBindHost());
  state.loopbackBind = loopback;
  ['auth-enabled', 'auth-password', 'auth-confirm', 'btn-save-auth'].forEach(id => {
    const el = $('#' + id);
    if (el) el.disabled = loopback;
  });
  const note = $('#auth-loopback-note');
  if (note) note.hidden = !loopback;
  const clear = $('#btn-clear-auth');
  if (clear) clear.hidden = !(state.auth && state.auth.has_password);
}

function renderAuth(auth) {
  state.auth = auth || { enabled: false, has_password: false };
  $('#auth-enabled').checked = !!state.auth.enabled;
  $('#auth-password').value = '';
  $('#auth-confirm').value = '';
  updateAuthVisibility();
  updateAuthAvailability();
}

function updateAuthVisibility() {
  const status = $('#auth-status');
  if (status) {
    status.textContent = state.auth && state.auth.has_password
      ? t('web.password_set') : t('web.password_unset');
  }
}

async function saveAuth() {
  if (isLoopbackHost(currentBindHost())) {
    toast(t('web.password_loopback_note'), 'warn', 7000);
    return;
  }
  const enabled = $('#auth-enabled').checked;
  const password = $('#auth-password').value;
  const confirm = $('#auth-confirm').value;
  if (enabled && password !== confirm) {
    toast(t('web.password_mismatch'), 'error');
    return;
  }
  if (enabled && !password && !(state.auth && state.auth.has_password)) {
    toast(t('web.password_required'), 'error');
    return;
  }
  if (enabled && password && password.length < 4) {
    toast(t('web.password_short'), 'error');
    return;
  }
  try {
    const data = await api('/api/auth', { method: 'POST', body: { enabled, password } });
    renderAuth(data.auth);
    if (data.reauth) {
      toast(t('web.password_saved'), 'ok');
      setTimeout(() => {
        // A loopback client never has to sign in again, so bouncing it to the
        // login page (which redirects straight back) only lost its place.  A
        // remote client is the one the password protects and must re-auth.
        if (data.loopback) {
          location.reload();
        } else {
          const next = location.pathname + location.hash;
          location.href = '/login?next=' + encodeURIComponent(next);
        }
      }, 700);
      return;
    }
    if (!enabled) {
      toast(t('web.saved'), 'ok');
    } else if (data.password_changed === false) {
      toast(t('web.password_unchanged'), 'ok');
    } else {
      toast(t('web.password_saved'), 'ok');
    }
  } catch (err) {
    toast(err.message, 'error', 6000);
  }
}

async function clearAuth() {
  try {
    const data = await api('/api/auth', { method: 'POST', body: { enabled: false } });
    renderAuth(data.auth);
    toast(t('web.password_cleared'), 'ok');
  } catch (err) { toast(err.message, 'error'); }
}

/* ---------- MCP key ----------
   An MCP key only matters for clients that reach the page over the network;
   on a loopback bind it cannot add security, so the controls are disabled. */
function renderMcp(mcp) {
  state.mcp = mcp || { enabled: false, has_key: false, endpoint: '', loopback_bind: false };
  const endpoint = $('#mcp-endpoint');
  if (endpoint) endpoint.value = state.mcp.endpoint || '';
  updateMcpAvailability();
}

/* ---------- REST API ----------
   The automation JSON API shares the Web UI listener.  This card shows its
   base URL and links to the in-program documentation page. */
function renderApi(api) {
  state.api = api || { endpoint: '', docs: '' };
  const endpoint = $('#api-endpoint');
  if (endpoint) endpoint.value = state.api.endpoint || '';
  const docs = $('#btn-api-docs');
  if (docs) {
    const url = state.api.docs || '/api/v1/docs';
    docs.href = url;
    docs.textContent = t('web.api_open_docs', { url });
    docs.hidden = !state.api.docs;
  }
}

function updateMcpAvailability() {
  const loopback = state.mcp ? !!state.mcp.loopback_bind : isLoopbackHost(currentBindHost());
  ['mcp-key', 'btn-save-mcp'].forEach(id => {
    const el = $('#' + id);
    if (el) el.disabled = loopback;
  });
  const note = $('#mcp-loopback-note');
  if (note) note.hidden = !loopback;
  const clear = $('#btn-clear-mcp');
  if (clear) clear.hidden = !(state.mcp && state.mcp.has_key);
  const status = $('#mcp-status');
  if (status) {
    status.textContent = state.mcp && state.mcp.has_key
      ? t('web.mcp_status_set') : t('web.mcp_status_unset');
  }
}

async function saveMcp() {
  if (state.mcp && state.mcp.loopback_bind) {
    toast(t('web.mcp_loopback_no_key'), 'warn', 7000);
    return;
  }
  const key = ($('#mcp-key').value || '').trim();
  if (!key) { toast(t('web.mcp_key_required'), 'error'); return; }
  if (key.length < 8) { toast(t('web.mcp_key_short'), 'error'); return; }
  try {
    const data = await api('/api/mcp', { method: 'POST', body: { key } });
    renderMcp(data.mcp);
    $('#mcp-key').value = '';
    toast(t('web.mcp_saved'), 'ok');
  } catch (err) { toast(err.message, 'error', 6000); }
}

async function clearMcp() {
  try {
    const data = await api('/api/mcp', { method: 'POST', body: { clear: true } });
    renderMcp(data.mcp);
    toast(t('web.mcp_cleared'), 'ok');
  } catch (err) { toast(err.message, 'error', 6000); }
}

function renderProblems(problems) {
  const box = $('#config-problems');
  box.textContent = (problems || []).join('\n');
}

/* A trailing parenthesised suffix is a build/channel tag, not part of the
   version ("EaglercraftX 1.21.11 (u1-beta)"); it is dropped before saving so
   it never travels upstream.  Applied repeatedly. */
function stripParenSuffix(text) {
  let out = String(text == null ? '' : text).trim();
  while (/\s*\([^()]*\)\s*$/.test(out)) {
    out = out.replace(/\s*\([^()]*\)\s*$/, '').trim();
  }
  return out;
}

/* Show or hide the persistent top-right notice that some settings only apply
   after the service is restarted.  It is a notification only -- the service is
   never restarted automatically. */
function renderServiceRestart(needed) {
  const note = $('#service-restart-toast');
  if (note) note.hidden = !needed;
}

function numberValue(id, label, integer) {
  const raw = ($('#' + id).value || '').trim();
  const value = Number(raw);
  if (raw === '' || !Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    throw new Error(t('web.invalid_number', { field: label }));
  }
  return value;
}

function collectConfig() {
  const config = {};
  ['target', 'listen_host', 'server_brand', 'server_brand_version', 'spoof_brand',
   'cert_dir', 'cert_common_name', 'web_host'].forEach(id => {
    config[id] = ($('#' + id).value || '').trim();
  });
  config.wss_port = numberValue('wss_port', t('gui.label.wss_port'), true);
  config.ws_port = numberValue('ws_port', t('gui.label.ws_port'), true);
  config.web_port = numberValue('web_port', t('gui.label.web_port'), true);
  config.heartbeat_sec = numberValue('heartbeat_sec', t('gui.label.heartbeat'), true);
  config.connect_timeout = numberValue('connect_timeout', t('gui.label.connect_timeout'), false);
  config.max_payload_mb = numberValue('max_payload_mb', t('gui.label.max_payload'), true);
  config.cert_days = numberValue('cert_days', t('gui.label.cert_days'), true);
  const routes = routeText();
  if (routes.error) throw new Error(routes.error);
  config.routes_text = routes.text;
  config.cert_extra_names = $('#cert_extra_names').value;
  config.spoof_client = $('#spoof_client').value;
  config.spoof_brand = stripParenSuffix($('#spoof_brand').value);
  config.resource_pack_mode = $('#resource_pack_mode').value;
  config.log_level = $('#log_level').value;
  config.log_max_lines = numberValue('log_max_lines', t('gui.label.log_max_lines'), true);
  config.cert_generator = $('#cert_generator').value;
  config.theme = $('#theme-select').value;
  config.language = $('#language-select').value;
  ['use_srv', 'rewrite_handshake_host', 'eagler_translate', 'login_ack',
   'packet_timing', 'auto_exit', 'update_check', 'suffix_route'].forEach(id => {
    const el = $('#' + id);
    if (el) config[id] = el.checked;
  });
  return config;
}

async function loadConfig() {
  try {
    renderConfig(await api('/api/config'));
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------- auto save ----------
   Editing a config field saves it automatically after a short debounce, so the
   "needs a restart" notice appears on its own without a manual save.  The
   save is silent (no toast): the savebar indicator and the persistent
   restart notice are the feedback.  Panes marked data-no-autosave keep their
   own save buttons (appearance, Web UI/auth, MCP key, API info) and the
   settings search box is excluded. */
let autoSaveTimer = null;
let autoSaveFlashTimer = null;

function scheduleAutoSave() {
  clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(runAutoSave, 900);
}

async function runAutoSave() {
  autoSaveTimer = null;
  try {
    await saveConfig(true);
    flashAutoSaved(t('web.auto_saved'));
  } catch (err) {
    flashAutoSaved(t('web.auto_save_error'));
  }
}

function flashAutoSaved(message) {
  const indicator = $('#auto-save-indicator');
  if (!indicator) return;
  indicator.textContent = message;
  indicator.hidden = false;
  requestAnimationFrame(() => indicator.classList.add('show'));
  clearTimeout(autoSaveFlashTimer);
  autoSaveFlashTimer = setTimeout(() => {
    indicator.classList.remove('show');
    autoSaveFlashTimer = setTimeout(() => { indicator.hidden = true; }, 300);
  }, 1800);
}

async function saveConfig(silent) {
  const config = collectConfig();
  const data = await api('/api/config', { method: 'POST', body: config });
  state.config = data.config;
  state.seenRevision = data.revision;
  renderProblems(data.problems || []);
  // A running proxy reads some settings only at startup: show a persistent
  // top-right notice that a restart is needed, but never restart it
  // automatically (no hot reload).
  renderServiceRestart(data.service_restart);
  if (!silent) toast(t('web.saved'), 'ok');
  if (data.language_changed) {
    toast(t('web.language_reload'), 'warn');
    setTimeout(() => location.reload(), 600);
    return data;
  }
  if (data.web_restart) {
    handleWebRestart(data);
  }
  return data;
}

/* Changing the bind address stops this very server and rebinds the new one in
   a background thread.  The current page is left on a dead connection, so it
   has to follow the listener: same port means the page's own origin is still
   reachable (the loopback or the wildcard covers it), while a new port has to
   be followed to the URL the server now reports.  Without this the UI silently
   froze after saving a new listen address, which read as "could not set it". */
function handleWebRestart(data) {
  toast(t('web.webui_restarting', { url: data.web_url }), 'warn', 9000);
  const currentPort = location.port || (location.protocol === 'https:' ? '443' : '80');
  const match = (data.web_url || '').match(/:(\d+)\/?/);
  const newPort = match ? match[1] : currentPort;
  // Give the background restart thread its one-second sleep plus time to bind.
  setTimeout(() => {
    if (newPort === currentPort) {
      location.reload();
    } else {
      location.href = data.web_url;
    }
  }, 1800);
}

/* ---------- service ---------- */
async function startService() {
  try {
    await saveConfig(true);
    await api('/api/service/start', { method: 'POST', body: {} });
    renderServiceRestart(false);
    toast(t('web.started'), 'ok');
    loadStatus();
  } catch (err) {
    toast(t('web.start_failed', { error: err.message }), 'error', 7000);
  }
}
async function stopService() {
  try {
    await api('/api/service/stop', { method: 'POST', body: {} });
    toast(t('web.stopped'), 'ok');
    loadStatus();
  } catch (err) {
    toast(t('web.stop_failed', { error: err.message }), 'error');
  }
}

/* ---------- logs ---------- */
let logQuery = '';

/* The search box filters the rendered lines.  It never asks the server: the
   page already has the newest 2500 lines, which is what the box shows, and the
   filter is applied as lines arrive so the match stays live. */
function logMatches(text) {
  if (!logQuery) return true;
  return String(text || '').toLowerCase().indexOf(logQuery) !== -1;
}
function applyLogFilter() {
  const box = $('#log-box');
  if (!box) return;
  for (const child of box.children) {
    child.hidden = !logMatches(child.textContent);
  }
}
async function loadLogs() {
  if (state.page !== 'logs') return;
  try {
    const level = $('#log-level').value || 'all';
    const data = await api('/api/logs?since=' + state.logSeq + '&level=' + encodeURIComponent(level));
    state.logSeq = data.seq;
    appendLogs(data.lines || []);
  } catch (err) { /* polling errors are transient */ }
}
function appendLogs(lines) {
  if (!lines.length) return;
  const box = $('#log-box');
  const frag = document.createDocumentFragment();
  lines.forEach(line => {
    const item = document.createElement('div');
    item.className = 'log-line log-' + (line.level || 'info');
    item.textContent = line.text || '';
    item.hidden = !logMatches(item.textContent);
    frag.appendChild(item);
  });
  box.appendChild(frag);
  while (box.childElementCount > 2500) box.firstElementChild.remove();
  if ($('#log-autoscroll').checked) box.scrollTop = box.scrollHeight;
}
async function clearLogs() {
  try {
    await api('/api/logs/clear', { method: 'POST', body: {} });
    $('#log-box').innerHTML = '';
    state.logSeq = 0;
    toast(t('web.log_cleared'), 'ok');
  } catch (err) { toast(err.message, 'error'); }
}

/* The log page keeps only the newest 2500 lines in the DOM, so copying the
   visible box would silently lose the older part of the buffer.  Both actions
   ask the server for the full buffer (respecting the level filter) instead. */
async function fetchLogText() {
  const level = $('#log-level').value || 'all';
  const response = await fetch('/api/logs/export?level=' + encodeURIComponent(level));
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.text();
}
async function copyLogs() {
  try {
    const text = await fetchLogText();
    if (!text.trim()) { toast(t('web.log_empty'), 'warn'); return; }
    await copyText(text);
  } catch (err) { toast(t('web.log_copy_failed', { error: err.message }), 'error'); }
}
async function exportLogs() {
  try {
    const text = await fetchLogText();
    if (!text.trim()) { toast(t('web.log_empty'), 'warn'); return; }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    link.href = url;
    link.download = 'server-protocol-bridge-' + stamp + '.log';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    toast(t('web.log_exported'), 'ok');
  } catch (err) { toast(t('web.log_export_failed', { error: err.message }), 'error'); }
}

/* ---------- accounts ---------- */
async function loadAccounts() {
  try {
    const data = await api('/api/accounts');
    state.accounts = data.accounts || [];
    renderAccounts();
  } catch (err) { toast(err.message, 'error'); }
}
function renderAccounts() {
  const body = $('#accounts-body');
  body.innerHTML = '';
  const hasActive = state.accounts.some(account => account.active);
  const useNone = $('#btn-use-none');
  if (useNone) useNone.disabled = !hasActive;
  if (!state.accounts.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.className = 'hint';
    cell.textContent = t('web.accounts_empty');
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  state.accounts.forEach(account => {
    const row = document.createElement('tr');
    const mark = document.createElement('td');
    mark.textContent = account.active ? '●' : '○';
    mark.style.color = account.active ? 'var(--success)' : 'var(--muted)';
    row.appendChild(mark);
    const name = document.createElement('td');
    name.textContent = account.username || '?';
    row.appendChild(name);
    const kind = document.createElement('td');
    const tag = document.createElement('span');
    tag.className = 'tag' + (account.active ? ' active' : '');
    tag.textContent = t('accounts.kind.' + account.kind);
    kind.appendChild(tag);
    row.appendChild(kind);
    const uuid = document.createElement('td');
    uuid.textContent = account.uuid ? account.uuid.slice(0, 8) + '…' : '—';
    uuid.style.fontFamily = 'Consolas, monospace';
    row.appendChild(uuid);
    const actions = document.createElement('td');
    actions.style.whiteSpace = 'nowrap';
    if (!account.active) {
      const activeBtn = document.createElement('button');
      activeBtn.className = 'btn ghost';
      activeBtn.textContent = t('gui.accounts.button.active');
      activeBtn.addEventListener('click', () => setActive(account.id));
      actions.appendChild(activeBtn);
    }
    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn ghost';
    removeBtn.style.color = 'var(--danger)';
    removeBtn.textContent = t('gui.accounts.button.remove');
    removeBtn.addEventListener('click', () => removeAccount(account));
    actions.appendChild(removeBtn);
    row.appendChild(actions);
    body.appendChild(row);
  });
}
async function setActive(id) {
  try {
    await api('/api/accounts/' + encodeURIComponent(id) + '/active', { method: 'POST', body: {} });
    toast(t('web.account_active'), 'ok');
    loadAccounts();
  } catch (err) { toast(err.message, 'error'); }
}
async function clearActive() {
  try {
    await api('/api/accounts/none', { method: 'POST', body: {} });
    toast(t('web.account_cleared'), 'ok');
    loadAccounts();
  } catch (err) { toast(err.message, 'error'); }
}
async function removeAccount(account) {
  if (!confirm(t('web.confirm_remove', { name: account.username }))) return;
  try {
    await api('/api/accounts/' + encodeURIComponent(account.id), { method: 'DELETE' });
    toast(t('web.account_removed'), 'ok');
    loadAccounts();
  } catch (err) { toast(err.message, 'error'); }
}

function modal(title, bodyHtml, buttons) {
  const dialog = $('#modal');
  dialog.innerHTML = '<div class="modal-head"><h3></h3><button type="button" class="icon-btn" data-close>×</button></div>'
    + '<div class="modal-body"></div><div class="modal-actions"></div>';
  dialog.querySelector('h3').textContent = title;
  dialog.querySelector('.modal-body').innerHTML = bodyHtml;
  const actions = dialog.querySelector('.modal-actions');
  (buttons || []).forEach(button => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = 'btn ' + (button.kind || 'ghost');
    element.textContent = button.label;
    element.addEventListener('click', () => button.onClick(dialog));
    actions.appendChild(element);
  });
  dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
  dialog.showModal();
  return dialog;
}

function addOffline() {
  const dialog = modal(t('gui.accounts.add.offline'),
    '<label>' + esc(t('web.offline_prompt')) + '</label><input id="offline-name" autocomplete="off">',
    [
      { label: t('gui.accounts.add.offline'), kind: 'primary', onClick: async (dlg) => {
          const name = dlg.querySelector('#offline-name').value.trim();
          try {
            await api('/api/accounts/offline', { method: 'POST', body: { username: name } });
            dlg.close(); toast(t('web.account_added'), 'ok'); loadAccounts();
          } catch (err) { toast(err.message, 'error'); }
        } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
  setTimeout(() => dialog.querySelector('#offline-name').focus(), 50);
}

function addThirdParty() {
  modal(t('gui.accounts.thirdparty.title'),
    '<label>' + esc(t('gui.accounts.thirdparty.server')) + '</label><input id="tp-server" placeholder="https://example.com" autocomplete="off">'
    + '<label>' + esc(t('gui.accounts.thirdparty.username')) + '</label><input id="tp-user" autocomplete="off">'
    + '<label>' + esc(t('gui.accounts.thirdparty.password')) + '</label><input id="tp-pass" type="password">'
    + '<p class="hint">' + esc(t('gui.accounts.thirdparty.note')) + '</p>',
    [
      { label: t('gui.accounts.thirdparty.submit'), kind: 'primary', onClick: async (dlg) => {
          const body = {
            server: dlg.querySelector('#tp-server').value.trim(),
            username: dlg.querySelector('#tp-user').value.trim(),
            password: dlg.querySelector('#tp-pass').value
          };
          if (!body.server || !body.username || !body.password) {
            toast(t('gui.accounts.thirdparty.missing'), 'error'); return;
          }
          const status = document.createElement('p');
          status.className = 'hint';
          status.textContent = t('gui.accounts.thirdparty.busy');
          dlg.querySelector('.modal-body').appendChild(status);
          try {
            await api('/api/accounts/thirdparty', { method: 'POST', body });
            dlg.close(); toast(t('web.account_added'), 'ok'); loadAccounts();
          } catch (err) { status.textContent = err.message; status.style.color = 'var(--danger)'; }
        } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
}

async function addMicrosoft(verify) {
  if (verify === undefined) verify = true;
  const dialog = modal(t('gui.accounts.ms.title'),
    '<p>' + esc(t('gui.accounts.ms.intro')) + '</p>'
    + '<div class="ms-code" id="ms-code">--------</div>'
    + '<input id="ms-link" class="ms-link" readonly>'
    + '<p class="hint" id="ms-status">' + esc(t('gui.accounts.ms.starting')) + '</p>',
    [
      { label: t('gui.accounts.ms.copy'), onClick: () => copyText($('#ms-code').textContent) },
      { label: t('gui.accounts.ms.open'), onClick: () => { const url = $('#ms-link').value; if (url) window.open(url, '_blank'); } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
  try {
    const start = await api('/api/accounts/microsoft/start', { method: 'POST', body: { verify } });
    $('#ms-code').textContent = start.user_code || '--------';
    $('#ms-link').value = start.verification_uri || '';
    $('#ms-status').textContent = t('web.ms_waiting') + ' ' + t('web.ms_verify_note');
    if (start.verification_uri) window.open(start.verification_uri, '_blank');
    pollMicrosoft(start.job, dialog, verify);
  } catch (err) {
    $('#ms-status').textContent = t('web.ms_failed', { error: err.message });
    $('#ms-status').style.color = 'var(--danger)';
  }
}

function pollMicrosoft(job, dialog, verify) {
  const timer = setInterval(async () => {
    if (!dialog.open) { clearInterval(timer); return; }
    try {
      const data = await api('/api/accounts/microsoft/' + encodeURIComponent(job));
      if (data.state === 'done') {
        clearInterval(timer);
        dialog.close();
        toast(t('web.ms_done', { name: data.account.username }), 'ok');
        loadAccounts();
      } else if (data.state === 'error') {
        clearInterval(timer);
        const status = dialog.querySelector('#ms-status');
        status.textContent = t('web.ms_failed', { error: data.error });
        status.style.color = 'var(--danger)';
        if (data.code === 'ssl' && verify) {
          const retry = document.createElement('button');
          retry.className = 'btn primary';
          retry.textContent = t('web.ms_retry_ssl');
          retry.addEventListener('click', () => { dialog.close(); addMicrosoft(false); });
          dialog.querySelector('.modal-actions').prepend(retry);
        }
      }
    } catch (err) {
      clearInterval(timer);
    }
  }, 2000);
}

/* ---------- certificate ---------- */
async function loadCert() {
  try {
    const data = await api('/api/cert');
    const info = data.info;
    const box = $('#cert-info');
    box.innerHTML = '';
    if (!data.exists || !info) {
      box.innerHTML = '<div class="hint">' + esc(t('web.no_cert')) + '</div>';
      return;
    }
    const rows = [
      [t('web.cert_file'), data.cert_path],
      [t('web.valid_until'), info.not_after || '—'],
      [t('web.fingerprint'), info.thumbprint || '—'],
      [t('web.covers'), (info.alt_names || []).join(', ') || '—']
    ];
    rows.forEach(([key, value]) => {
      const row = document.createElement('div');
      const label = document.createElement('span');
      label.textContent = key;
      const text = document.createElement('b');
      text.textContent = value;
      row.append(label, text);
      box.appendChild(row);
    });
  } catch (err) { toast(err.message, 'error'); }
}
async function generateCert() {
  const body = {
    common_name: $('#cert_cn_page').value.trim(),
    extra_names: $('#cert_extra_page').value,
    days: Number($('#cert_days_page').value || 3650),
    generator: $('#cert_generator_page').value
  };
  try {
    await api('/api/cert/generate', { method: 'POST', body });
    toast(t('web.cert_generated'), 'ok');
    loadCert(); loadConfig();
  } catch (err) { toast(err.message, 'error', 7000); }
}
async function installCert() {
  try {
    await api('/api/cert/install', { method: 'POST', body: {} });
    toast(t('web.cert_installed'), 'ok');
  } catch (err) { toast(err.message, 'error', 7000); }
}

/* ---------- update / about ---------- */
async function checkUpdate() {
  const button = $('#btn-update');
  button.disabled = true;
  button.textContent = t('web.update_checking');
  try {
    const data = await api('/api/update');
    state.update = data.update;
    if (data.update.newer) {
      $('#update-text').textContent = t('web.update_available', {
        version: data.update.version, current: data.update.current
      });
      const link = $('#update-link');
      link.href = data.update.page || '#';
      link.style.display = data.update.page ? '' : 'none';
      $('#update-banner').classList.add('show');
    } else {
      toast(t('web.update_current', { version: data.update.current || '__VERSION__' }), 'ok');
    }
  } catch (err) {
    toast(t('web.update_failed', { error: err.message }), 'error', 7000);
  } finally {
    button.disabled = false;
    button.textContent = t('gui.update.button_check');
  }
}

/* Build the text copied by the About page.  Headings come from the active
   interface language; component names, licences and URLs are language-neutral. */
function aboutComponentText(data) {
  const lines = [t('core.app_name') + '  v' + data.version, ''];
  lines.push(t('gui.about.components'));
  (data.components || []).forEach(component => {
    lines.push('- ' + component.name + '  ·  ' + component.license + '  ·  ' + component.url);
  });
  lines.push('', t('gui.about.stdlib'));
  (data.stdlib || []).forEach(name => {
    lines.push('- ' + name + '  ·  PSF-2.0  ·  '
      + 'https://docs.python.org/3/library/' + name + '.html');
  });
  return lines.join('\n');
}

function renderAboutRows(container, rows) {
  container.innerHTML = '';
  rows.forEach(row => {
    const item = document.createElement('div');
    item.className = 'component';
    const label = document.createElement('span');
    label.textContent = row.label;
    const link = document.createElement('a');
    link.href = row.url;
    link.target = '_blank';
    link.rel = 'noreferrer';
    link.textContent = '↗';
    item.append(label, link);
    container.appendChild(item);
  });
}

async function loadAbout() {
  try {
    const data = await api('/api/about');
    state.about = data;
    $('#about-title').textContent = t('core.app_name') + '  v' + data.version;
    $('#about-blurb').textContent = data.blurb;
    $('#about-license').textContent = data.license;
    renderAboutRows($('#about-components'), (data.components || []).map(component => ({
      label: component.name + '  ·  ' + component.license,
      url: component.url,
    })));
    renderAboutRows($('#about-stdlib'), (data.stdlib || []).map(name => ({
      label: name + '  ·  PSF-2.0',
      url: 'https://docs.python.org/3/library/' + name + '.html',
    })));
    const copy = $('#btn-copy-about');
    if (copy && !copy.dataset.bound) {
      copy.dataset.bound = '1';
      copy.addEventListener('click', () => {
        if (state.about) copyText(aboutComponentText(state.about));
      });
    }
  } catch (err) { toast(err.message, 'error'); }
}

/* ---------- clipboard / theme / language ---------- */
async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast(t('web.copy_done'), 'ok');
  } catch (err) {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast(t('web.copy_done'), 'ok');
  }
}

async function savePreference(payload) {
  try {
    return await api('/api/ui/preferences', { method: 'POST', body: payload });
  } catch (err) {
    toast(err.message, 'error');
    return null;
  }
}

/* ---------- wiring ---------- */
function bindEvents() {
  $$('.nav button').forEach(button => {
    button.addEventListener('click', () => setPage(button.dataset.page));
  });
  $('#btn-start').addEventListener('click', startService);
  $('#btn-stop').addEventListener('click', stopService);
  /* Save and reset appear on both the dashboard and the settings page, so they
     are wired by data-action rather than by id. */
  $$('[data-action="save-config"]').forEach(button => {
    button.addEventListener('click', async () => {
      try { await saveConfig(false); loadStatus(); }
      catch (err) { toast(t('web.save_failed', { error: err.message }), 'error', 7000); }
    });
  });
  $$('[data-action="reset-defaults"]').forEach(button => {
    button.addEventListener('click', async () => {
      if (!confirm(t('gui.dialog.reset.ask'))) return;
      try {
        const data = await api('/api/config', { method: 'POST', body: { reset: true } });
        const options = (await api('/api/config')).options;
        renderConfig({ config: data.config, options, problems: data.problems,
                       auth: data.auth, revision: data.revision });
        if (data.language_changed) {
          toast(t('web.language_reload'), 'warn');
          setTimeout(() => location.reload(), 600);
          return;
        }
        if (data.web_restart) {
          handleWebRestart(data);
        }
        toast(t('web.saved'), 'ok');
      } catch (err) { toast(err.message, 'error'); }
    });
  });
  $('#btn-save-auth').addEventListener('click', saveAuth);
  $('#btn-clear-auth').addEventListener('click', clearAuth);
  $('#web_host').addEventListener('input', () => { updateAuthAvailability(); updateMcpAvailability(); });
  $('#btn-save-mcp').addEventListener('click', saveMcp);
  $('#btn-clear-mcp').addEventListener('click', clearMcp);
  $('#btn-copy-mcp').addEventListener('click', () => copyText($('#mcp-endpoint').value));
  $('#btn-copy-api').addEventListener('click', () => copyText($('#api-endpoint').value));
  $('#btn-service-restart-close').addEventListener('click', () => renderServiceRestart(false));
  $('#btn-route-add').addEventListener('click', () => addRouteRow('', ''));
  $('#suffix_route').addEventListener('change', updateSuffixRouteState);
  /* Auto-save config fields as they change (debounced).  The settings search
     box and panes with their own save buttons are marked data-no-autosave.
     The dashboard holds the connection fields (target, listen host, ports,
     use_srv), which auto-save too so the "needs a restart" notice appears on
     its own when one of them changes. */
  const onConfigEdit = (event) => {
    if (event.target instanceof Element
        && !event.target.closest('[data-no-autosave]')) {
      scheduleAutoSave();
    }
  };
  ['#page-settings', '#page-dashboard'].forEach(selector => {
    const page = $(selector);
    page.addEventListener('input', onConfigEdit);
    page.addEventListener('change', onConfigEdit);
  });
  /* Removing a route row changes the config even though it is a button. */
  $('#page-settings').addEventListener('click', (event) => {
    if (event.target instanceof Element && event.target.closest('.route-remove')) {
      scheduleAutoSave();
    }
  });
  $('#btn-web-restart').addEventListener('click', async () => {
    try {
      const data = await api('/api/web/restart', { method: 'POST', body: {} });
      handleWebRestart({ web_url: data.url, web_restart: true });
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#btn-copy-endpoint').addEventListener('click', () => copyText($('#endpoint').textContent));
  $('#btn-update').addEventListener('click', checkUpdate);
  $('#btn-clear-log').addEventListener('click', clearLogs);
  $('#btn-copy-log').addEventListener('click', copyLogs);
  $('#btn-export-log').addEventListener('click', exportLogs);
  $('#log-level').addEventListener('change', () => {
    $('#log-box').innerHTML = '';
    state.logSeq = 0;
    loadLogs();
  });
  $('#log-search').addEventListener('input', event => {
    logQuery = (event.target.value || '').trim().toLowerCase();
    applyLogFilter();
  });
  $('#settings-search').addEventListener('input', event => {
    settingsQuery = (event.target.value || '').trim().toLowerCase();
    applySettingsFilter();
  });
  $('#spoof_client').addEventListener('change', updateSpoofBrandVisibility);
  $('#btn-add-offline').addEventListener('click', addOffline);
  $('#btn-add-thirdparty').addEventListener('click', addThirdParty);
  $('#btn-add-microsoft').addEventListener('click', () => addMicrosoft(true));
  $('#btn-use-none').addEventListener('click', clearActive);
  $('#btn-generate-cert').addEventListener('click', generateCert);
  $('#btn-install-cert').addEventListener('click', installCert);
  $('#theme-select').addEventListener('change', async event => {
    const theme = event.target.value;
    document.documentElement.dataset.theme = theme;
    state.theme = theme;
    const result = await savePreference({ theme });
    if (result) toast(t('web.theme_saved'), 'ok');
  });

  // ---------- appearance / personalization ----------
  const AP_PRESETS = {
    default: { accent: '#2f6fed', bgColor: '#eef1f6' },
    ocean:   { accent: '#0ea5e9', bgColor: '#e0f2fe' },
    forest:  { accent: '#16a34a', bgColor: '#dcfce7' },
    sunset:  { accent: '#f97316', bgColor: '#ffedd5' },
    mono:    { accent: '#525252', bgColor: '#f5f5f5' },
  };
  function collectAppearance() {
    return {
      preset: $('#ap-preset').value,
      accent: $('#ap-accent').value,
      bgColor: $('#ap-bgcolor').value,
      radius: parseInt($('#ap-radius').value, 10),
      density: $('#ap-density').value,
      fontScale: parseInt($('#ap-font-scale').value, 10),
    };
  }
  // preset change auto-fills colors; picking a real preset clears the custom flag
  $('#ap-preset').addEventListener('change', () => {
    const preset = $('#ap-preset').value;
    const p = AP_PRESETS[preset];
    if (p) {
      $('#ap-accent').value = p.accent;
      $('#ap-bgcolor').value = p.bgColor;
    }
    applyAppearance(collectAppearance());
  });
  // changing a color no longer matches a preset, so flip to "custom"
  function refreshPresetFromColors() {
    const preset = matchAppearancePreset($('#ap-accent').value, $('#ap-bgcolor').value);
    $('#ap-preset').value = preset;
  }
  ['#ap-accent','#ap-bgcolor'].forEach(sel => {
    const el = $(sel);
    if (el) el.addEventListener('input', () => { refreshPresetFromColors(); applyAppearance(collectAppearance()); });
  });
  ['#ap-radius','#ap-density','#ap-font-scale'].forEach(sel => {
    const el = $(sel);
    if (el) el.addEventListener('input', () => applyAppearance(collectAppearance()));
  });
  const saveBtn = $('#ap-save');
  if (saveBtn) saveBtn.addEventListener('click', async () => {
    const a = collectAppearance();
    state.appearance = a;
    try {
      const result = await savePreference({ appearance: a });
      if (result) toast(t('web.appearance_saved'), 'ok');
    } catch (err) { toast(err.message, 'error'); }
  });
  const resetBtn = $('#ap-reset');
  if (resetBtn) resetBtn.addEventListener('click', () => {
    const a = { preset: 'default', accent: '#2f6fed', bgColor: '#eef1f6', radius: 14, density: 'comfortable', fontScale: 100 };
    state.appearance = a;
    loadAppearanceControls(a);
    applyAppearance(a);
    savePreference({ appearance: a });
  });

  $('#language-select').addEventListener('change', async event => {
    const language = event.target.value;
    const result = await savePreference({ language });
    if (result && result.language_changed) {
      toast(t('web.language_reload'), 'warn');
      setTimeout(() => location.reload(), 500);
    }
  });
  window.addEventListener('hashchange', () => setPage(location.hash.slice(1) || 'dashboard'));
}

async function init() {
  applyI18n();
  bindEvents();
  setPage(location.hash.slice(1) || 'dashboard');
  await Promise.allSettled([loadConfig(), loadStatus(), loadAccounts(), loadCert()]);
  if (state.page === 'logs') loadLogs();
  applySettingsFilter();
  setInterval(loadStatus, 1200);
  setInterval(loadLogs, 1000);
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""
LOGIN_HTML = r"""<!doctype html>
<html lang="__LANG__" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · __APP__</title>
<style>
:root {
  --bg: #eef1f6; --card: #ffffff; --field: #f4f6fa; --border: #d8dfe9;
  --text: #151c26; --muted: #5d6878; --accent: #2f6fed; --accent-hover: #2559c9;
  --danger: #d64545; --shadow: 0 10px 30px rgba(20, 30, 50, .10);
}
html[data-theme="dark"] {
  --bg: #0d1014; --card: #1a1f27; --field: #11151b; --border: #262d38;
  --text: #e9eef6; --muted: #8b95a7; --accent: #3b82f6; --accent-hover: #2f6fed;
  --danger: #ef5b5b; --shadow: 0 10px 30px rgba(0, 0, 0, .40);
}
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] {
    --bg: #0d1014; --card: #1a1f27; --field: #11151b; --border: #262d38;
    --text: #e9eef6; --muted: #8b95a7; --accent: #3b82f6; --accent-hover: #2f6fed;
    --danger: #ef5b5b; --shadow: 0 10px 30px rgba(0, 0, 0, .40);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
  background: var(--bg); color: var(--text);
  font: 15px/1.55 "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
}
.card {
  width: min(400px, 100%); background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 28px; box-shadow: var(--shadow);
}
h1 { margin: 0 0 4px; font-size: 22px; }
p.intro { margin: 0 0 20px; color: var(--muted); font-size: 13px; }
label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
input[type="password"] {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 9px; padding: 11px 12px; font: inherit; color: inherit; outline: none;
}
input[type="password"]:focus { border-color: var(--accent); }
button {
  width: 100%; margin-top: 16px; border: 0; border-radius: 9px; padding: 11px 16px;
  background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer;
}
button:hover { background: var(--accent-hover); }
.error { color: var(--danger); font-size: 13px; margin-top: 12px; }
.error:empty { display: none; }
.brand { color: var(--muted); font-size: 12px; margin-top: 18px; text-align: center; }
</style>
</head>
<body>
<form class="card" method="post" action="/login">
  <h1>__TITLE__</h1>
  <p class="intro">__INTRO__</p>
  <label for="password">__PASSWORD__</label>
  <input id="password" name="password" type="password" autocomplete="current-password" autofocus required>
  <input type="hidden" name="next" value="__NEXT__">
  <input type="hidden" name="device" id="device-id">
  <button type="submit">__SUBMIT__</button>
  <div class="error">__ERROR__</div>
  <div class="brand">__APP__</div>
</form>
<script>
/* Give this browser profile a stable id.  The server binds the session to it,
   so a copied session cookie fails when replayed from another profile --
   each browser has to type the password.  Kept in localStorage, never sent to
   any other server. */
(function () {
  var KEY = 'spb-device-id';
  var value = '';
  try { value = localStorage.getItem(KEY) || ''; } catch (err) { value = ''; }
  if (!value) {
    if (window.crypto && crypto.randomUUID) {
      value = crypto.randomUUID();
    } else {
      value = 'd-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
    }
    // Storage may be unavailable (private window, storage blocked).  Keep using
    // the id for this page rather than submitting an empty one.
    try { localStorage.setItem(KEY, value); } catch (err) { }
  }
  var field = document.getElementById('device-id');
  if (field) field.value = value;
})();
</script>
</body>
</html>
"""
