(function () {
  const { api, t, $, $$, esc, toast, haptic, openSheet, closeSheet, confirmDialog, revealSpoilers, openLink, I, tg } = UW;
  const MOODLE = "https://moodle.uwed.uz";
  let me = null;
  let scope = "upcoming";
  let items = [];
  let courses = [];

  // ---------- helpers ----------
  // [[value, unit], [value, unit]] for the two largest units
  function leftParts(ms) {
    const m = Math.max(0, Math.floor(ms / 60000));
    const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
    if (d) return [[d, t("days")], [h, t("hours")]];
    if (h) return [[h, t("hours")], [mm, t("mins")]];
    return [[mm, t("mins")]];
  }
  function left(ms) { return leftParts(ms).filter(([v], i) => v || i === 0).map(([v, u]) => `${v} ${u}`).join(" "); }
  function urgency(ms) { return ms < 6 * 3600e3 ? "u-high" : ms < 24 * 3600e3 ? "u-mid" : "u-low"; }
  const fmtTime = UW.fmt.time;
  function dayLabel(d) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const x = new Date(d); x.setHours(0, 0, 0, 0);
    const diff = Math.round((x - today) / 864e5);
    if (diff === 0) return t("today");
    if (diff === 1) return t("tomorrow");
    return UW.fmt.dayLong(d);
  }
  function errText(e) {
    if (e.status === 401) return t("err_open_in_tg");
    const k = "err_" + e.detail;
    return t(k) !== k ? t(k) : t(e.detail) !== e.detail ? t(e.detail) : t("err_generic");
  }
  function offsetLabel(o) {
    if (o % 1440 === 0) return `${o / 1440} ${t("days")}`;
    if (o >= 60) return `${o / 60} ${t("hours")}`;
    return `${o} ${t("mins")}`;
  }

  // ---------- navigation ----------
  function show(page) {
    if (page === "deadlines" && me && !me.linked) page = "connect";
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + page));
    const tab = page === "connect" ? "deadlines" : page;
    $$("#dock button").forEach((b) => b.classList.toggle("active", b.dataset.page === tab));
    if (page === "ai") loadChat();
    window.scrollTo({ top: 0 });
  }
  $$("#dock button").forEach((b) => (b.onclick = () => { haptic("select"); show(b.dataset.page); }));
  $$("[data-icon]").forEach((el) => (el.innerHTML = I[el.dataset.icon]));

  // ---------- deadlines ----------
  function renderHero() {
    const now = Date.now();
    const up = scope === "upcoming" ? items : [];
    const hero = $("#hero");
    if (scope !== "upcoming") { hero.classList.add("hidden"); return; }
    hero.classList.remove("hidden");
    if (!up.length) {
      hero.innerHTML = `<div style="font-size:48px">🌿</div><div class="grow"><div class="what">${t("all_clear")}</div><div class="muted small">${t("all_clear_d")}</div></div>`;
      return;
    }
    const next = up[0];
    const ms = new Date(next.due_at) - now;
    const span = 72 * 3600e3;
    const frac = Math.max(0.04, Math.min(1, ms / span));
    const C = 2 * Math.PI * 34;
    const color = ms < 6 * 3600e3 ? "var(--danger)" : ms < 24 * 3600e3 ? "var(--warn)" : "var(--ok)";
    const endOfDay = new Date(); endOfDay.setHours(23, 59, 59, 999);
    const todayN = up.filter((d) => new Date(d.due_at) <= endOfDay).length;
    const weekN = up.filter((d) => new Date(d.due_at) - now < 7 * 864e5).length;
    const [[v, u]] = leftParts(ms);
    hero.innerHTML = `
      <div class="ring">
        <svg viewBox="0 0 80 80"><circle class="track" cx="40" cy="40" r="34" fill="none" stroke-width="7"/>
          <circle class="bar" cx="40" cy="40" r="34" fill="none" stroke="${color}" stroke-width="7" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - frac)}"/></svg>
        <div class="label"><div>${esc(v)}<small>${esc(u || "")}</small></div></div>
      </div>
      <div class="grow">
        <div class="kicker">${t("next_deadline")}</div>
        <div class="what">${esc(next.title)}</div>
        <div class="muted small ellipsis">${esc(next.course || "")}</div>
        <div class="stats">
          ${todayN ? `<span class="chip danger">${t("n_today", { n: todayN })}</span>` : ""}
          <span class="chip">${t("n_week", { n: weekN })}</span>
          <span class="chip">${t("n_upcoming", { n: up.length })}</span>
        </div>
      </div>`;
    hero.onclick = () => openDetail(next);
  }

  function renderList() {
    const box = $("#deadline-list");
    if (!items.length) {
      box.innerHTML = scope === "upcoming" ? "" :
        `<div class="glass empty"><div class="art">${scope === "done" ? "✅" : "🗂"}</div><div class="muted">${t(scope === "done" ? "empty_done" : "empty_past")}</div></div>`;
      return;
    }
    const now = Date.now();
    let html = "", lastDay = "";
    items.forEach((d) => {
      const due = new Date(d.due_at);
      const label = dayLabel(due);
      if (label !== lastDay) { html += `<div class="day-label">${esc(label)}</div>`; lastDay = label; }
      const ms = due - now;
      const right = scope === "upcoming"
        ? `<b>${esc(left(ms))}</b><span>${fmtTime(due)}</span>`
        : `<b>${fmtTime(due)}</b><span>${UW.fmt.day(due)}</span>`;
      html += `<div class="glass dl ${scope === "upcoming" ? urgency(ms) : ""} ${d.completed ? "is-done" : ""}" data-id="${d.id}">
        <div class="stripe"></div>
        <div class="grow"><div class="t">${esc(d.title)}</div><div class="c ellipsis">${esc(d.course || "")}</div></div>
        <div class="when">${right}</div></div>`;
    });
    box.innerHTML = html;
    $$(".dl", box).forEach((el) => (el.onclick = () => openDetail(items.find((x) => x.id == el.dataset.id))));
  }

  async function loadDeadlines() {
    if (!me.linked) return;
    $("#deadline-list").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
    try {
      const r = await api("/api/deadlines?scope=" + scope);
      items = r.items; courses = r.courses;
      renderHero(); renderList(); renderCourses();
    } catch (e) { toast(errText(e), "error"); $("#deadline-list").innerHTML = ""; }
  }

  function openDetail(d) {
    if (!d) return;
    haptic("light");
    const due = new Date(d.due_at);
    const ms = due - Date.now();
    openSheet(`<div class="detail">
        <h2>${esc(d.title)}</h2>
        ${d.course ? `<span class="chip">🎓 ${esc(d.course)}</span>` : ""}
        <div class="row" style="margin-top:14px">
          <div class="grow"><div class="muted small">${dayLabel(due)}</div><div style="font-weight:700;font-size:18px">${fmtTime(due)}</div></div>
          ${ms > 0 ? `<span class="chip ${urgency(ms) === "u-high" ? "danger" : urgency(ms) === "u-mid" ? "warn" : "ok"}">${esc(left(ms))} ${t("left")}</span>` : ""}
        </div>
        ${d.description ? `<div class="desc">${esc(d.description)}</div>` : ""}
        ${d.completed_auto ? `<div class="chip ok" style="margin-top:8px">🤖 ${t("auto_done")}</div>` : ""}
        <div class="actions">
          <button class="btn ${d.completed ? "ghost" : ""} block" id="toggle-done">${t(d.completed ? "mark_undone" : "mark_done")}</button>
          ${d.url ? `<button class="btn ghost block" id="open-url">${t("open_moodle")}</button>` : ""}
        </div></div>`, (sheet) => {
      $("#toggle-done", sheet).onclick = async () => {
        try {
          await api(`/api/deadlines/${d.id}/done`, { body: { done: !d.completed } });
          toast(t("marked"), "success"); closeSheet(); loadDeadlines();
        } catch (e) { toast(errText(e), "error"); }
      };
      const ou = $("#open-url", sheet);
      if (ou) ou.onclick = () => openLink(d.url);
    });
  }

  $$("#scope button").forEach((b) => (b.onclick = () => {
    haptic("select");
    $$("#scope button").forEach((x) => x.classList.toggle("active", x === b));
    scope = b.dataset.scope; loadDeadlines();
  }));

  $("#btn-sync").innerHTML = I.refresh;
  $("#btn-sync").onclick = async () => {
    const btn = $("#btn-sync");
    btn.style.animation = "spin 1s linear infinite";
    $("#sync-status").textContent = t("syncing");
    try {
      const r = await api("/api/moodle/sync", { body: {} });
      me = r.user; toast(t("sync_ok"), "success"); renderSync(); loadDeadlines();
    } catch (e) { toast(errText(e), "error"); renderSync(); }
    btn.style.animation = "";
  };
  const spin = document.createElement("style");
  spin.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
  document.head.appendChild(spin);

  function renderSync() {
    $("#hello").textContent = t("hello", { name: me.first_name || "" });
    $("#sync-status").textContent = me.last_sync_at
      ? t("synced", { t: fmtTime(new Date(me.last_sync_at)) })
      : t("never_synced");
  }

  // ---------- connect ----------
  $("#open-export").onclick = () => openLink(MOODLE + "/calendar/export.php");
  $("#paste").onclick = async () => {
    try { $("#ical-url").value = await navigator.clipboard.readText(); haptic("light"); }
    catch (e) { $("#ical-url").focus(); }
  };
  $("#connect-btn").onclick = async () => {
    const url = $("#ical-url").value.trim();
    if (!url) { $("#ical-url").focus(); return; }
    const btn = $("#connect-btn");
    btn.disabled = true; btn.textContent = t("connecting");
    try {
      const r = await api("/api/moodle/ical", { body: { url } });
      me = r.user;
      toast(t("linked_ok", { n: r.count }), "success");
      if (tg && tg.showConfetti) tg.showConfetti();
      renderSettings(); renderSync(); show("deadlines"); loadDeadlines();
    } catch (e) { toast(errText(e), "error"); }
    btn.disabled = false; btn.textContent = t("connect_btn");
  };

  // ---------- AI chat ----------
  let chatLoaded = false;
  function bubble(html, mine) {
    const el = document.createElement("div");
    el.className = "bubble" + (mine ? " me" : "");
    el.innerHTML = html;
    revealSpoilers(el);
    $$("a", el).forEach((a) => (a.onclick = (ev) => { ev.preventDefault(); openLink(a.href); }));
    $("#chat").appendChild(el);
    el.scrollIntoView({ behavior: "smooth", block: "end" });
    return el;
  }
  function renderSuggest() {
    $("#suggest").innerHTML = ["q1", "q2", "q3", "q4"].map((k) => `<button>${esc(t(k))}</button>`).join("");
    $$("#suggest button").forEach((b) => (b.onclick = () => { $("#ai-input").value = b.textContent; send(); }));
  }
  function renderAiLeft() {
    $("#ai-left").textContent = me.ai_enabled ? t("ai_left", { n: me.ai_left }) : t("ai_disabled");
  }
  async function loadChat() {
    renderAiLeft();
    if (chatLoaded) return;
    chatLoaded = true;
    $("#chat").innerHTML = "";
    try {
      const h = await api("/api/ai/history");
      if (!h.length) {
        $("#chat").innerHTML = `<div class="glass ai-hello"><div class="orb"></div><div style="font-weight:700">${t("ai_hello_t")}</div><div class="muted small">${t("ai_hello_d")}</div></div>`;
        renderSuggest();
      } else {
        h.forEach((m) => bubble(m.role === "assistant" ? m.html : esc(m.text), m.role === "user"));
        $("#suggest").innerHTML = "";
      }
    } catch (e) { chatLoaded = false; toast(errText(e), "error"); }
  }
  let attached = null; // { mime, b64, name, url }
  function setAttachment(a) {
    attached = a;
    $("#attach-chip").classList.toggle("hidden", !a);
    if (a) $("#attach-name").textContent = (a.mime === "application/pdf" ? "📄 " : "🖼 ") + a.name;
    $("#ai-file").value = "";
  }
  $("#ai-file").onchange = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!["image/jpeg", "image/png", "image/webp", "application/pdf"].includes(f.type)) { toast(t("unsupported"), "error"); return; }
    if (f.size > 10 * 1024 * 1024) { toast(t("file_big"), "error"); return; }
    const reader = new FileReader();
    reader.onload = () => setAttachment({
      mime: f.type, name: f.name, b64: String(reader.result).split(",")[1],
      url: f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
    });
    reader.readAsDataURL(f);
    haptic("light");
  };
  $("#attach-x").onclick = () => setAttachment(null);

  async function send() {
    const input = $("#ai-input");
    const text = input.value.trim();
    if (!text && !attached) return;
    const hello = $(".ai-hello"); if (hello) hello.remove();
    $("#suggest").innerHTML = "";
    input.value = ""; input.style.height = "";
    const att = attached;
    const attHtml = att ? (att.url ? `<img class="att" src="${att.url}" alt="">` : `📄 ${esc(att.name)}<br>`) : "";
    bubble(attHtml + esc(text), true);
    setAttachment(null);
    haptic("light");
    const typing = bubble('<span class="typing"><i></i><i></i><i></i></span>');
    try {
      const body = { message: text };
      if (att) { body.file_b64 = att.b64; body.file_mime = att.mime; }
      const r = await api("/api/ai", { body });
      typing.remove(); bubble(r.html);
      me.ai_left = Math.max(0, me.ai_left - 1); renderAiLeft();
    } catch (e) {
      typing.remove();
      bubble("⚠️ " + esc(t({ limit: "ai_limit", disabled: "ai_disabled", busy: "ai_busy", unsupported: "unsupported" }[e.detail] || "ai_error")));
    }
  }
  $("#ai-send").innerHTML = I.send;
  $("#composer").onsubmit = (e) => { e.preventDefault(); send(); };
  $("#ai-input").addEventListener("input", (e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; });
  $("#ai-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !("ontouchstart" in window)) { e.preventDefault(); send(); } });
  $("#ai-clear").onclick = async () => {
    if (!(await confirmDialog(t("clear_q")))) return;
    await api("/api/ai/history", { method: "DELETE" });
    chatLoaded = false; loadChat();
  };

  // ---------- settings ----------
  async function save(patch) {
    try { me = await api("/api/me", { method: "PATCH", body: patch }); haptic("select"); }
    catch (e) { toast(errText(e), "error"); }
  }
  function renderSettings() {
    $$("#lang-seg button").forEach((b) => b.classList.toggle("active", b.dataset.lang === me.lang));
    $("#paused").checked = me.paused;
    $("#offsets").innerHTML = me.allowed_offsets.map((o) => `
      <div class="item"><div class="icon">${o >= 1440 ? "📅" : o >= 360 ? "⏳" : "🔥"}</div>
        <div class="grow"><div class="title">${offsetLabel(o)} ${t("before")}</div></div>
        <label class="switch"><input type="checkbox" data-off="${o}" ${me.offsets.includes(o) ? "checked" : ""}/><span></span></label></div>`).join("");
    $$("#offsets input").forEach((inp) => (inp.onchange = () => {
      save({ offsets: $$("#offsets input").filter((x) => x.checked).map((x) => +x.dataset.off) });
    }));
    renderMoodleBox();
    renderCourses();
    $("#admin-box").classList.toggle("hidden", !me.is_admin);
    $("#admin-title").hidden = !me.is_admin;
  }
  function renderCourses() {
    $("#courses-block").classList.toggle("hidden", !courses.length);
    $("#courses").innerHTML = courses.map((c) => `
      <div class="item"><div class="icon">🎓</div><div class="grow title ellipsis">${esc(c)}</div>
      <label class="switch"><input type="checkbox" data-course="${esc(c)}" ${(me.muted_courses || []).includes(c) ? "" : "checked"}/><span></span></label></div>`).join("");
    $$("#courses input").forEach((inp) => (inp.onchange = () => {
      save({ muted_courses: $$("#courses input").filter((x) => !x.checked).map((x) => x.dataset.course) });
    }));
  }
  function renderMoodleBox() {
    const box = $("#moodle-box");
    if (!me.linked) {
      box.innerHTML = `<div class="item" id="go-connect"><div class="icon">🔗</div><div class="grow title">${t("connect_title")}</div><span class="chev">›</span></div>`;
      $("#go-connect").onclick = () => show("connect");
      return;
    }
    box.innerHTML = `
      <div class="item"><div class="icon">✅</div><div class="grow"><div class="title">${t("moodle_linked")}</div><div class="meta">${$("#sync-status").textContent}</div></div></div>
      <div class="item" id="pro"><div class="icon">🤖</div><div class="grow"><div class="title">${t("pro_t")}</div><div class="meta">${t("pro_d")}</div></div>
        ${me.account_linked ? `<span class="chip ok">${t("pro_on")}</span>` : '<span class="chev">›</span>'}</div>
      <div class="item" id="relink"><div class="icon">🔄</div><div class="grow title">${t("relink")}</div><span class="chev">›</span></div>
      <div class="item" id="unlink"><div class="icon">⛓️‍💥</div><div class="grow title" style="color:var(--danger)">${t("unlink")}</div></div>`;
    $("#relink").onclick = () => { $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-connect")); };
    $("#unlink").onclick = async () => {
      if (!(await confirmDialog(t("unlink_q")))) return;
      const r = await api("/api/moodle", { method: "DELETE" });
      me = r.user; items = []; courses = []; renderSettings();
    };
    $("#pro").onclick = openPro;
  }
  function openPro() {
    if (me.account_linked) {
      openSheet(`<h2 style="margin-top:0">${t("pro_t")}</h2><p class="muted">${t("pro_d")}</p>
        <button class="btn danger block" id="pro-off">${t("disable")}</button>`, (s) => {
        $("#pro-off", s).onclick = async () => {
          const r = await api("/api/moodle?account_only=true", { method: "DELETE" });
          me = r.user; closeSheet(); renderSettings();
        };
      });
      return;
    }
    openSheet(`<h2 style="margin-top:0">${t("pro_t")}</h2>
      <p class="muted small">${t("pro_sheet")}</p>
      <div class="stack">
        <div class="field"><label>${t("username")}</label><input class="input" id="mu" autocomplete="username" autocapitalize="off"/></div>
        <div class="field"><label>${t("password")}</label><input class="input" id="mp" type="password" autocomplete="current-password"/></div>
        <button class="btn block" id="pro-on">${t("enable")}</button>
      </div>`, (s) => {
      $("#pro-on", s).onclick = async (ev) => {
        ev.target.disabled = true;
        try {
          const r = await api("/api/moodle/account", { body: { username: $("#mu", s).value, password: $("#mp", s).value } });
          me = r.user; closeSheet(); toast(t("saved"), "success"); renderSettings(); loadDeadlines();
        } catch (e) { toast(errText(e), "error"); }
        ev.target.disabled = false;
      };
    });
  }
  $$("#lang-seg button").forEach((b) => (b.onclick = async () => {
    await save({ lang: b.dataset.lang });
    UW.setLang(me.lang); renderAll();
  }));
  $("#paused").onchange = (e) => save({ paused: e.target.checked });
  $("#open-admin").onclick = () => (location.href = "/admin/");

  function renderAll() {
    renderSync(); renderSettings(); renderHero(); renderList(); renderSuggestIfEmpty(); renderAiLeft();
  }
  function renderSuggestIfEmpty() { if ($(".ai-hello")) { $(".ai-hello").remove(); chatLoaded = false; } }

  // ---------- boot ----------
  async function boot() {
    try {
      me = await api("/api/me");
    } catch (e) {
      document.querySelector(".app").innerHTML = `<div class="glass empty" style="margin-top:30vh"><div class="art">🔐</div><div>${esc(errText(e))}</div></div>`;
      $("#dock").classList.add("hidden");
      return;
    }
    UW.setLang(me.lang);
    renderSync(); renderSettings();
    const hash = location.hash.replace("#", "");
    show(["ai", "settings", "connect"].includes(hash) ? hash : "deadlines");
    if (me.linked) loadDeadlines();
    setInterval(() => { if (scope === "upcoming") { renderHero(); renderList(); } }, 30000);
  }
  boot();
})();
