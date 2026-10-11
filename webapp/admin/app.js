(function () {
  const { api, t, $, $$, esc, toast, haptic, openSheet, closeSheet, confirmDialog, revealSpoilers, I } = UW;
  let me = null;
  const loaded = {};

  const fmtDate = (s) => UW.fmt.dateTime(new Date(s));
  function errText(e) {
    if (e.status === 403) return t("forbidden");
    const k = "err_" + e.detail;
    return t(k) !== k ? t(k) : e.detail || t("err_generic");
  }
  function offsetLabel(o) {
    if (o % 1440 === 0) return `${o / 1440} ${t("days")}`;
    if (o >= 60) return `${o / 60} ${t("hours")}`;
    return `${o} ${t("mins")}`;
  }

  // ---------- nav ----------
  const loaders = { dash: loadDash, users: () => loadUsers(true), bc: loadBc, chat: loadInbox, ai: loadKb, set: loadSettings };
  function show(page) {
    $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + page));
    $$("#dock button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    if (page === "chat") { loadInbox(); startChatPoll(); } else stopChatPoll();
    if (!loaded[page]) { loaded[page] = true; if (page !== "chat") loaders[page](); }
    window.scrollTo({ top: 0 });
  }
  $$("#dock button").forEach((b) => (b.onclick = () => { haptic("select"); show(b.dataset.page); }));
  $$("[data-icon]").forEach((el) => (el.innerHTML = I[el.dataset.icon]));

  // ---------- dashboard ----------
  async function loadDash() {
    try {
      const s = await api("/api/admin/stats");
      const k = [
        ["k_users", s.users, "navy"], ["k_linked", s.linked, "crimson"],
        ["k_active", s.active_week, "navy"], ["k_new", s.new_day, "crimson"],
        ["k_upcoming", s.upcoming_deadlines, "navy"], ["k_rem", s.reminders_day, "crimson"],
        ["k_ai", s.ai_questions_day, "navy"], ["k_blocked", s.blocked, "crimson"],
        ["k_support", s.support_unread, "crimson"],
      ];
      setChatBadge(s.support_unread);
      $("#kpis").innerHTML = k.map(([l, v, c]) => `<div class="glass kpi ${c}"><div class="v">${v}</div><div class="l">${t(l)}</div></div>`).join("");
      const max = Math.max(1, ...s.growth.map((g) => g.n));
      $("#growth").innerHTML = s.growth.map((g, i) =>
        `<div style="height:${(g.n / max) * 100}%">${g.n ? `<b>${g.n}</b>` : ""}${i % 3 === 0 ? `<span>${g.day}</span>` : ""}</div>`).join("");
      const total = Object.values(s.langs).reduce((a, b) => a + b, 0) || 1;
      $("#langs").innerHTML = ["uz", "ru", "en"].map((l) => {
        const n = s.langs[l] || 0;
        return `<div class="lang-row"><b style="width:28px">${l.toUpperCase()}</b><div class="track"><i style="width:${(n / total) * 100}%"></i></div><span class="muted">${n}</span></div>`;
      }).join("");
    } catch (e) { toast(errText(e), "error"); }
  }
  $("#dash-refresh").onclick = () => { haptic("light"); loadDash(); };

  // ---------- users ----------
  let uOffset = 0, uFilter = "all", uTimer;
  async function loadUsers(reset) {
    if (reset) { uOffset = 0; $("#user-list").innerHTML = '<div class="skeleton" style="margin:10px"></div>'; }
    try {
      const q = encodeURIComponent($("#user-q").value.trim());
      const r = await api(`/api/admin/users?q=${q}&filter=${uFilter}&offset=${uOffset}&limit=30`);
      $("#users-total").textContent = t("total", { n: r.total });
      const html = r.items.map((u) => `
        <div class="item" data-id="${u.id}">
          <div class="avatar">${esc((u.first_name || "?")[0].toUpperCase())}</div>
          <div class="grow">
            <div class="title ellipsis">${esc(u.first_name || "—")} ${u.username ? `<span class="muted small">@${esc(u.username)}</span>` : ""}</div>
            <div class="badges">
              <span class="chip">${u.lang.toUpperCase()}</span>
              ${u.linked ? `<span class="chip ok">${t("linked")}</span>` : ""}
              ${u.is_admin ? `<span class="chip warn">${t("admin")}</span>` : ""}
              ${u.is_banned ? `<span class="chip danger">${t("banned")}</span>` : ""}
              ${u.blocked_bot ? `<span class="chip">${t("left_bot")}</span>` : ""}
            </div>
          </div><span class="chev">›</span></div>`).join("");
      if (reset) $("#user-list").innerHTML = html || `<div class="empty muted">—</div>`;
      else $("#user-list").insertAdjacentHTML("beforeend", html);
      uOffset += r.items.length;
      $("#more-users").classList.toggle("hidden", uOffset >= r.total);
      $$("#user-list .item").forEach((el) => (el.onclick = () => openUser(+el.dataset.id)));
    } catch (e) { toast(errText(e), "error"); }
  }
  $("#user-q").oninput = () => { clearTimeout(uTimer); uTimer = setTimeout(() => loadUsers(true), 300); };
  $("#more-users").onclick = () => loadUsers(false);
  $$("#user-filter button").forEach((b) => (b.onclick = () => {
    $$("#user-filter button").forEach((x) => x.classList.toggle("active", x === b));
    uFilter = b.dataset.f; haptic("select"); loadUsers(true);
  }));

  async function openUser(id) {
    let u;
    try { u = await api("/api/admin/users/" + id); } catch (e) { toast(errText(e), "error"); return; }
    openSheet(`
      <div class="row"><div class="avatar" style="width:52px;height:52px;font-size:20px">${esc((u.first_name || "?")[0].toUpperCase())}</div>
        <div class="grow"><h2 style="margin:0">${esc(u.first_name || "—")}</h2>
        <div class="muted small">${u.username ? "@" + esc(u.username) + " · " : ""}ID ${u.id}</div></div></div>
      <div class="glass list" style="margin-top:14px">
        <div class="item"><div class="grow muted small">${t("joined")}</div><div class="small">${fmtDate(u.created_at)}</div></div>
        <div class="item"><div class="grow muted small">${t("seen")}</div><div class="small">${fmtDate(u.last_seen_at)}</div></div>
        <div class="item"><div class="grow muted small">Moodle</div><div class="small">${u.linked ? "✅" : "—"} ${u.account_linked ? "🤖" : ""}</div></div>
      </div>
      <div class="section-title">${t("deadlines")}</div>
      <div class="glass list">${u.deadlines.length ? u.deadlines.map((d) =>
        `<div class="item"><div class="grow"><div class="title small">${d.completed ? "✅ " : ""}${esc(d.title)}</div><div class="meta">${esc(d.course)}</div></div><div class="small muted">${fmtDate(d.due_at)}</div></div>`).join("") : `<div class="item muted">${t("none")}</div>`}</div>
      <div class="stack" style="margin-top:16px">
        <button class="btn block" id="u-msg">✉️ ${t("write_msg")}</button>
        <div class="row">
          <button class="btn ghost grow" id="u-admin">${t(u.is_admin ? "remove_admin" : "make_admin")}</button>
          <button class="btn ${u.is_banned ? "ghost" : "danger"} grow" id="u-ban">${t(u.is_banned ? "unban" : "ban")}</button>
        </div>
      </div>`, (s) => {
      const patch = async (body) => {
        try { await api("/api/admin/users/" + id, { method: "PATCH", body }); toast(t("saved"), "success"); closeSheet(); loadUsers(true); }
        catch (e) { toast(errText(e), "error"); }
      };
      $("#u-admin", s).onclick = () => patch({ is_admin: !u.is_admin });
      $("#u-ban", s).onclick = () => patch({ is_banned: !u.is_banned });
      $("#u-msg", s).onclick = () => directMessage(u);
    });
  }

  function directMessage(u) {
    openSheet(`<h2 style="margin-top:0">✉️ ${esc(u.first_name || "")}</h2>
      <div class="glass editor-card"><div class="toolbar" id="dm-toolbar"></div>
      <div class="editor" id="dm-editor" contenteditable="true" data-ph="${esc(t("editor_ph"))}"></div></div>
      <button class="btn block" id="dm-send" style="margin-top:12px">${t("send_all")}</button>`, (s) => {
      $("#dm-toolbar", s).innerHTML = $("#toolbar").innerHTML;
      bindToolbar($("#dm-toolbar", s), $("#dm-editor", s));
      $("#dm-send", s).onclick = async () => {
        try {
          await api(`/api/admin/users/${u.id}/message`, { body: { html: $("#dm-editor", s).innerHTML } });
          toast("✅", "success"); closeSheet();
        } catch (e) { toast(errText(e), "error"); }
      };
    });
  }

  // ---------- rich text editor ----------
  const EMOJI = "📢 🎓 📚 📝 ⏰ ✅ ❗ ⚠️ 🔥 🎉 💡 📌 📅 🏛 🌐 👉 ❤️ 🙏".split(" ");
  function wrapSelection(editor, tag, cls) {
    const sel = window.getSelection();
    if (!sel.rangeCount || !editor.contains(sel.anchorNode)) return;
    const range = sel.getRangeAt(0);
    if (range.collapsed) return;
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    el.appendChild(range.extractContents());
    range.insertNode(el);
    sel.removeAllRanges();
    const r = document.createRange(); r.selectNodeContents(el); sel.addRange(r);
  }
  function bindToolbar(toolbar, editor) {
    editor.dataset.ph = t("editor_ph");
    $$("button", toolbar).forEach((b) => {
      b.onmousedown = (e) => e.preventDefault(); // keep selection
      b.onclick = () => {
        editor.focus();
        const c = b.dataset.cmd;
        haptic("select");
        if (c === "link") {
          const url = prompt(t("link_q"), "https://");
          if (url && /^(https?:\/\/|tg:\/\/)/.test(url)) document.execCommand("createLink", false, url);
        } else if (c === "code") wrapSelection(editor, "code");
        else if (c === "spoiler") wrapSelection(editor, "span", "tg-spoiler");
        else if (c === "quote") wrapSelection(editor, "blockquote");
        else if (c === "emoji") {
          openSheet(`<div class="chips">${EMOJI.map((e) => `<button class="pill" style="font-size:22px">${e}</button>`).join("")}</div>`, (s) => {
            $$("button", s).forEach((x) => (x.onclick = () => { closeSheet(); editor.focus(); document.execCommand("insertText", false, x.textContent); editor.dispatchEvent(new Event("input")); }));
          });
          return;
        } else document.execCommand(c, false, null);
        editor.dispatchEvent(new Event("input"));
      };
    });
    // paste as plain text to avoid foreign styles
    editor.addEventListener("paste", (e) => {
      e.preventDefault();
      document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain"));
    });
  }

  // ---------- broadcast ----------
  let pvTimer;
  const segment = () => {
    const v = $("#seg-linked .active").dataset.v;
    return { langs: $$("#seg-langs .pill.active").map((p) => p.dataset.l), linked: v === "all" ? null : v === "true" };
  };
  const payload = () => ({
    html: $("#editor").innerHTML,
    button_text: $("#btn-text").value.trim() || null,
    button_url: $("#btn-url").value.trim() || null,
    segment: segment(),
  });
  async function refreshPreview() {
    const p = payload();
    try {
      const r = await api("/api/admin/broadcast/preview", { body: p });
      $("#preview").innerHTML = r.html || `<span class="muted">${t("preview_empty")}</span>`;
      revealSpoilers($("#preview"));
      const cc = $("#char-count");
      cc.textContent = `${r.length} / 4096`;
      cc.classList.toggle("over", r.length > 4096);
    } catch (e) {}
    $("#preview-btn").innerHTML = p.button_text && p.button_url ? `<div class="preview-btn">${esc(p.button_text)} ↗</div>` : "";
  }
  async function refreshCount() {
    try { const r = await api("/api/admin/broadcast/count", { body: segment() }); $("#seg-count").textContent = t("recipients", { n: r.count }); return r.count; }
    catch (e) { return 0; }
  }
  async function loadBc() {
    refreshCount(); loadBcHistory();
  }
  async function loadBcHistory() {
    try {
      const rows = await api("/api/admin/broadcasts");
      $("#bc-history").innerHTML = rows.map((b) => `
        <div class="glass bc-item"><div class="row"><div class="grow small muted">${fmtDate(b.created_at)}</div>
          <span class="chip ${b.status === "done" ? "ok" : "warn"}">${t("st_" + b.status)} · ${b.sent}/${b.total}${b.failed ? ` · ❌${b.failed}` : ""}</span></div>
          <div class="snippet">${b.html}</div>
          ${b.status !== "done" ? `<div class="progress"><i style="width:${b.total ? (b.sent + b.failed) / b.total * 100 : 0}%"></i></div>` : ""}</div>`).join("");
      if (rows.some((b) => b.status !== "done")) setTimeout(loadBcHistory, 3000);
    } catch (e) {}
  }
  bindToolbar($("#toolbar"), $("#editor"));
  ["#editor", "#btn-text", "#btn-url"].forEach((s) => $(s).addEventListener("input", () => { clearTimeout(pvTimer); pvTimer = setTimeout(refreshPreview, 350); }));
  $$("#seg-langs .pill").forEach((p) => (p.onclick = () => { p.classList.toggle("active"); haptic("select"); refreshCount(); }));
  $$("#seg-linked button").forEach((b) => (b.onclick = () => {
    $$("#seg-linked button").forEach((x) => x.classList.toggle("active", x === b)); haptic("select"); refreshCount();
  }));
  $("#bc-test").onclick = async () => {
    try { await api("/api/admin/broadcast/test", { body: payload() }); toast(t("sent_test"), "success"); }
    catch (e) { toast(errText(e), "error"); }
  };
  $("#bc-send").onclick = async () => {
    const n = await refreshCount();
    if (!(await confirmDialog(t("confirm_send", { n })))) return;
    try {
      await api("/api/admin/broadcast", { body: payload() });
      toast(t("started"), "success");
      $("#editor").innerHTML = ""; refreshPreview(); loadBcHistory();
    } catch (e) { toast(errText(e), "error"); }
  };

  // ---------- student chats ----------
  let openUid = null, threadItems = [], chatTimer = null;
  function setChatBadge(n) {
    const b = $("#chat-badge");
    b.textContent = n > 9 ? "9+" : String(n || 0);
    b.classList.toggle("hidden", !n);
  }
  const initial = (n) => esc(((n || "?").trim()[0] || "?").toUpperCase());
  async function loadInbox() {
    if (openUid) return loadThread(false);
    try {
      const r = await api("/api/admin/support");
      setChatBadge(r.unread);
      $("#inbox-sub").textContent = t("chats_sub", { n: r.unread });
      $("#inbox-list").innerHTML = r.items.length ? r.items.map((c) => `
        <div class="item" data-uid="${c.user_id}">
          <div class="avatar">${initial(c.first_name)}</div>
          <div class="grow" style="min-width:0">
            <div class="row"><div class="grow title ellipsis">${esc(c.first_name || "—")} ${c.username ? `<span class="muted small">@${esc(c.username)}</span>` : ""}</div>
              <span class="muted small">${UW.fmt.time(new Date(c.last_at))}</span></div>
            <div class="row"><div class="grow meta ellipsis">${c.last_from_admin ? t("you") + ": " : ""}${esc(c.last_text)}</div>
              ${c.unread ? `<span class="unread-pill">${c.unread}</span>` : ""}</div>
          </div></div>`).join("") : `<div class="empty muted">💬 ${t("chats_empty")}</div>`;
      $$("#inbox-list .item").forEach((el) => (el.onclick = () => openThread(+el.dataset.uid)));
    } catch (e) { toast(errText(e), "error"); }
  }
  function renderThread(scroll) {
    let html = "", lastDay = "";
    threadItems.forEach((m) => {
      const at = new Date(m.at);
      const day = UW.fmt.day(at);
      if (day !== lastDay) { html += `<div class="sup-day">${esc(day)}</div>`; lastDay = day; }
      const mine = m.from_admin;
      const tick = mine ? ` ${m.pending ? "🕓" : m.read ? "✓✓" : "✓"}` : "";
      html += `<div class="bubble ${mine ? "me" : ""}">${esc(m.text)}<span class="meta">${UW.fmt.time(at)}${tick}</span></div>`;
    });
    const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
    $("#thread-list").innerHTML = html;
    if (scroll || atBottom) window.scrollTo({ top: document.body.scrollHeight });
  }
  async function loadThread(scroll) {
    try {
      const r = await api("/api/admin/support/" + openUid);
      const u = r.user;
      $("#thread-avatar").textContent = ((u.first_name || "?")[0] || "?").toUpperCase();
      $("#thread-name").textContent = u.first_name || "—";
      $("#thread-meta").textContent = [u.username ? "@" + u.username : null, "ID " + u.id, u.lang.toUpperCase()].filter(Boolean).join(" · ");
      if (JSON.stringify(r.items) !== JSON.stringify(threadItems.filter((m) => !m.pending))) {
        threadItems = r.items; renderThread(scroll);
      }
    } catch (e) { toast(errText(e), "error"); }
  }
  function openThread(uid) {
    openUid = uid; threadItems = [];
    $("#inbox").classList.add("hidden"); $("#thread").classList.remove("hidden");
    $("#thread-list").innerHTML = '<div class="skeleton"></div>';
    loadThread(true);
    if (UW.tg && UW.tg.BackButton) { UW.tg.BackButton.show(); UW.tg.BackButton.onClick(closeThread); }
  }
  function closeThread() {
    openUid = null;
    $("#thread").classList.add("hidden"); $("#inbox").classList.remove("hidden");
    if (UW.tg && UW.tg.BackButton) { UW.tg.BackButton.offClick(closeThread); UW.tg.BackButton.hide(); }
    loadInbox();
  }
  function startChatPoll() { clearInterval(chatTimer); chatTimer = setInterval(loadInbox, 4000); }
  function stopChatPoll() { clearInterval(chatTimer); chatTimer = null; }
  $("#thread-back").onclick = closeThread;
  $("#thread-send").innerHTML = I.send;
  async function sendReply() {
    const input = $("#thread-input");
    const text = input.value.trim();
    if (!text || !openUid) return;
    input.value = ""; input.style.height = "";
    const temp = { id: -Date.now(), from_admin: true, text, at: new Date().toISOString(), pending: true };
    threadItems.push(temp); renderThread(true); haptic("light");
    try {
      Object.assign(temp, await api("/api/admin/support/" + openUid, { body: { text } }), { pending: false });
      renderThread(false);
    } catch (e) {
      threadItems = threadItems.filter((x) => x !== temp); renderThread(false);
      input.value = text; toast(errText(e), "error");
    }
  }
  $("#thread-form").onsubmit = (e) => { e.preventDefault(); sendReply(); };
  $("#thread-input").addEventListener("input", (e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; });
  $("#thread-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !("ontouchstart" in window)) { e.preventDefault(); sendReply(); } });

  // ---------- knowledge base ----------
  let docs = [];
  async function loadKb() {
    try {
      docs = await api("/api/admin/kb");
      const stats = await api("/api/admin/stats");
      $("#kb-sub").textContent = t("kb_count", { d: docs.length, c: stats.kb.chunks });
      $("#kb-list").innerHTML = docs.map((d) => `
        <div class="glass kb-item" data-id="${d.id}"><div class="row"><div class="grow title" style="font-weight:700">${esc(d.title)}</div>
          ${d.enabled ? "" : `<span class="chip">${t("off")}</span>`}<span class="muted small">${t("chars", { n: d.chars })}</span></div>
          <div class="snippet">${esc(d.content.slice(0, 220))}</div></div>`).join("");
      $$("#kb-list .kb-item").forEach((el) => (el.onclick = () => editDoc(docs.find((d) => d.id == el.dataset.id))));
    } catch (e) { toast(errText(e), "error"); }
  }
  function editDoc(d) {
    d = d || { title: "", content: "", enabled: true };
    openSheet(`<div class="stack">
        <div class="field"><label>${t("doc_title")}</label><input class="input" id="d-title" maxlength="255" value="${esc(d.title)}"/></div>
        <div class="field"><label>${t("doc_content")}</label><textarea class="input" id="d-content" rows="12">${esc(d.content)}</textarea></div>
        <div class="row"><div class="grow">${t("enabled")}</div><label class="switch"><input type="checkbox" id="d-en" ${d.enabled ? "checked" : ""}/><span></span></label></div>
        <button class="btn block" id="d-save">${t("save")}</button>
        ${d.id ? `<button class="btn ghost block" id="d-del" style="color:var(--danger)">${t("delete")}</button>` : ""}
      </div>`, (s) => {
      $("#d-save", s).onclick = async () => {
        const body = { title: $("#d-title", s).value.trim(), content: $("#d-content", s).value.trim(), enabled: $("#d-en", s).checked };
        try {
          await api(d.id ? `/api/admin/kb/${d.id}` : "/api/admin/kb", { method: d.id ? "PUT" : "POST", body });
          toast(t("saved"), "success"); closeSheet(); loadKb();
        } catch (e) { toast(errText(e), "error"); }
      };
      const del = $("#d-del", s);
      if (del) del.onclick = async () => {
        if (!(await confirmDialog(t("delete_q")))) return;
        await api(`/api/admin/kb/${d.id}`, { method: "DELETE" }); closeSheet(); loadKb();
      };
    });
  }
  $("#kb-add").onclick = () => editDoc(null);
  $("#ai-ask").onclick = async () => {
    const q = $("#ai-q").value.trim();
    if (!q) return;
    $("#ai-out").innerHTML = '<div class="skeleton" style="height:60px"></div>';
    try {
      const r = await api("/api/admin/ai/test", { body: { message: q } });
      $("#ai-out").innerHTML = `<div class="bubble">${r.html}</div>` +
        (r.sources.length ? `<div class="sources"><b>${t("sources")}:</b> ${r.sources.map((s) => esc(s.title)).join(" · ")}</div>` : "");
    } catch (e) { $("#ai-out").innerHTML = `<div class="muted">⚠️ ${esc(errText(e))}</div>`; }
  };

  // ---------- settings ----------
  let st = null;
  const ALLOWED = [4320, 2880, 1440, 720, 360, 180, 120, 60, 30];
  async function loadSettings() {
    try {
      st = await api("/api/admin/settings");
      $("#s-maint").checked = st.maintenance;
      $("#s-ai").checked = st.ai_enabled;
      $("#s-tts").checked = st.tts_enabled;
      $("#s-limit").value = st.ai_daily_limit;
      $("#s-prompt").value = st.ai_system_prompt;
      $("#s-offsets").innerHTML = (st.allowed_offsets || ALLOWED).map((o) =>
        `<button class="pill ${st.default_offsets.includes(o) ? "active" : ""}" data-o="${o}">${offsetLabel(o)}</button>`).join("");
      $$("#s-offsets .pill").forEach((p) => (p.onclick = () => { p.classList.toggle("active"); haptic("select"); }));
    } catch (e) { toast(errText(e), "error"); }
  }
  $("#s-save").onclick = async () => {
    try {
      st = await api("/api/admin/settings", {
        method: "PUT",
        body: {
          maintenance: $("#s-maint").checked, ai_enabled: $("#s-ai").checked, tts_enabled: $("#s-tts").checked,
          ai_daily_limit: +$("#s-limit").value, ai_system_prompt: $("#s-prompt").value,
          default_offsets: $$("#s-offsets .pill.active").map((p) => +p.dataset.o),
        },
      });
      toast(t("saved"), "success");
    } catch (e) { toast(errText(e), "error"); }
  };
  $("#to-student").onclick = () => (location.href = "/app/");

  // ---------- boot ----------
  (async function boot() {
    try {
      me = await api("/api/me");
      if (!me.is_admin) throw new UW.ApiError(403, "forbidden");
    } catch (e) {
      document.querySelector(".app").innerHTML = `<div class="glass empty" style="margin-top:30vh"><div class="art">🔐</div><div>${esc(t(e.status === 403 ? "forbidden" : "err_generic"))}</div></div>`;
      $("#dock").classList.add("hidden");
      return;
    }
    UW.setLang(me.lang);
    $("#editor").dataset.ph = t("editor_ph");
    const m = UW.startPage().match(/^chat-(\d+)$/);
    if (m) { show("chat"); openThread(+m[1]); } else show("dash");
  })();
})();
