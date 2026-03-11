/* ─── Preparer Dashboard JS ─── */

(function () {
  'use strict';

  // ── 1. Tab persistence ────────────────────────────────────────────────────
  var STORAGE_KEY = 'preparer_active_tab_' + window.location.pathname;

  var tabEls = document.querySelectorAll('#clientTabs [data-bs-toggle="tab"]');
  if (tabEls.length) {
    var saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      var target = document.querySelector('[data-bs-target="' + saved + '"]');
      if (target) {
        new bootstrap.Tab(target).show();
      }
    }
    tabEls.forEach(function (el) {
      el.addEventListener('shown.bs.tab', function (e) {
        sessionStorage.setItem(STORAGE_KEY, e.target.getAttribute('data-bs-target'));
      });
    });
  }

  // ── 2. Prior-year compare selector ───────────────────────────────────────
  var compareSelect = document.getElementById('compare-year-select');
  if (compareSelect) {
    compareSelect.addEventListener('change', function () {
      var url = new URL(window.location.href);
      if (this.value) {
        url.searchParams.set('compare_year', this.value);
      } else {
        url.searchParams.delete('compare_year');
      }
      window.location.href = url.toString();
    });
  }

  // ── 3. Confidence bar coloring ────────────────────────────────────────────
  document.querySelectorAll('.conf-bar[data-conf]').forEach(function (bar) {
    var conf = parseFloat(bar.getAttribute('data-conf'));
    if (conf < 0.30) {
      bar.style.background = '#dc3545';   // red
    } else if (conf < 0.55) {
      bar.style.background = '#ffc107';   // amber
    } else {
      bar.style.background = '#198754';   // green
    }
  });

})();
