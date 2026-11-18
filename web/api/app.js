(function () {
  'use strict';

  var dictionaries = {
    en: {
      'page.title': 'Field reference — Server Protocol Bridge',
      'meta.description': 'Reference for the seven static JSON files served under /api/.',
      'skip': 'Skip to content',
      'brand': 'Server Protocol Bridge',
      'edition.api': 'API reference',
      'lang.label': 'Language',
      'api.kicker': 'Static JSON',
      'api.title': 'Field reference',
      'api.lead': 'Seven read-only JSON files serve the release page, the FAQ and the desktop updater. There is no key, no account and no server-side code; the host returns the files as they are.',
      'api.note': 'Base URL /api/ · UTF-8 · CORS * · Cache-Control no-store · no auth.',
      'index.title': 'Endpoints',
      'table.path': 'Path',
      'table.returns': 'Returns',
      'index.version': 'Release manifest: version, date, size, download and source links.',
      'index.faq': 'Bilingual FAQ items rendered by the release page.',
      'index.features': 'Feature catalogue; the current release page does not load it.',
      'index.stats': 'Static platform, runtime, port, Web UI/MCP endpoint, protocol and client facts.',
      'index.licenses': 'Third-party components and their licences.',
      'index.site': 'Site metadata and links to every endpoint.',
      'index.endpoints': 'Machine-readable index of these seven files.',
      'table.method': 'Method',
      'runtime.title': 'Runtime REST API (/api/v1/)',
      'runtime.lead': 'The running program exposes an automation JSON API under /api/v1/ on the Web UI listener. Every operation maps to an MCP tool, so scripts and curl can control the program exactly the way an MCP client does.',
      'runtime.auth': 'Authentication matches the MCP endpoint: loopback (127.0.0.1) is free; a non-loopback caller must present the MCP key as Authorization: Bearer &lt;key&gt;, X-MCP-Key: &lt;key&gt; or X-API-Key: &lt;key&gt;. With no key set the API is open only when the Web UI password is off.',
      'rt.index': 'Discovery: name, version and the full tool catalogue.',
      'rt.docs': 'In-program bilingual documentation page (English by default, switchable).',
      'rt.status': 'Current service state, version, listeners and traffic counters.',
      'rt.config_get': 'Read the live configuration (passwords and tokens are omitted).',
      'rt.config_post': 'Write configuration fields; the body is the config object or {"config": {...}}.',
      'rt.service_start': 'Start the proxy with the current configuration.',
      'rt.service_stop': 'Stop the proxy; the Web UI and MCP endpoint stay up.',
      'rt.service_restart': 'Stop then start again with the current configuration.',
      'rt.logs': 'Read the in-memory log; query since/level/limit.',
      'rt.clear': 'Clear the in-memory log.',
      'rt.tools': 'List every MCP tool (name, description, inputSchema).',
      'rt.tool_call': 'Call any MCP tool by name; the body is the arguments object or {"arguments": {...}}.',
      'rt.examples': 'Examples',
      'conventions.title': 'Conventions',
      'conventions.lead': 'The same rules apply to every file under /api/.',
      'conv.1': 'Every endpoint is a GET request. There are no writes or authenticated routes.',
      'conv.2': 'Responses are UTF-8 JSON. Fields may be added; clients should ignore unknown fields.',
      'conv.3': 'No key, account or cookie is required. The static host returns the file directly.',
      'conv.4': 'JSON responses send Access-Control-Allow-Origin: * and Cache-Control: no-store.',
      'conv.5': 'Replacing a JSON file publishes the change; there is no service to restart.',
      'conv.6': 'version.json is the single source of truth for release metadata. The page shows an error state, not a bundled fallback, when it cannot be read.',
      'version.desc': 'Read by the release page and the desktop updater. Only version is required; unknown fields are ignored, so the schema can grow without breaking older clients. The values below are illustrative; the source fields are filled in after the archive is built.',
      'table.field': 'Field',
      'table.type': 'Type',
      'table.notes': 'Notes',
      'field.version': 'Newest published version, compared with the running build.',
      'field.download_url': 'Direct link to the Windows build. Empty hides the download button.',
      'field.page_url': 'Release page opened by the desktop updater when download_url is a static build path.',
      'field.min_version': 'Oldest build still supported; older clients are asked to update.',
      'field.force_update': 'Marks the release as mandatory for older clients.',
      'field.release_date': 'Release date, preferably YYYY-MM-DD.',
      'field.changelog': 'Default release notes. One line per entry.',
      'field.changelog_en': 'English release notes used when the interface is English.',
      'field.file_size': 'Windows build size in bytes.',
      'field.source_url': 'Direct link to the source ZIP. Empty hides the source button.',
      'field.source_size': 'Source ZIP size in bytes.',
      'field.source_name': 'Source ZIP filename shown in the button tooltip.',
      'field.source_version': 'Version inside the source package.',
      'field.source_updated': 'UTC timestamp of the last source export.',
      'version.note': 'The updater accepts http:// and https:// links and resolves same-site relative paths against the manifest URL. A missing optional field never blocks a running session.',
      'faq.desc': 'The release page fetches this file once and renders every item in both languages. Switching the language does not make another request.',
      'field.faq_version': 'Schema version for this document.',
      'field.faq_updated': 'Last content update date.',
      'field.faq_items': 'Ordered FAQ entries.',
      'field.faq_id': 'Stable identifier.',
      'field.faq_question': 'Object with en and zh strings.',
      'field.faq_answer': 'Object with en and zh strings, rendered as text.',
      'other.title': 'Other files',
      'other.lead': 'These files are descriptive. The current release page does not need them to render, but they remain public for tools and older versions.',
      'other.features': '— version and a bilingual item list (id, title, body).',
      'other.stats': '— platform, runtime, listener, Web UI/MCP endpoints, protocol, client and language facts.',
      'other.licenses': '— runtime components, standard-library modules and licence names.',
      'other.site': '— project name, version, tagline, base URL and a link map.',
      'other.endpoints': '— base path, count and the seven endpoint records.',
      'footer.note': 'Static files. No cookies and no analytics on this page.',
      'footer.back': 'Back to the release page'
    },
    zh: {
      'page.title': '字段说明 — 服务器协议转换',
      'meta.description': '/api/ 下七个静态 JSON 文件的字段说明。',
      'skip': '跳到正文',
      'brand': '服务器协议转换',
      'edition.api': 'API 说明',
      'lang.label': '语言',
      'api.kicker': '静态 JSON',
      'api.title': '字段说明',
      'api.lead': '/api/ 下的七个只读 JSON 文件为发布页、常见问题和桌面更新器提供数据。没有密钥、没有账号、也没有服务端代码；静态主机按原样返回文件。',
      'api.note': '基础路径 /api/ · UTF-8 · CORS * · Cache-Control no-store · 无需认证。',
      'index.title': '端点',
      'table.path': '路径',
      'table.returns': '返回',
      'index.version': '发布清单：版本、日期、大小、下载与源码链接。',
      'index.faq': '发布页渲染的双语常见问题。',
      'index.features': '功能目录；当前发布页不再加载它。',
      'index.stats': '平台、运行时、端口、Web UI/MCP 端点、协议与客户端的静态事实。',
      'index.licenses': '第三方组件及其许可证。',
      'index.site': '站点元数据与所有端点的链接。',
      'index.endpoints': '这七个文件的机器可读索引。',
      'table.method': '方法',
      'runtime.title': '运行态 REST API（/api/v1/）',
      'runtime.lead': '正在运行的程序在 Web UI 监听器上暴露一个面向自动化的 JSON API（/api/v1/）。每个操作都映射到一个 MCP 工具，脚本和 curl 可以像 MCP 客户端一样精确地控制程序。',
      'runtime.auth': '鉴权与 MCP 端点一致：回环（127.0.0.1）免密；非回环调用方需以 Authorization: Bearer &lt;key&gt;、X-MCP-Key: &lt;key&gt; 或 X-API-Key: &lt;key&gt; 提供 MCP 密钥。未设置密钥时，仅当 Web UI 密码关闭才开放。',
      'rt.index': '发现：名称、版本与完整工具目录。',
      'rt.docs': '程序内双语说明页（默认英文，可切换）。',
      'rt.status': '当前服务状态、版本、监听器与流量计数。',
      'rt.config_get': '读取运行配置（不含密码与令牌）。',
      'rt.config_post': '写入配置字段；请求体为配置对象或 {"config": {...}}。',
      'rt.service_start': '用当前配置启动代理。',
      'rt.service_stop': '停止代理；Web UI 与 MCP 端点保持运行。',
      'rt.service_restart': '停止后用当前配置重新启动。',
      'rt.logs': '读取内存日志；查询参数 since/level/limit。',
      'rt.clear': '清空内存日志。',
      'rt.tools': '列出全部 MCP 工具（名称、描述、inputSchema）。',
      'rt.tool_call': '按名称调用任意 MCP 工具；请求体为参数对象或 {"arguments": {...}}。',
      'rt.examples': '示例',
      'conventions.title': '约定',
      'conventions.lead': '/api/ 下的所有文件遵循同一组规则。',
      'conv.1': '所有端点都是 GET 请求；没有写入或需要认证的路由。',
      'conv.2': '响应为 UTF-8 JSON。字段可能增加；客户端应忽略不认识的字段。',
      'conv.3': '不需要密钥、账号或 Cookie；静态主机直接返回文件。',
      'conv.4': 'JSON 响应发送 Access-Control-Allow-Origin: * 和 Cache-Control: no-store。',
      'conv.5': '替换 JSON 文件即发布变更；没有需要重启的服务。',
      'conv.6': 'version.json 是发布元数据的唯一来源。读取失败时页面显示错误状态，不会回退到内置数据。',
      'version.desc': '由发布页和桌面更新器读取。只有 version 是必填字段；未知字段会被忽略，因此 schema 可以扩展而不破坏旧客户端。下面的值只是示例；源码字段在压缩包生成后写入。',
      'table.field': '字段',
      'table.type': '类型',
      'table.notes': '说明',
      'field.version': '最新发布版本，用于和正在运行的构建比较。',
      'field.download_url': 'Windows 构建的直链。留空时隐藏下载按钮。',
      'field.page_url': '当 download_url 是静态构建路径时，桌面更新器打开的发布页。',
      'field.min_version': '仍然支持的最旧版本；更旧的客户端会被要求更新。',
      'field.force_update': '把该版本标记为旧客户端的强制更新。',
      'field.release_date': '发布日期，建议使用 YYYY-MM-DD。',
      'field.changelog': '默认更新日志，每行一条。',
      'field.changelog_en': '英文界面使用的英文更新日志。',
      'field.file_size': 'Windows 构建大小，单位为字节。',
      'field.source_url': '源码 ZIP 的直链。留空时隐藏源码按钮。',
      'field.source_size': '源码 ZIP 大小，单位为字节。',
      'field.source_name': '按钮提示中显示的源码 ZIP 文件名。',
      'field.source_version': '源码包内部的版本号。',
      'field.source_updated': '最后一次导出源码的 UTC 时间。',
      'version.note': '更新器接受 http:// 和 https:// 链接，并会把同站相对路径按清单地址解析。缺少可选字段不会阻塞正在运行的会话。',
      'faq.desc': '发布页只请求一次该文件，并用双语渲染所有条目。切换界面语言不会再次请求。',
      'field.faq_version': '本文档的 schema 版本。',
      'field.faq_updated': '最后一次内容更新日期。',
      'field.faq_items': '按顺序排列的常见问题条目。',
      'field.faq_id': '稳定标识符。',
      'field.faq_question': '包含 en 和 zh 字符串的对象。',
      'field.faq_answer': '包含 en 和 zh 字符串的对象，按纯文本渲染。',
      'other.title': '其他文件',
      'other.lead': '这些文件用于说明；当前发布页渲染时不依赖它们，但它们仍对工具和旧版本公开。',
      'other.features': '— 版本号和双语条目列表（id、title、body）。',
      'other.stats': '— 平台、运行时、监听、Web UI/MCP 端点、协议、客户端和语言信息。',
      'other.licenses': '— 运行时组件、标准库模块和许可证名称。',
      'other.site': '— 项目名称、版本、标语、基础 URL 和链接表。',
      'other.endpoints': '— 基础路径、数量以及七个端点记录。',
      'footer.note': '静态文件。本页不设置 Cookie，也不运行统计。',
      'footer.back': '返回发布页'
    }
  };

  var state = { lang: 'en' };

  function t(key) {
    var table = dictionaries[state.lang] || dictionaries.en;
    return Object.prototype.hasOwnProperty.call(table, key)
      ? table[key]
      : (dictionaries.en[key] || key);
  }

  function setLanguage(lang) {
    if (!dictionaries[lang]) lang = 'en';
    state.lang = lang;

    if (window.SiteI18n) {
      window.SiteI18n.remember(lang);
      window.SiteI18n.apply(lang, dictionaries[lang], document);
    } else {
      document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
      document.title = t('page.title');
    }

    Array.prototype.forEach.call(document.querySelectorAll('[data-lang]'), function (button) {
      var active = button.getAttribute('data-lang') === lang;
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.classList.toggle('is-active', active);
    });
  }

  function init() {
    var preferred = window.SiteI18n ? window.SiteI18n.preferred() : 'en';
    setLanguage(preferred);
    Array.prototype.forEach.call(document.querySelectorAll('[data-lang]'), function (button) {
      button.addEventListener('click', function () {
        setLanguage(button.getAttribute('data-lang'));
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
