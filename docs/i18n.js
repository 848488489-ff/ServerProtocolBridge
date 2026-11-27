(function (global) {
  'use strict';

  var KEY = 'spb-site-language';
  var AVAILABLE = ['en', 'zh'];

  function remember(language) {
    try { localStorage.setItem(KEY, language); } catch (error) {   }
  }

  function fromQuery() {
    try {
      var value = new URLSearchParams(global.location.search).get('lang');
      return AVAILABLE.indexOf(value) >= 0 ? value : null;
    } catch (error) {
      return null;
    }
  }

  function remembered() {
    try {
      var value = localStorage.getItem(KEY);
      return AVAILABLE.indexOf(value) >= 0 ? value : null;
    } catch (error) {
      return null;
    }
  }

  function preferred() {
    var value = fromQuery();
    if (value) {
      remember(value);
      return value;
    }
    return remembered() || 'en';
  }

  function fill(scope, attribute, apply) {
    scope.querySelectorAll('[' + attribute + ']').forEach(function (node) {
      var text = apply(node.getAttribute(attribute));
      if (typeof text !== 'string') { return; }
      if (attribute === 'data-i18n') { node.textContent = text; }
      else if (attribute === 'data-i18n-html') { node.innerHTML = text; }
      else if (attribute === 'data-i18n-title') { node.setAttribute('title', text); }
      else if (attribute === 'data-i18n-content') { node.setAttribute('content', text); }
      else if (attribute === 'data-i18n-placeholder') { node.setAttribute('placeholder', text); }
      else if (attribute === 'data-i18n-aria-label') { node.setAttribute('aria-label', text); }
    });
  }

  function apply(language, dictionary, root) {
    var scope = root || global.document;
    var lookup = function (key) { return dictionary[key]; };
    fill(scope, 'data-i18n', lookup);
    fill(scope, 'data-i18n-html', lookup);
    fill(scope, 'data-i18n-title', lookup);
    fill(scope, 'data-i18n-content', lookup);
    fill(scope, 'data-i18n-placeholder', lookup);
    fill(scope, 'data-i18n-aria-label', lookup);
    if (typeof dictionary['page.title'] === 'string') {
      global.document.title = dictionary['page.title'];
    }
    global.document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  }

  global.SiteI18n = {
    available: AVAILABLE,
    preferred: preferred,
    remember: remember,
    apply: apply
  };
})(window);
