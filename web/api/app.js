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
      'field.faq_question': 'English question string.',
      'field.faq_answer': 'English answer string, rendered as text.',
      'other.title': 'Other files',
      'other.lead': 'These files are descriptive. The current release page does not need them to render, but they remain public for tools and older versions.',
      'other.features': '— version and a bilingual item list (id, title, body).',
      'other.stats': '— platform, runtime, listener, Web UI/MCP endpoints, protocol, client and language facts.',
      'other.licenses': '— runtime components, standard-library modules and licence names.',
      'other.site': '— project name, version, tagline, base URL and a link map.',
      'other.endpoints': '— base path, count and the seven endpoint records.',
      'footer.note': 'Static files. No cookies and no analytics on this page.',
      'footer.back': 'Back to the release page'
    }
  };

  var state = { lang: 'en' };

  function t(key) {
    var table = dictionaries.en;
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
      document.documentElement.lang = 'en';
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
