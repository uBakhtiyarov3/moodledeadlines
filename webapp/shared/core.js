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
    uz: ["yakşanba", "duşanba", "seşanba", "çorşanba", "payşanba", "juma", "şanba"],
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
    el.dataset.kind = kind || "";
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
      sheetDrag(wrap.querySelector(".sheet"));
    }
    const sheet = wrap.querySelector(".sheet");
    clearTimeout(sheetTimer);
    wrap.classList.remove("closing", "fading");
    sheet.style.transform = "";
    sheet.innerHTML = '<div class="grabber"></div>' + html;
    sheet.scrollTop = 0;
    $$(".segmented", sheet).forEach(segMotion);
    wrap.classList.add("open");
    if (tg && tg.BackButton) { tg.BackButton.show(); tg.BackButton.onClick(closeSheet); }
    if (onMount) onMount(sheet);
    return sheet;
  }
  let sheetTimer;
  function closeSheet(dragged) {
    const wrap = $("#sheet");
    if (wrap && wrap.classList.contains("open") && !wrap.classList.contains("closing") && !wrap.classList.contains("fading")) {
      const sheet = wrap.querySelector(".sheet");
      if (dragged === true) {  // already under the finger: keep sliding from where it is
        sheet.style.transform = "translateY(105%)";
        wrap.classList.add("fading");
      } else {
        sheet.style.transform = "";
        wrap.classList.add("closing");  // slide down, then really hide
      }
      clearTimeout(sheetTimer);
      sheetTimer = setTimeout(() => { wrap.classList.remove("open", "closing", "fading"); sheet.style.transform = ""; }, calm ? 0 : 260);
    }
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


  // --- motion ----------------------------------------------------------------
  const calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Dock: a glass pill slides to the active tab; pages slide in the direction of travel.
  function dockMotion(dock) {
    const pill = document.createElement("i");
    pill.className = "dock-pill";
    dock.prepend(pill);
    let last = -1;
    const place = () => {
      const btns = $$("button", dock);
      const idx = btns.findIndex((b) => b.classList.contains("active"));
      if (idx < 0 || !dock.clientWidth) return;
      const cs = getComputedStyle(dock);
      const pad = parseFloat(cs.paddingLeft) || 0, gap = parseFloat(cs.columnGap) || 0;
      const grow = parseFloat(cs.getPropertyValue("--dock-grow")) || 1;
      // the layout the tabs are animating towards (flex-grow: active = grow, others = 1)
      const unit = (dock.clientWidth - pad * 2 - gap * (btns.length - 1)) / (btns.length - 1 + grow);
      pill.style.width = grow * unit + "px";
      pill.style.transform = `translateX(${pad + idx * (unit + gap)}px)`;
      if (last >= 0 && idx !== last) document.documentElement.dataset.nav = idx > last ? "fwd" : "back";
      last = idx;
    };
    new MutationObserver(place).observe(dock, { subtree: true, attributes: true, attributeFilter: ["class"] });
    window.addEventListener("resize", place);
    place();
    requestAnimationFrame(() => requestAnimationFrame(() => dock.classList.add("ready")));
  }

  // Segmented controls: a thumb slides under the active option.
  function segMotion(seg) {
    if (seg.classList.contains("has-thumb")) return;
    const thumb = document.createElement("i");
    thumb.className = "seg-thumb";
    seg.prepend(thumb);
    seg.classList.add("has-thumb");
    const place = () => {
      const b = $("button.active", seg);
      if (!b || !b.offsetWidth) return;
      thumb.style.width = b.offsetWidth + "px";
      thumb.style.transform = `translateX(${b.offsetLeft}px)`;
      requestAnimationFrame(() => seg.classList.add("ready"));
    };
    new MutationObserver(place).observe(seg, { subtree: true, attributes: true, attributeFilter: ["class"] });
    if (window.ResizeObserver) new ResizeObserver(place).observe(seg);  // also when its page becomes visible
    place();
  }

  // Count a number up to its value (keeps any prefix/suffix, e.g. "78 %").
  function countUp(el, ms = 700) {
    const m = String(el.textContent).match(/^(\D*)(\d+(?:[.,]\d+)?)(.*)$/);
    if (!m || calm) return;
    const [, pre, num, post] = m, to = parseFloat(num.replace(",", ".")), dec = (num.split(/[.,]/)[1] || "").length;
    const sep = num.includes(",") ? "," : ".", t0 = performance.now();
    const tick = (now) => {
      const k = Math.min(1, (now - t0) / ms), eased = 1 - Math.pow(1 - k, 3);
      el.textContent = pre + (to * eased).toFixed(dec).replace(".", sep) + post;
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // A short burst of brand-coloured confetti (for finished tasks).
  function confetti(x = innerWidth / 2, y = innerHeight * 0.6) {
    if (calm) return;
    const c = document.createElement("canvas");
    c.className = "confetti";
    const dpr = Math.min(2, devicePixelRatio || 1);
    c.width = innerWidth * dpr; c.height = innerHeight * dpr;
    document.body.appendChild(c);
    const g = c.getContext("2d");
    g.scale(dpr, dpr);
    const colors = ["#8a0119", "#123654", "#ffffff", "#d2687a", "#6f93b8", "#22c55e", "#f59e0b"];
    const bits = Array.from({ length: 90 }, () => {
      const a = -Math.PI / 2 + (Math.random() - 0.5) * 2.2, v = 7 + Math.random() * 9;
      return { x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, w: 5 + Math.random() * 6, h: 3 + Math.random() * 4,
               r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.5, c: colors[(Math.random() * colors.length) | 0] };
    });
    const t0 = performance.now();
    const frame = (now) => {
      const life = (now - t0) / 1500;
      g.clearRect(0, 0, innerWidth, innerHeight);
      if (life >= 1) { c.remove(); return; }
      bits.forEach((b) => {
        b.vy += 0.32; b.vx *= 0.99; b.x += b.vx; b.y += b.vy; b.r += b.vr;
        g.save(); g.translate(b.x, b.y); g.rotate(b.r);
        g.globalAlpha = Math.max(0, 1 - life * life); g.fillStyle = b.c;
        g.fillRect(-b.w / 2, -b.h / 2, b.w, b.h); g.restore();
      });
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  // Drag a sheet down to close it.
  function sheetDrag(sheet) {
    let y0 = null, dy = 0, t0 = 0;
    sheet.addEventListener("touchstart", (e) => {
      if (sheet.scrollTop > 0 || e.target.closest("input, textarea, select")) { y0 = null; return; }
      y0 = e.touches[0].clientY; dy = 0; t0 = Date.now();
    }, { passive: true });
    sheet.addEventListener("touchmove", (e) => {
      if (y0 === null) return;
      dy = e.touches[0].clientY - y0;
      if (dy <= 0) { if (sheet.classList.contains("dragging")) sheet.style.transform = ""; return; }
      if (dy > 6) { sheet.classList.add("dragging"); e.preventDefault(); sheet.style.transform = `translateY(${dy}px)`; }
    }, { passive: false });
    sheet.addEventListener("touchend", () => {
      if (y0 === null || !sheet.classList.contains("dragging")) { y0 = null; return; }
      sheet.classList.remove("dragging");
      const fast = dy / Math.max(1, Date.now() - t0) > 0.6;
      if (dy > 120 || (fast && dy > 40)) closeSheet(true); else sheet.style.transform = "";
      y0 = null;
    });
  }

  function initMotion() {
    $$(".dock").forEach(dockMotion);
    $$(".segmented").forEach(segMotion);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initMotion); else initMotion();

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
    headset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/><path d="M21 19a3 3 0 0 1-3 3h-4"/></svg>',
    award: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M22 9 12 4 2 9l10 5 10-5z"/><path d="M6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/><path d="M22 9v6"/></svg>',
    eyeoff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c5 0 9 4.5 10 7a13 13 0 0 1-3 4.2M6.2 6.2A13 13 0 0 0 2 12c1 2.5 5 7 10 7a9.6 9.6 0 0 0 4.8-1.3"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/></svg>',
  };

  // Section to open on start. Telegram appends its own #tgWebAppData=… to the URL hash,
  // so sections travel in the query string (?p=settings); a plain #hash is a fallback.
  function startPage() {
    const q = params.get("p");
    if (q) return q;
    const h = location.hash.replace(/^#/, "").split("&")[0];
    return h.includes("=") ? "" : h;
  }

  window.UW = { tg, api, fmt, startPage, ApiError, t, setLang, translate, get lang() { return lang; }, setDict: (d) => (dict = d),
    $, $$, esc, haptic, toast, openSheet, closeSheet, confirmDialog, revealSpoilers, openLink, I,
    confetti, countUp, segMotion };
})();
