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
    if (page === "support") openSupport(); else stopSupport();
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

  // ---------- chat with admin ----------
  let supItems = [];
  let supTimer = null;
  function supDay(d) {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const x = new Date(d); x.setHours(0, 0, 0, 0);
    const diff = Math.round((today - x) / 864e5);
    return diff === 0 ? t("today") : UW.fmt.day(d);
  }
  function renderSupport(scroll) {
    const box = $("#sup-list");
    if (!supItems.length) {
      box.innerHTML = `<div class="sup-empty"><div class="art">💬</div>${esc(t("sup_empty"))}</div>`;
      return;
    }
    let html = "", lastDay = "";
    supItems.forEach((m) => {
      const at = new Date(m.at);
      const day = supDay(at);
      if (day !== lastDay) { html += `<div class="sup-day">${esc(day)}</div>`; lastDay = day; }
      const mine = !m.from_admin;
      const tick = mine ? `<span class="tick">${m.pending ? "🕓" : m.read ? "✓✓" : "✓"}</span>` : "";
      html += `<div class="bubble ${mine ? "me" : ""}">${esc(m.text)}<span class="meta">${UW.fmt.time(at)}${tick}</span></div>`;
    });
    const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
    box.innerHTML = html;
    if (scroll || atBottom) window.scrollTo({ top: document.body.scrollHeight, behavior: scroll === "smooth" ? "smooth" : "auto" });
  }
  async function loadSupport(scroll) {
    try {
      const r = await api("/api/support");
      const changed = JSON.stringify(r.items) !== JSON.stringify(supItems.filter((m) => !m.pending));
      if (changed) {
        const hadNewAdmin = r.items.length > supItems.length && r.items[r.items.length - 1]?.from_admin;
        supItems = r.items;
        renderSupport(scroll);
        if (hadNewAdmin && !scroll) haptic("success");
      }
      setSupBadge(0);
    } catch (e) { if (scroll) toast(errText(e), "error"); }
  }
  function openSupport() {
    loadSupport(true);
    clearInterval(supTimer);
    supTimer = setInterval(() => loadSupport(false), 4000);
  }
  function stopSupport() { clearInterval(supTimer); supTimer = null; }
  function setSupBadge(n) {
    const b = $("#sup-badge");
    b.textContent = n > 9 ? "9+" : String(n);
    b.classList.toggle("hidden", !n);
  }
  async function sendSupport() {
    const input = $("#sup-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = ""; input.style.height = "";
    const temp = { id: -Date.now(), from_admin: false, text, at: new Date().toISOString(), pending: true };
    supItems.push(temp); renderSupport("smooth"); haptic("light");
    try {
      const m = await api("/api/support", { body: { text } });
      Object.assign(temp, m, { pending: false });
      renderSupport(false);
    } catch (e) {
      supItems = supItems.filter((x) => x !== temp); renderSupport(false);
      input.value = text; toast(t("sup_failed"), "error");
    }
  }
  $("#sup-send").innerHTML = I.send;
  $("#sup-form").onsubmit = (e) => { e.preventDefault(); sendSupport(); };
  $("#sup-input").addEventListener("input", (e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; });
  $("#sup-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !("ontouchstart" in window)) { e.preventDefault(); sendSupport(); } });

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
    renderProfileBox();
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
  // ---------- profile & AI memory ----------
  let prof = null;
  async function loadProfile() {
    try { prof = await api("/api/profile"); renderProfileBox(); } catch (e) { /* settings still work without it */ }
  }
  const yearLabel = (y) => (y === "master" ? t("year_master") : y ? t("year_n", { n: y }) : "");
  function renderProfileBox() {
    const box = $("#profile-box");
    if (!prof) { box.innerHTML = ""; return; }
    const summary = [prof.faculty, yearLabel(prof.year), prof.group_name].filter(Boolean).join(" · ");
    const mem = !prof.memory_on ? t("memory_off") : prof.memory.length ? t("memory_n", { n: prof.memory.length }) : t("memory_zero");
    box.innerHTML = `
      <div class="item" id="open-profile"><div class="icon">👤</div>
        <div class="grow"><div class="title ellipsis">${esc(prof.name || prof.moodle_name || "—")}</div>
        <div class="meta ellipsis">${esc(summary || t("profile_fill"))}</div></div><span class="chev">›</span></div>
      <div class="item" id="open-memory"><div class="icon">🧠</div>
        <div class="grow"><div class="title">${t("memory")}</div><div class="meta">${esc(mem)}</div></div><span class="chev">›</span></div>`;
    $("#open-profile").onclick = openProfile;
    $("#open-memory").onclick = openMemory;
  }
  function openProfile() {
    const years = ["1", "2", "3", "4", "master"];
    openSheet(`<h2 style="margin-top:0">${esc(prof.name || t("profile"))}</h2>
      ${prof.moodle_name ? `<p class="muted small" style="margin-top:-6px">Moodle: ${esc(prof.moodle_name)}</p>` : ""}
      <p class="muted small">${t("profile_hint")}</p>
      <div class="stack">
        <div class="field"><label>${t("faculty")}</label><input class="input" id="pf-faculty" maxlength="160" placeholder="${esc(t("faculty_ph"))}" value="${esc(prof.faculty)}"/></div>
        <div class="field"><label>${t("year")}</label><select class="input" id="pf-year"><option value="">—</option>
          ${years.map((y) => `<option value="${y}" ${prof.year === y ? "selected" : ""}>${esc(yearLabel(y))}</option>`).join("")}</select></div>
        <div class="field"><label>${t("group")}</label><input class="input" id="pf-group" maxlength="64" value="${esc(prof.group_name)}"/></div>
        <div class="field"><label>${t("about")}</label><textarea class="input" id="pf-about" maxlength="600" placeholder="${esc(t("about_ph"))}">${esc(prof.about)}</textarea></div>
        <button class="btn block" id="pf-save">${t("save")}</button>
      </div>`, (s) => {
      $("#pf-save", s).onclick = async (ev) => {
        ev.target.disabled = true;
        try {
          prof = await api("/api/profile", { method: "PATCH", body: {
            faculty: $("#pf-faculty", s).value, year: $("#pf-year", s).value,
            group_name: $("#pf-group", s).value, about: $("#pf-about", s).value } });
          closeSheet(); toast(t("saved"), "success"); renderProfileBox();
        } catch (e) { toast(errText(e), "error"); }
        ev.target.disabled = false;
      };
    });
  }
  function openMemory() {
    const facts = prof.memory.map((f, i) => `
      <div class="item"><div class="grow small">${esc(f)}</div>
        <button class="btn ghost sm" data-forget="${i}" aria-label="✕">✕</button></div>`).join("");
    openSheet(`<h2 style="margin-top:0">🧠 ${t("memory")}</h2>
      <p class="muted small">${t("memory_d")}</p>
      <div class="glass list">
        <div class="item"><div class="grow title">${t("memory_toggle")}</div>
          <label class="switch"><input type="checkbox" id="mem-on" ${prof.memory_on ? "checked" : ""}/><span></span></label></div>
      </div>
      ${prof.memory.length ? `<div class="glass list" style="margin-top:10px">${facts}</div>
        <button class="btn danger block" id="mem-clear" style="margin-top:14px">${t("memory_clear")}</button>`
        : `<p class="center muted small" style="margin-top:16px">${t("memory_zero")}</p>`}`, (s) => {
      $("#mem-on", s).onchange = async (e) => {
        try { prof = await api("/api/profile", { method: "PATCH", body: { memory_on: e.target.checked } }); haptic("select"); renderProfileBox(); }
        catch (err) { toast(errText(err), "error"); }
      };
      $$("[data-forget]", s).forEach((b) => (b.onclick = async () => {
        try { prof = await api(`/api/profile/memory?index=${b.dataset.forget}`, { method: "DELETE" }); renderProfileBox(); openMemory(); }
        catch (err) { toast(errText(err), "error"); }
      }));
      const clear = $("#mem-clear", s);
      if (clear) clear.onclick = async () => {
        if (!(await confirmDialog(t("memory_clear_q")))) return;
        try { prof = await api("/api/profile/memory", { method: "DELETE" }); renderProfileBox(); openMemory(); }
        catch (err) { toast(errText(err), "error"); }
      };
    });
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
    const start = UW.startPage();
    show(["ai", "settings", "connect", "support", "deadlines"].includes(start) ? start : "deadlines");
    setSupBadge(me.support_unread || 0);
    loadProfile();
    if (me.linked) loadDeadlines();
    setInterval(() => { if (scope === "upcoming") { renderHero(); renderList(); } }, 30000);
  }
  boot();
})();
