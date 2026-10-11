// Shared runtime for UWED Mini Apps: Telegram bridge, API client, i18n, UI helpers.
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  const params = new URLSearchParams(location.search);

  function applyTheme() {
    const inTg = tg && tg.initData;
    const scheme = (inTg && tg.colorScheme) || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = scheme;
    if (tg) {
      const bg = scheme === "dark" ? "#060b1a" : "#eaf0fb";
      try { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); tg.setBottomBarColor && tg.setBottomBarColor(bg); } catch (e) {}
    }
  }

  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
    tg.onEvent("themeChanged", applyTheme);
  }
  applyTheme();

  // --- i18n --------------------------------------------------------------
  let dict = {};
  let lang = "uz";
  function setLang(l) { lang = ["uz", "ru", "en"].includes(l) ? l : "uz"; document.documentElement.lang = lang; translate(); }
  function t(key, vars) {
    const e = dict[key];
    let s = (e && (e[lang] || e.uz)) || key;
    if (vars) for (const k in vars) s = s.replaceAll("{" + k + "}", vars[k]);
    return s;
  }
  function translate(root) {
    (root || document).querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
    (root || document).querySelectorAll("[data-i18n-html]").forEach((el) => (el.innerHTML = t(el.dataset.i18nHtml)));
    (root || document).querySelectorAll("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
  }

  // --- dates (own names: many WebViews lack the uz-UZ locale) --------------
  const MONTHS = {
    uz: ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"],
    ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  };
  const WEEKDAYS = {
    uz: ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"],
    ru: ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"],
    en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  };
  const pad = (n) => String(n).padStart(2, "0");
  const fmt = {
    time: (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`,
    day: (d) => `${d.getDate()}-${MONTHS[lang][d.getMonth()]}`.replace(/^(\d+)-/, lang === "uz" ? "$1-" : "$1 "),
    dayLong: (d) => { const w = WEEKDAYS[lang][d.getDay()]; return (lang === "en" ? w : w[0].toUpperCase() + w.slice(1)) + ", " + fmt.day(d); },
    dateTime: (d) => `${fmt.day(d)}, ${fmt.time(d)}`,
  };

  // --- API ---------------------------------------------------------------
  class ApiError extends Error {
    constructor(status, detail) { super(detail || String(status)); this.status = status; this.detail = detail; }
  }
  async function api(path, opts = {}) {
    const headers = { Authorization: "tma " + ((tg && tg.initData) || params.get("initData") || "") };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw new ApiError(res.status, data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)));
    return data;
  }

  // --- UI helpers ----------------------------------------------------------
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function haptic(kind) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (["success", "error", "warning"].includes(kind)) tg.HapticFeedback.notificationOccurred(kind);
      else if (kind === "select") tg.HapticFeedback.selectionChanged();
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) {}
  }
  let toastTimer;
  function toast(msg, kind) {
    let el = $("#toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast glass strong";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    haptic(kind === "error" ? "error" : kind === "success" ? "success" : "light");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }
  function openSheet(html, onMount) {
    let wrap = $("#sheet");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "sheet";
      wrap.className = "sheet-wrap";
      wrap.innerHTML = '<div class="scrim"></div><div class="sheet glass strong" role="dialog" aria-modal="true"></div>';
      document.body.appendChild(wrap);
      wrap.querySelector(".scrim").onclick = closeSheet;
    }
    const sheet = wrap.querySelector(".sheet");
    sheet.innerHTML = '<div class="grabber"></div>' + html;
    wrap.classList.add("open");
    if (tg && tg.BackButton) { tg.BackButton.show(); tg.BackButton.onClick(closeSheet); }
    if (onMount) onMount(sheet);
    return sheet;
  }
  function closeSheet() {
    const wrap = $("#sheet");
    if (wrap) wrap.classList.remove("open");
    if (tg && tg.BackButton) { tg.BackButton.offClick(closeSheet); tg.BackButton.hide(); }
  }
  function confirmDialog(msg) {
    return new Promise((resolve) => {
      if (tg && tg.showConfirm && tg.platform !== "unknown") tg.showConfirm(msg, resolve);
      else resolve(window.confirm(msg));
    });
  }
  function revealSpoilers(root) {
    $$("tg-spoiler, .spoiler", root).forEach((s) => (s.onclick = () => s.classList.add("revealed")));
  }
  function openLink(url) {
    if (tg && tg.openLink) tg.openLink(url); else window.open(url, "_blank");
  }

  // Tiny inline icon set (SF-Symbols-like strokes)
  const I = {
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3.4 20.4 21 12 3.4 3.6 3.4 10l12.6 2-12.6 2z"/></svg>',
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3"/></svg>',
    megaphone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 11v2a2 2 0 0 0 2 2h2l6 4V5L7 9H5a2 2 0 0 0-2 2z"/><path d="M17 8a5 5 0 0 1 0 8"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5a3 3 0 1 0-5.9.8A3 3 0 0 0 4 11a3 3 0 0 0 1.5 5.4A3 3 0 0 0 12 18z"/><path d="M12 5a3 3 0 1 1 5.9.8A3 3 0 0 1 20 11a3 3 0 0 1-1.5 5.4A3 3 0 0 1 12 18z"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/></svg>',
  };

  window.UW = { tg, api, fmt, ApiError, t, setLang, translate, get lang() { return lang; }, setDict: (d) => (dict = d),
    $, $$, esc, haptic, toast, openSheet, closeSheet, confirmDialog, revealSpoilers, openLink, I };
})();
