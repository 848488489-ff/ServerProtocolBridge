(function () {
  'use strict';

  var dictionaries = {
    en: {
      'page.title': 'Server Protocol Bridge — Downloads',
      'meta.description': 'A local relay for Minecraft clients that use wss:// or ws://. Windows build, Web UI, MCP control, checksums, release notes and a static API.',
      'skip': 'Skip to content',
      'brand': 'Server Protocol Bridge',
      'edition.os': 'Windows / Linux build',
      'lang.label': 'Language',
      'nav.label': 'Sections',
      'nav.download': 'Download',
      'nav.menu': 'Menu',
      'nav.how': 'What it does',
      'nav.release': 'Release',
      'nav.start': 'Run it',
      'nav.notes': 'Notes',
      'nav.api': 'API',
      'hero.breadcrumbHome': 'Home',
      'hero.breadcrumbDownloads': 'Downloads',
      'hero.heading': 'Server Protocol Bridge',
      'hero.kicker': 'Windows and Linux · 127.0.0.1 only · single executable · Web UI + MCP',
      'hero.title': 'A local relay between Minecraft clients that speak wss:// or ws:// and Java servers.',
      'hero.desc': 'Server Protocol Bridge listens on 127.0.0.1, terminates wss:// or ws://, translates the few packets a WebSocket client cannot send, and forwards the rest untouched. The Java server sees an ordinary client.',
      'action.download': 'Download for Windows',
      'action.downloadPending': 'Download link pending',
      'action.notes': 'Read the release notes',
      'action.source': 'Get source',
      'action.sourceSoon': 'Source package pending',
      'download.title': 'Download',
      'download.lead': 'Take the Windows or Linux single-file build, the Android APK, or download the source package.',
      'download.windows': 'Server Protocol Bridge for Windows',
      'download.windowsMeta': 'Windows 10/11 · x64 · single EXE',
      'download.windowsBody': 'One executable, no installer or service. The build is unsigned.',
      'download.linux': 'Server Protocol Bridge for Linux',
      'download.linuxMeta': 'Linux x86_64 · single ELF',
      'download.linuxBody': 'Single ELF binary built on Debian 12 (glibc 2.36+). With python3-gi and gir1.2-webkit2-4.1 installed it opens a native WebKitGTK window; otherwise the Web UI opens in your browser. Make it executable with chmod +x.',
      'action.linux': 'Download for Linux',
      'action.linuxSoon': 'Linux build pending',
      'release.linuxUnavailable': 'The Linux build is not available yet.',
      'download.source': 'Source package',
      'download.sourceMeta': 'Python source · Unlicense',
      'download.sourceBody': 'The archive contains the application and website source, LICENSE and THIRD_PARTY_NOTICES.txt. macOS runs from source.',
      'download.android': 'Server Protocol Bridge for Android',
      'download.androidMeta': 'Android 7.0+ · arm64-v8a',
      'download.androidBody': 'Native APK with an embedded WebView control panel. Python 3.13 is embedded; the arm64-v8a ABI is included.',
      'action.android': 'Download APK',
      'action.androidSoon': 'APK pending',
      'release.apkUnavailable': 'The APK is not available yet.',
      'download.note': 'The builds are unsigned.',
      'hero.note': 'Free and unsigned. No installer, no service, no telemetry.',
      'docket.title': 'Current build',
      'docket.version': 'Version',
      'docket.released': 'Released',
      'docket.platform': 'Platform',
      'docket.platformValue': 'Windows 10/11 · Linux x86_64',
      'docket.size': 'Size',
      'docket.min': 'Minimum',
      'docket.link': 'Direct link',
      'docket.updated': 'Updated',
      'release.optional': 'Optional update',
      'release.required': 'Required update',
      'release.reading': 'Reading manifest',
      'release.unavailable': 'Manifest unavailable',
      'release.loaded': 'Loaded from api/version.json',
      'release.status': 'Reading api/version.json…',
      'release.error': 'Could not read api/version.json.',
      'release.none': 'No release notes for this build.',
      'release.pending': 'Not published',
      'release.pendingTitle': 'The download link has not been published yet.',
      'release.sourceUnavailable': 'The source package link has not been published yet.',
      'release.title': "What's in this build",
      'release.lead': 'The 2.x line adds a browser control panel and an MCP endpoint, so the same relay can be configured by hand or driven by an AI client. The relay core stays small: game data is forwarded unchanged.',
      'release.c1.title': 'Control from the browser',
      'release.c1.body': 'The Web UI listens on http://127.0.0.1:8765 by default. Start and stop the relay, edit forwarding settings, read logs, manage accounts and install the certificate from one page. A password is optional and only allowed when the UI is bound to a non-loopback address.',
      'release.c2.title': 'MCP for AI clients',
      'release.c2.body': 'The same listener serves /mcp over JSON-RPC 2.0 and Streamable HTTP. It exposes 39 tools for status, configuration, logs, accounts, certificates and updates, plus resources and prompts. Loopback clients need no key; remote clients use an MCP key.',
      'release.c3.title': 'Sign-in and certificates',
      'release.c3.body': 'Offline accounts need no sign-in. Microsoft sign-in uses the device-code flow with a built-in public client ID; credentials refresh before every server join. A self-signed certificate is created on first run and can be installed into the Windows trust store.',
      'release.c4.title': 'A smaller gateway',
      'release.c4.body': 'FastAPI, uvicorn and the ASGI layer are gone. HTTP status pages and game traffic run directly on websockets, which handles TLS, binary frames, subprotocols and the closing handshake. Compression is off, and client data is forwarded unchanged.',
      'release.notesTitle': 'Full changelog',
      'release.notesSource': 'Read from api/version.json when the page loads.',
      'how.title': 'What it does',
      'how.lead': 'The relay is deliberately small. It handles the transport and handshake work a browser cannot do, then gets out of the way.',
      'how.note': 'It is not a VPN and it does not change your IP. A local server stays local; a public server stays public.',
      'how.listener': 'Listener',
      'how.listenerNote': 'by default; the plaintext fallback is ws://127.0.0.1:8080.',
      'how.transport': 'Transport',
      'how.transportBody': 'One process. TLS, binary frames, subprotocols and the closing handshake are handled by websockets; compression is off.',
      'how.browser': 'WebSocket clients',
      'how.browserBody': 'Handshakes from clients that support wss:// or ws:// are answered locally. Classic Java clients pass through.',
      'how.login': 'Java login',
      'how.loginBody': 'SRV lookup like the vanilla client; a login acknowledgement is sent for 1.20.2+ targets when the browser client does not send one.',
      'how.accounts': 'Accounts',
      'how.accountsBody': 'Offline by default. Microsoft sign-in uses the device-code flow. A compatible third-party account service can be added with the API root from its provider.',
      'how.certificate': 'Certificate',
      'how.certificateBody': 'A self-signed certificate is created on first run and can be installed into the Windows trust store.',
      'how.webui': 'Web UI',
      'how.webuiBody': 'A loopback-only control panel at http://127.0.0.1:8765 for start/stop, settings, logs, accounts and certificates. The desktop window is the same UI in a native webview.',
      'how.mcp': 'MCP',
      'how.mcpBody': 'The same listener exposes /mcp over JSON-RPC 2.0 and Streamable HTTP, with 39 tools, resources and prompts for AI clients.',
      'how.serverList': 'Server list',
      'how.serverListBody': 'Every list query goes to the target live. There is no status cache, so the MOTD, player count and version are current; a slow target makes that one query wait.',
      'how.excluded': 'Not included',
      'how.excludedBody': 'No anti-cheat bypass, no movement rewriting, no packet pacing, no cloud relay.',
      'start.title': 'Run it',
      'start.lead': 'The Windows build is a single EXE. The first run creates a certificate and starts a local listener; nothing is installed as a service.',
      'start.step1.title': 'Download and run',
      'start.step1.body': 'Start the EXE. SmartScreen will warn because the build is unsigned; choose More info → Run anyway.',
      'start.step2.title': 'Set the target',
      'start.step2.body': 'Enter the Java server address in the app. SRV records are used when the address has no port.',
      'start.step3.title': 'Connect the browser client',
      'start.step3.body': 'Use wss://127.0.0.1:8443 in any client that accepts a wss:// address. The plaintext fallback is ws://127.0.0.1:8080.',
      'start.step4.title': 'Join the server',
      'start.step4.body': 'Start the relay and connect. The app shows the handshake and any kick reason as readable text.',
      'start.sourceTitle': 'From source',
      'start.sourceLead': 'The source package is a Python project; it also runs on Linux and macOS. Unzip it and install the dependencies:',
      'start.note': 'The Linux release is a single ELF (glibc 2.36+); macOS runs from source.',
      'start.controlTitle': 'Control and automation',
      'start.controlLead': 'The desktop window is the Web UI in a native webview. Open the same address in a browser, or point an MCP client at /mcp:',
      'start.controlNote': 'Both are loopback-only by default. A Web UI password can only be set on a non-loopback bind; remote MCP requires an MCP key.',
      'start.requirements': 'Requirements: Windows 10/11 x64 and the Microsoft Visual C++ Redistributable. The native window uses the system Edge WebView2 runtime; the Web UI works in any current browser.',
      'notes.title': 'Notes and limits',
      'notes.lead': 'The short version: this is a local transport relay, not a cheat, a VPN, or a hosted service.',
      'notes.antiCheatTitle': 'Anti-cheat',
      'notes.antiCheatBody': 'Movement packets are not rewritten, transaction probes are not answered, and idle position packets are not sent. A server-side anti-cheat that is sensitive to jitter can still flag a connection through any relay; this build does not try to work around that.',
      'faq.loading': 'Loading FAQ …',
      'faq.error': 'FAQ could not be loaded. The rest of the page is unaffected.',
      'faq.empty': 'No FAQ entries are published for this build.',
      'api.title': 'Static JSON',
      'api.lead': "The release page and the app's updater read the same manifest. Everything under /api/ is a static file with CORS enabled.",
      'api.note': 'Seven endpoints. No key, no account, no server-side code.',
      'api.docs': 'Open the field reference',
      'api.path': 'Path',
      'api.returns': 'Returns',
      'api.version': 'Release manifest: version, date, size, download and source links.',
      'api.faq': 'The bilingual Q&A above.',
      'api.features': 'Bilingual feature catalogue, also used by older pages.',
      'api.stats': 'Platform, runtime, ports, Web UI/MCP endpoints and supported clients.',
      'api.licenses': 'Third-party components and licenses.',
      'api.site': 'Site metadata and links to every endpoint.',
      'api.endpoints': 'Machine-readable index of these seven endpoints.',
      'footer.statement': 'A local relay for Minecraft web clients. A native Python webview window plus a loopback-only Web UI and MCP endpoint; no cloud service in the middle.',
      'footer.licenseLine': 'Unlicense. Third-party notices ship with the source package.',
      'footer.links': 'Links',
      'footer.download': 'Download',
      'footer.api': 'API reference',
      'footer.license': 'License',
      'footer.version': 'version.json',
      'footer.top': 'Back to top',
      'footer.rights': '© 2026 Server Protocol Bridge',
      'footer.note': 'Release data comes from api/version.json. This page sets no cookies and runs no analytics.'
    }
  };

  var state = {
    lang: 'en',
    release: null,
    releaseState: 'loading',
    releaseError: '',
    faq: null,
    faqState: 'loading'
  };

  var PLACEHOLDER_HOSTS = ['example.com', 'example.org', 'example.net'];

  function byId(id) {
    return document.getElementById(id);
  }

  function all(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function t(key) {
    var table = dictionaries.en;
    return Object.prototype.hasOwnProperty.call(table, key)
      ? table[key]
      : (dictionaries.en[key] || key);
  }

  function setText(id, value, title) {
    var node = byId(id);
    if (!node) return;
    node.textContent = value;
    if (typeof title === 'string') node.title = title;
  }

  function trim(value) {
    return value == null ? '' : String(value).trim();
  }

  function normalizeRelease(raw) {
    function get(key) {
      if (Object.prototype.hasOwnProperty.call(raw, key)) return raw[key];
      var spaced = key + ' ';
      if (Object.prototype.hasOwnProperty.call(raw, spaced)) return raw[spaced];
      var found = Object.keys(raw).find(function (name) {
        return String(name).trim() === key;
      });
      return found ? raw[found] : undefined;
    }

    function bool(value) {
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string') {
        return ['true', '1', 'yes', 'on'].indexOf(value.trim().toLowerCase()) >= 0;
      }
      return Boolean(value);
    }

    return {
      version: trim(get('version')),
      download_url: trim(get('download_url')),
      min_version: trim(get('min_version')),
      force_update: bool(get('force_update')),
      release_date: trim(get('release_date')),
      changelog_en: trim(get('changelog_en')),
      file_size: Number(trim(get('file_size'))) || 0,
      source_url: trim(get('source_url')),
      source_size: Number(trim(get('source_size'))) || 0,
      source_name: trim(get('source_name')),
      source_version: trim(get('source_version')),
      source_updated: trim(get('source_updated')),
      apk_url: trim(get('apk_url')),
      apk_size: Number(trim(get('apk_size'))) || 0,
      apk_name: trim(get('apk_name')),
      apk_version: trim(get('apk_version')),
      apk_updated: trim(get('apk_updated')),
      linux_url: trim(get('linux_url')),
      linux_size: Number(trim(get('linux_size'))) || 0,
      linux_name: trim(get('linux_name')),
      linux_version: trim(get('linux_version')),
      linux_updated: trim(get('linux_updated'))
    };
  }

  function usableUrl(value) {
    var url = trim(value);
    if (/^https?:\/\//i.test(url)) {
      try {
        var parsed = new URL(url);
        if (PLACEHOLDER_HOSTS.indexOf(parsed.hostname.toLowerCase()) >= 0) return '';
        return url;
      } catch (error) {
        return '';
      }
    }
    // The release and its downloads can live on the same static host.  A same-site
    // absolute path is resolved against this origin so the button still works when
    // the manifest and the build are uploaded together.
    if (/^\/(?!\/)/.test(url)) {
      try {
        var resolved = new URL(url, location.href);
        if (resolved.origin === location.origin) return resolved.pathname + resolved.search + resolved.hash;
      } catch (error) {
        return '';
      }
    }
    return '';
  }

  function formatSize(bytes) {
    if (!bytes || bytes < 0) return '—';
    if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB';
    return bytes + ' B';
  }

  function formatDate(value) {
    var text = trim(value);
    if (!text) return '—';
    var date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(text) ? text + 'T00:00:00Z' : text);
    if (isNaN(date.getTime())) return text;
    try {
      return new Intl.DateTimeFormat('en-GB', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        timeZone: 'UTC'
      }).format(date);
    } catch (error) {
      return text;
    }
  }

  function middleEllipsis(value, max) {
    var text = String(value || '');
    if (text.length <= max) return text;
    var keep = Math.floor((max - 1) / 2);
    return text.slice(0, keep) + '…' + text.slice(-keep);
  }

  function renderChangelog(notes) {
    var box = byId('changelog');
    if (!box) return;
    box.textContent = '';
    var lines = String(notes || '').split(/\r?\n/).map(function (line) {
      return line.replace(/^\s*[-*•]\s*/, '').trim();
    }).filter(Boolean);
    if (!lines.length) {
      var empty = document.createElement('p');
      empty.className = 'changelog-empty';
      empty.textContent = t('release.none');
      box.appendChild(empty);
      return;
    }
    var list = document.createElement('ol');
    list.className = 'changelog-list';
    lines.forEach(function (line) {
      var item = document.createElement('li');
      item.textContent = line;
      list.appendChild(item);
    });
    box.appendChild(list);
  }

  function fallbackUrl(node) {
    return node ? usableUrl(node.getAttribute('data-fallback-url') || '') : '';
  }

  function setDownloadHref(value) {
    var primary = usableUrl(value);
    all('[data-download-button]').forEach(function (button) {
      var url = primary || fallbackUrl(button);
      var label = button.querySelector('[data-download-label]');
      if (url) {
        button.href = url;
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
        button.removeAttribute('aria-disabled');
        button.removeAttribute('tabindex');
        button.classList.remove('is-disabled');
        if (label) label.textContent = t('action.download');
      } else {
        button.href = '#';
        button.removeAttribute('target');
        button.removeAttribute('rel');
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('tabindex', '-1');
        button.classList.add('is-disabled');
        if (label) label.textContent = t('action.downloadPending');
      }
    });

    var link = byId('download-url');
    if (!link) return;
    var linkUrl = primary || fallbackUrl(link);
    if (linkUrl) {
      link.href = linkUrl;
      link.textContent = middleEllipsis(linkUrl, 54);
      link.title = linkUrl;
      link.removeAttribute('aria-disabled');
      link.removeAttribute('tabindex');
      link.classList.remove('is-disabled');
    } else {
      link.href = '#';
      link.textContent = t('release.pending');
      link.title = t('release.pendingTitle');
      link.setAttribute('aria-disabled', 'true');
      link.setAttribute('tabindex', '-1');
      link.classList.add('is-disabled');
    }
  }

  function setDownloadMeta(data) {
    var version = data && data.version ? 'v' + data.version : '—';
    var size = data && data.file_size ? formatSize(data.file_size) : '—';
    var date = data ? formatDate(data.release_date) : '—';
    all('[data-download-meta-version]').forEach(function (node) { node.textContent = version; });
    all('[data-download-meta-size]').forEach(function (node) {
      node.textContent = size;
      node.title = data && data.file_size ? data.file_size + ' bytes' : '';
    });
    all('[data-download-meta-date]').forEach(function (node) { node.textContent = date; });
  }

  function setSourceMeta(data) {
    var size = data && data.source_size ? formatSize(data.source_size) : '—';
    var date = data ? formatDate(data.source_updated) : '—';
    all('[data-source-meta-size]').forEach(function (node) {
      node.textContent = size;
      node.title = data && data.source_size ? data.source_size + ' bytes' : '';
    });
    all('[data-source-meta-date]').forEach(function (node) { node.textContent = date; });
  }

  function setSourceHref(data) {
    all('[data-source-button]').forEach(function (button) {
      var url = usableUrl(data && data.source_url) || fallbackUrl(button);
      var label = button.querySelector('[data-source-label]');
      if (url) {
        button.href = url;
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
        button.removeAttribute('aria-disabled');
        button.removeAttribute('tabindex');
        button.classList.remove('is-disabled');
        if (label) label.textContent = t('action.source');
        var meta = [];
        if (data && data.source_name) meta.push(data.source_name);
        if (data && data.source_size) meta.push(formatSize(data.source_size));
        button.title = meta.join(' · ') || t('action.source');
      } else {
        button.href = '#';
        button.removeAttribute('target');
        button.removeAttribute('rel');
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('tabindex', '-1');
        button.classList.add('is-disabled');
        if (label) label.textContent = t('action.sourceSoon');
        button.title = t('release.sourceUnavailable');
      }
    });
  }

  function setApkMeta(data) {
    var size = data && data.apk_size ? formatSize(data.apk_size) : '—';
    var date = data ? formatDate(data.apk_updated) : '—';
    var version = data && data.apk_version ? data.apk_version : (data && data.version ? data.version : '—');
    all('[data-apk-meta-size]').forEach(function (node) {
      node.textContent = size;
      node.title = data && data.apk_size ? data.apk_size + ' bytes' : '';
    });
    all('[data-apk-meta-version]').forEach(function (node) { node.textContent = version; });
    all('[data-apk-meta-date]').forEach(function (node) { node.textContent = date; });
  }

  function setApkHref(data) {
    all('[data-apk-button]').forEach(function (button) {
      var url = usableUrl(data && data.apk_url) || fallbackUrl(button);
      var label = button.querySelector('[data-apk-label]');
      if (url) {
        button.href = url;
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
        button.removeAttribute('aria-disabled');
        button.removeAttribute('tabindex');
        button.classList.remove('is-disabled');
        if (label) label.textContent = t('action.android');
        var meta = [];
        if (data && data.apk_name) meta.push(data.apk_name);
        if (data && data.apk_size) meta.push(formatSize(data.apk_size));
        button.title = meta.join(' · ') || t('action.android');
      } else {
        button.href = '#';
        button.removeAttribute('target');
        button.removeAttribute('rel');
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('tabindex', '-1');
        button.classList.add('is-disabled');
        if (label) label.textContent = t('action.androidSoon');
        button.title = t('release.apkUnavailable');
      }
    });
  }

  function setLinuxMeta(data) {
    var size = data && data.linux_size ? formatSize(data.linux_size) : '—';
    var date = data ? formatDate(data.linux_updated) : '—';
    var version = data && data.linux_version ? data.linux_version : (data && data.version ? data.version : '—');
    all('[data-linux-meta-size]').forEach(function (node) {
      node.textContent = size;
      node.title = data && data.linux_size ? data.linux_size + ' bytes' : '';
    });
    all('[data-linux-meta-version]').forEach(function (node) { node.textContent = version; });
    all('[data-linux-meta-date]').forEach(function (node) { node.textContent = date; });
  }

  function setLinuxHref(data) {
    all('[data-linux-button]').forEach(function (button) {
      var url = usableUrl(data && data.linux_url) || fallbackUrl(button);
      var label = button.querySelector('[data-linux-label]');
      if (url) {
        button.href = url;
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
        button.removeAttribute('aria-disabled');
        button.removeAttribute('tabindex');
        button.classList.remove('is-disabled');
        if (label) label.textContent = t('action.linux');
        var meta = [];
        if (data && data.linux_name) meta.push(data.linux_name);
        if (data && data.linux_size) meta.push(formatSize(data.linux_size));
        button.title = meta.join(' · ') || t('action.linux');
      } else {
        button.href = '#';
        button.removeAttribute('target');
        button.removeAttribute('rel');
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('tabindex', '-1');
        button.classList.add('is-disabled');
        if (label) label.textContent = t('action.linuxSoon');
        button.title = t('release.linuxUnavailable');
      }
    });
  }

  function renderRelease() {
    var status = byId('release-status');
    var policy = byId('update-policy');

    if (!state.release) {
      if (status) {
        status.hidden = false;
        status.classList.toggle('is-warning', state.releaseState === 'error');
        status.textContent = t(state.releaseState === 'error' ? 'release.error' : 'release.status');
        status.title = state.releaseError || '';
      }
      if (policy) {
        policy.textContent = t(state.releaseState === 'error'
          ? 'release.unavailable'
          : 'release.reading');
        policy.classList.remove('is-required');
        policy.classList.add('is-pending');
      }
      all('[data-release-size]').forEach(function (node) {
        node.textContent = '—';
        node.title = '';
      });
      setDownloadMeta(null);
      setSourceMeta(null);
      setDownloadHref('');
      setSourceHref(null);
      setApkMeta(null);
      setApkHref(null);
      setLinuxMeta(null);
      setLinuxHref(null);
      return;
    }

    var data = state.release;
    setText('edition-version', data.version ? 'v' + data.version : '—');
    setText('edition-date', formatDate(data.release_date));
    setText('release-title-version', data.version ? 'v' + data.version : '—');
    setText('version', data.version || '—');
    setText('release-date', formatDate(data.release_date));
    setText('file-size', formatSize(data.file_size),
      data.file_size ? data.file_size + ' bytes' : '');
    all('[data-release-size]').forEach(function (node) {
      node.textContent = formatSize(data.file_size);
      node.title = data.file_size ? data.file_size + ' bytes' : '';
    });
    setText('min-version', data.min_version || '—');

    if (policy) {
      policy.textContent = t(data.force_update ? 'release.required' : 'release.optional');
      policy.classList.toggle('is-required', Boolean(data.force_update));
      policy.classList.remove('is-pending');
    }

    var notes = data.changelog_en || data.changelog;
    renderChangelog(notes);
    setDownloadMeta(data);
    setSourceMeta(data);
    setApkMeta(data);
    setApkHref(data);
    setLinuxMeta(data);
    setLinuxHref(data);
    setDownloadHref(data.download_url);
    setSourceHref(data);

    if (status) {
      status.hidden = false;
      status.classList.remove('is-warning');
      status.textContent = t('release.loaded');
      status.title = '';
    }
  }

  function renderFaq() {
    var box = byId('faq-list');
    if (!box) return;
    box.textContent = '';

    if (state.faqState === 'loading') {
      var loading = document.createElement('p');
      loading.className = 'faq-state';
      loading.textContent = t('faq.loading');
      box.appendChild(loading);
      return;
    }

    if (state.faqState === 'error') {
      var error = document.createElement('p');
      error.className = 'faq-state is-warning';
      error.textContent = t('faq.error');
      box.appendChild(error);
      return;
    }

    var items = state.faq || [];
    if (!items.length) {
      var empty = document.createElement('p');
      empty.className = 'faq-state';
      empty.textContent = t('faq.empty');
      box.appendChild(empty);
      return;
    }

    items.forEach(function (item) {
      var question = item && item.question;
      var answer = item && item.answer;
      var q = question && (question.en || question.zh);
      var a = answer && (answer.en || answer.zh);
      if (!q || !a) return;
      var article = document.createElement('article');
      article.className = 'faq-item';
      var heading = document.createElement('h3');
      heading.textContent = q;
      var body = document.createElement('p');
      body.textContent = a;
      article.appendChild(heading);
      article.appendChild(body);
      box.appendChild(article);
    });
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

    all('[data-lang]').forEach(function (button) {
      var active = button.getAttribute('data-lang') === lang;
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.classList.toggle('is-active', active);
    });

    renderRelease();
    renderFaq();
  }

  function loadRelease() {
    state.release = null;
    state.releaseState = 'loading';
    state.releaseError = '';
    renderRelease();

    fetch('api/version.json', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (raw) {
        var data = normalizeRelease(raw);
        if (!data.version) throw new Error('version is missing');
        state.release = data;
        state.releaseState = 'ready';
        renderRelease();
      })
      .catch(function (error) {
        state.release = null;
        state.releaseState = 'error';
        state.releaseError = String(error && error.message ? error.message : error);
        renderRelease();
      });
  }

  function loadFaq() {
    state.faq = null;
    state.faqState = 'loading';
    renderFaq();

    fetch('api/faq.json', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        state.faq = Array.isArray(data.items) ? data.items : [];
        state.faqState = 'ready';
        renderFaq();
      })
      .catch(function () {
        state.faq = null;
        state.faqState = 'error';
        renderFaq();
      });
  }

  function initLanguageButtons() {
    all('[data-lang]').forEach(function (button) {
      button.addEventListener('click', function () {
        setLanguage(button.getAttribute('data-lang'));
      });
    });
  }

  function initDisabledLinks() {
    document.addEventListener('click', function (event) {
      var target = event.target.closest ? event.target.closest('[aria-disabled="true"]') : null;
      if (target) event.preventDefault();
    });
  }

  function init() {
    var preferred = window.SiteI18n ? window.SiteI18n.preferred() : 'en';
    setLanguage(preferred);
    initLanguageButtons();
    initDisabledLinks();
    loadRelease();
    loadFaq();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
