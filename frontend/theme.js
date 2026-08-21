(() => {
  'use strict';

  const STORAGE_KEY = 'smartfinance-theme';
  const DARK = 'dark';
  const LIGHT = 'light';
  const SYSTEM = 'system';
  const root = document.documentElement;
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = readSavedTheme();

  function readSavedTheme() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return [DARK, LIGHT, SYSTEM].includes(saved) ? saved : SYSTEM;
    } catch {
      return SYSTEM;
    }
  }

  function effectiveTheme() {
    return preference === SYSTEM ? (systemDark.matches ? DARK : LIGHT) : preference;
  }

  function translate(key, fallbackVi, fallbackEn) {
    if (window.I18n) return window.I18n.t(key);
    return root.lang === 'en' ? fallbackEn : fallbackVi;
  }

  function renderControls() {
    const dark = effectiveTheme() === DARK;
    const title = dark
      ? translate('turn_off_dark_mode', 'Tắt chế độ tối', 'Turn off dark mode')
      : translate('turn_on_dark_mode', 'Bật chế độ tối', 'Turn on dark mode');
    const label = translate('dark_mode', 'Chế độ tối', 'Dark mode');

    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('title', title);
      const icon = button.querySelector('[data-theme-icon]');
      if (icon) icon.textContent = dark ? '☀' : '☾';
    });
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
      const active = button.dataset.themeChoice === preference;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  function setTheme(next, { persist = true } = {}) {
    preference = [DARK, LIGHT, SYSTEM].includes(next) ? next : SYSTEM;
    const theme = effectiveTheme();
    root.dataset.theme = theme;
    root.dataset.themePreference = preference;
    root.style.colorScheme = theme;
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, preference);
      } catch {
        // The visual theme still works when storage is unavailable.
      }
    }
    renderControls();
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme, preference } }));
  }

  setTheme(preference, { persist: false });

  document.addEventListener('DOMContentLoaded', renderControls);
  document.addEventListener('click', event => {
    const choice = event.target.closest?.('[data-theme-choice]');
    if (choice) {
      setTheme(choice.dataset.themeChoice);
      return;
    }
    if (event.target.closest?.('[data-theme-toggle]')) {
      setTheme(effectiveTheme() === DARK ? LIGHT : DARK);
    }
  });
  systemDark.addEventListener('change', () => {
    if (preference === SYSTEM) setTheme(SYSTEM, { persist: false });
  });
  window.addEventListener('languagechange', renderControls);

  window.Theme = {
    setTheme,
    toggle: () => setTheme(effectiveTheme() === DARK ? LIGHT : DARK),
    get current() { return effectiveTheme(); },
    get preference() { return preference; },
    storageKey: STORAGE_KEY
  };
})();
