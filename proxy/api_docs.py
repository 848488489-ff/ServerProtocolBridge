"""In-program documentation page for the REST JSON API (/api/v1).

Served at ``/api/v1/docs`` by :mod:`proxy.api_routes`.  It is a self-contained
bilingual page: English is shown by default, and a language switch (labelled
with each language's native name, "English" and "中文") toggles between the two
blocks and remembers the choice in localStorage.  The page describes only the
endpoint surface -- it needs no live data, so it is served without the API key.
"""

API_DOCS_HTML = r"""<!doctype html>
<html lang="en" data-lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>REST API — Server Protocol Bridge</title>
<style>
  :root { color-scheme: light; --bg:#f4f6f9; --card:#fff; --border:#dde3ea;
          --ink:#15212d; --muted:#5c6b7a; --accent:#2f6fed; --code:#0f172a; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--ink); }
  header { background:var(--card); border-bottom:1px solid var(--border); }
  .wrap { max-width:960px; margin:0 auto; padding:16px 20px; }
  .top { display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .brand { font-weight:700; }
  .edition { color:var(--muted); font-size:13px; }
  .lang-switch { display:flex; gap:8px; }
  .lang-switch button { border:1px solid var(--border); background:var(--card);
      padding:5px 12px; border-radius:8px; cursor:pointer; font:inherit; color:var(--ink); }
  .lang-switch button[aria-pressed="true"] { background:var(--accent); color:#fff;
      border-color:var(--accent); }
  main { padding:24px 20px 48px; }
  h1 { font-size:26px; margin:0 0 6px; }
  h2 { font-size:18px; margin:28px 0 8px; }
  p.lead { color:var(--muted); margin:0 0 16px; }
  .note { background:var(--card); border:1px solid var(--border); border-left:4px solid var(--accent);
      padding:10px 14px; border-radius:8px; margin:12px 0; }
  table { width:100%; border-collapse:collapse; background:var(--card);
      border:1px solid var(--border); border-radius:8px; overflow:hidden; margin:12px 0; }
  th,td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--border); vertical-align:top; }
  th { background:#eef2f7; font-size:13px; }
  tr:last-child td { border-bottom:0; }
  code { font-family:ui-monospace,Consolas,monospace; font-size:13px; }
  td code { background:#eef2f7; padding:2px 6px; border-radius:4px; }
  pre { background:var(--code); color:#e6edf3; padding:14px 16px; border-radius:8px;
      overflow:auto; font-size:13px; line-height:1.5; }
  pre code { background:none; padding:0; color:inherit; }
  footer { color:var(--muted); font-size:13px; border-top:1px solid var(--border);
      background:var(--card); }
  .foot { padding:14px 20px; }
</style>
</head>
<body>
<header>
  <div class="wrap top">
    <div>
      <div class="brand">Server Protocol Bridge</div>
      <div class="edition" data-i18n="edition">REST API · /api/v1/ · v__VERSION__</div>
    </div>
    <div class="lang-switch" role="group" aria-label="Language">
      <button type="button" data-lang="zh" aria-pressed="false">中文</button>
      <button type="button" data-lang="en" aria-pressed="true">English</button>
    </div>
  </div>
</header>

<main class="wrap">
  <!-- English (default) -->
  <div class="lang-en">
    <h1>REST API (<code>/api/v1/</code>)</h1>
    <p class="lead">An automation-oriented REST JSON API served on the Web UI
    listener. Every operation maps to one MCP tool, so scripts and
    <code>curl</code> control the program exactly the way an MCP client does —
    one implementation, two transports.</p>

    <h2>Authentication</h2>
    <div class="note">Loopback (<code>127.0.0.1</code>) needs no key. A
    non-loopback caller must present the MCP key as
    <code>Authorization: Bearer &lt;key&gt;</code>, <code>X-MCP-Key: &lt;key&gt;</code>
    or <code>X-API-Key: &lt;key&gt;</code>. With no key set the API is open only
    when the Web UI password is off — exactly the <code>/mcp</code> rule.</div>

    <h2>Endpoints</h2>
    <table>
      <thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>
      <tbody>
        <tr><td><code>GET</code></td><td><code>/api/v1/</code></td>
            <td>Discovery: name, version and the full tool catalogue.</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/docs</code></td>
            <td>This page (HTML, bilingual).</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/status</code></td>
            <td>Service state, version, listeners and traffic counters.</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/config</code></td>
            <td>Read the live configuration (passwords and tokens omitted).</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/config</code></td>
            <td>Write configuration fields; the body is the config object or
                <code>{"config": {...}}</code>.</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/start</code></td>
            <td>Start the proxy with the current configuration.</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/stop</code></td>
            <td>Stop the proxy; the Web UI and MCP endpoint stay up.</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/restart</code></td>
            <td>Stop then start again with the current configuration.</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/logs</code></td>
            <td>Read the in-memory log; query <code>since</code>/<code>level</code>/<code>limit</code>.</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/logs/clear</code></td>
            <td>Clear the in-memory log.</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/tools</code></td>
            <td>List every MCP tool (name, description, inputSchema).</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/tools/&lt;name&gt;</code></td>
            <td>Call any MCP tool by name; the body is the arguments object or
                <code>{"arguments": {...}}</code>.</td></tr>
      </tbody>
    </table>

    <h2>Examples</h2>
    <pre><code># status (loopback)
curl -s http://127.0.0.1:8765/api/v1/status

# set the forwarding target and start
curl -s -X POST http://127.0.0.1:8765/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{"target": "mc.example.com:25565"}'
curl -s -X POST http://127.0.0.1:8765/api/v1/service/start

# read logs since sequence 42
curl -s "http://127.0.0.1:8765/api/v1/logs?since=42&amp;level=error"

# remote automation needs the MCP key
curl -s http://host:8765/api/v1/status \
  -H 'Authorization: Bearer YOUR_MCP_KEY'

# call any MCP tool
curl -s -X POST http://127.0.0.1:8765/api/v1/tools/get_config \
  -H 'Content-Type: application/json' -d '{}'</code></pre>
  </div>

  <!-- Chinese -->
  <div class="lang-zh" hidden>
    <h1>REST API（<code>/api/v1/</code>）</h1>
    <p class="lead">在 Web UI 监听器上提供的面向自动化的 REST JSON API。每个
    操作都映射到一个 MCP 工具，脚本和 <code>curl</code> 可以像 MCP 客户端一样
    精确地控制程序——一套实现，两种传输。</p>

    <h2>鉴权</h2>
    <div class="note">回环（<code>127.0.0.1</code>）免密。非回环调用方需以
    <code>Authorization: Bearer &lt;key&gt;</code>、<code>X-MCP-Key: &lt;key&gt;</code>
    或 <code>X-API-Key: &lt;key&gt;</code> 提供 MCP 密钥。未设置密钥时，仅当
    Web UI 密码关闭才开放——与 <code>/mcp</code> 规则完全一致。</div>

    <h2>端点</h2>
    <table>
      <thead><tr><th>方法</th><th>路径</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td><code>GET</code></td><td><code>/api/v1/</code></td>
            <td>发现：名称、版本与完整工具目录。</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/docs</code></td>
            <td>本页（HTML，双语）。</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/status</code></td>
            <td>服务状态、版本、监听器与流量计数。</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/config</code></td>
            <td>读取运行配置（不含密码与令牌）。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/config</code></td>
            <td>写入配置字段；请求体为配置对象或
                <code>{"config": {...}}</code>。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/start</code></td>
            <td>用当前配置启动代理。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/stop</code></td>
            <td>停止代理；Web UI 与 MCP 端点保持运行。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/service/restart</code></td>
            <td>停止后用当前配置重新启动。</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/logs</code></td>
            <td>读取内存日志；查询参数 <code>since</code>/<code>level</code>/<code>limit</code>。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/logs/clear</code></td>
            <td>清空内存日志。</td></tr>
        <tr><td><code>GET</code></td><td><code>/api/v1/tools</code></td>
            <td>列出全部 MCP 工具（名称、描述、inputSchema）。</td></tr>
        <tr><td><code>POST</code></td><td><code>/api/v1/tools/&lt;name&gt;</code></td>
            <td>按名称调用任意 MCP 工具；请求体为参数对象或
                <code>{"arguments": {...}}</code>。</td></tr>
      </tbody>
    </table>

    <h2>示例</h2>
    <pre><code># 状态（回环）
curl -s http://127.0.0.1:8765/api/v1/status

# 设置转发目标并启动
curl -s -X POST http://127.0.0.1:8765/api/v1/config \
  -H 'Content-Type: application/json' \
  -d '{"target": "mc.example.com:25565"}'
curl -s -X POST http://127.0.0.1:8765/api/v1/service/start

# 从序号 42 起读错误日志
curl -s "http://127.0.0.1:8765/api/v1/logs?since=42&amp;level=error"

# 远端自动化需要 MCP 密钥
curl -s http://host:8765/api/v1/status \
  -H 'Authorization: Bearer YOUR_MCP_KEY'

# 调用任意 MCP 工具
curl -s -X POST http://127.0.0.1:8765/api/v1/tools/get_config \
  -H 'Content-Type: application/json' -d '{}'</code></pre>
  </div>
</main>

<footer>
  <div class="wrap foot">
    Base URL <code>http://&lt;host&gt;:&lt;web_port&gt;/api/v1/</code> ·
    UTF-8 JSON · <code>Cache-Control: no-store</code>
  </div>
</footer>

<script>
(function () {
  'use strict';
  var root = document.documentElement;
  function apply(lang) {
    root.setAttribute('data-lang', lang);
    root.lang = lang === 'zh' ? 'zh-CN' : 'en';
    Array.prototype.forEach.call(document.querySelectorAll('.lang-en, .lang-zh'),
      function (block) { block.hidden = !block.classList.contains('lang-' + lang); });
    Array.prototype.forEach.call(document.querySelectorAll('.lang-switch button'),
      function (btn) {
        var active = btn.getAttribute('data-lang') === lang;
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
  }
  var stored = null;
  try { stored = localStorage.getItem('spb-api-docs-lang'); } catch (e) {}
  var lang = (stored === 'zh' || stored === 'en') ? stored : 'en';
  apply(lang);
  Array.prototype.forEach.call(document.querySelectorAll('.lang-switch button'),
    function (btn) {
      btn.addEventListener('click', function () {
        var next = btn.getAttribute('data-lang');
        apply(next);
        try { localStorage.setItem('spb-api-docs-lang', next); } catch (e) {}
      });
    });
})();
</script>
</body>
</html>
"""
