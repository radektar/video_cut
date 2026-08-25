/* KADR Review UI — vanilla JS, bez bundlera (spec sekcja 10).
   Stan = edl.json na serwerze; UI czyta/pisze JSON i odtwarza proxy. */

const $ = (id) => document.getElementById(id);

const state = {
  data: null,          // /api/state
  selected: null,      // id wybranego zakresu
  dirty: false,
  saveTimer: null,
  pendingEdl: null,    // edl czekający po 409
  player: { playing: false, idx: -1, events: [] },
  compareVersion: null,
};

/* ---------- helpery danych ---------- */

const edl = () => state.data.edl;
const prefs = () => state.data.preferences;
const rangeById = (id) => edl().ranges.find((r) => r.id === id);
const stemOf = (file) => file.replace(/\.[^.]+$/, "");
const sourceStem = (r) => stemOf(edl().sources[r.source]);
const transcriptFor = (r) => state.data.transcripts_index[sourceStem(r)] || null;
const primaryFormat = () => (prefs().output.formats[0] || "9x16");
const trashRanges = () => edl().ranges.filter((r) => !edl().order.includes(r.id));
const dur = (r) => r.end - r.start;

function fmtTime(t) {
  const m = Math.floor(t / 60);
  const s = (t % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

function wordsInRange(r) {
  const t = transcriptFor(r);
  if (!t) return [];
  return t.words.filter((w) => w.start >= r.start - 0.02 && w.end <= r.end + 0.02);
}

function chunkEvents(r) {
  // przybliżenie napisów jak w renderze: chunk_words słów na linię, czasy źródłowe
  const n = prefs().subtitles.chunk_words || 3;
  const upper = prefs().subtitles.case === "upper";
  const words = wordsInRange(r);
  const events = [];
  for (let i = 0; i < words.length; i += n) {
    const chunk = words.slice(i, i + n);
    let text = chunk.map((w) => w.text).join(" ");
    if (upper) text = text.toUpperCase();
    events.push({ start: chunk[0].start, end: chunk[chunk.length - 1].end, text });
  }
  return events;
}

/* ---------- API ---------- */

async function fetchState() {
  const res = await fetch("/api/state");
  state.data = await res.json();
  renderAll();
}

function markDirty() {
  state.dirty = true;
  setSaveIndicator("niezapisane", "save-dirty");
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveEdl, 500); // autosave, debounce 500 ms
  renderAll();
}

async function saveEdl(force = false) {
  const body = state.pendingEdl && force ? state.pendingEdl : edl();
  setSaveIndicator("zapisywanie…", "save-dirty");
  const res = await fetch(`/api/edl${force ? "?force=true" : ""}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 409) {
    state.pendingEdl = body;
    setSaveIndicator("konflikt", "save-conflict");
    $("conflictDialog").showModal();
    return;
  }
  if (!res.ok) {
    const err = await res.json();
    setSaveIndicator("błąd walidacji", "save-conflict");
    console.error("PUT /api/edl:", err);
    alert("EDL odrzucony przez walidację:\n" + (err.detail || res.status));
    return;
  }
  const saved = await res.json();
  state.data.edl = saved;
  state.dirty = false;
  state.pendingEdl = null;
  setSaveIndicator("zapisano", "save-ok");
}

function setSaveIndicator(text, cls) {
  const el = $("saveIndicator");
  el.textContent = text;
  el.className = cls;
}

let prefsTimer = null;
function savePrefsDebounced() {
  clearTimeout(prefsTimer);
  prefsTimer = setTimeout(async () => {
    const res = await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prefs()),
    });
    if (res.ok) state.data.preferences = await res.json();
    renderAll();
  }, 500);
}

/* ---------- lista segmentów ---------- */

function frameUrl(r, t, height = 120) {
  return `/api/frame?source=${encodeURIComponent(sourceStem(r))}&t=${t.toFixed(3)}&height=${height}`;
}

function renderSegments() {
  const list = $("segmentsList");
  list.innerHTML = "";
  edl().order.forEach((id, idx) => {
    const r = rangeById(id);
    const card = document.createElement("div");
    card.className = "seg-card" + (state.selected === id ? " selected" : "");
    card.draggable = !r.locked;
    card.dataset.id = id;
    const mid = r.start + dur(r) / 2;
    card.innerHTML = `
      <img loading="lazy" src="${frameUrl(r, mid)}" alt="">
      <div>
        <div class="quote">${escapeHtml(r.quote || "(bez transkryptu)")}</div>
        <div class="seg-meta">
          <span class="badge">${escapeHtml(r.source)}</span>
          <span>${fmtTime(dur(r))}</span>
          ${r.beat ? `<span class="badge">${escapeHtml(r.beat)}</span>` : ""}
          <span class="seg-icons">
            <button data-act="subtitles" class="${r.subtitles ? "on" : ""}" title="napisy">💬</button>
            <button data-act="mute" class="${r.mute ? "on" : ""}" title="mute">🔇</button>
            <button data-act="locked" class="${r.locked ? "on" : ""}" title="kłódka — agent nie zmienia">🔒</button>
            <button data-act="trash" title="usuń z montażu (do kosza)">🗑</button>
          </span>
        </div>
      </div>`;
    card.addEventListener("click", (e) => {
      const act = e.target.dataset?.act;
      if (act) { e.stopPropagation(); toggleFlag(id, act); return; }
      selectSegment(id);
    });
    // drag & drop zmienia order
    card.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", id));
    card.addEventListener("dragover", (e) => { e.preventDefault(); card.classList.add("dragover"); });
    card.addEventListener("dragleave", () => card.classList.remove("dragover"));
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("dragover");
      const dragged = e.dataTransfer.getData("text/plain");
      if (!dragged || dragged === id) return;
      const order = edl().order.filter((x) => x !== dragged);
      order.splice(order.indexOf(id), 0, dragged);
      edl().order = order;
      markDirty();
    });
    list.appendChild(card);
  });

  const trash = $("trashList");
  trash.innerHTML = "";
  trashRanges().forEach((r) => {
    const el = document.createElement("div");
    el.className = "trash-card";
    el.innerHTML = `<span class="badge">${escapeHtml(r.source)}</span>
      <span>${escapeHtml((r.quote || r.id).slice(0, 60))}</span>
      <span class="spacer"></span>
      <button>przywróć</button>`;
    el.querySelector("button").addEventListener("click", () => {
      edl().order.push(r.id);
      markDirty();
    });
    trash.appendChild(el);
  });
}

function toggleFlag(id, act) {
  const r = rangeById(id);
  if (act === "trash") {
    edl().order = edl().order.filter((x) => x !== id);
    if (state.selected === id) state.selected = null;
  } else {
    r[act] = !r[act];
  }
  markDirty();
}

function selectSegment(id) {
  state.selected = id;
  stopSequence();
  const r = rangeById(id);
  const video = $("preview");
  video.src = `/media/proxy/${encodeURIComponent(sourceStem(r))}.mp4`;
  video.currentTime = r.start;
  renderAll();
}

/* ---------- trymowanie ---------- */

function wordContext(r, boundary, t) {
  const words = transcriptFor(r)?.words || [];
  const before = words.filter((w) => w.end <= t + 0.001).slice(-3);
  const after = words.filter((w) => w.start >= t - 0.001).slice(0, 3);
  const b = before.map((w) => w.text).join(" ");
  const a = after.map((w) => w.text).join(" ");
  return boundary === "start" ? `${escapeHtml(b)} | <b>${escapeHtml(a)}</b>` : `<b>${escapeHtml(b)}</b> | ${escapeHtml(a)}`;
}

function snapToWord(r, boundary) {
  const words = transcriptFor(r)?.words || [];
  if (!words.length) return;
  const pad = 0.05; // padding 30-200 ms — najprostsza interpretacja: 50 ms
  if (boundary === "start") {
    const t = r.start;
    const nearest = words.reduce((a, w) => (Math.abs(w.start - t) < Math.abs(a.start - t) ? w : a));
    r.start = Math.max(0, +(nearest.start - pad).toFixed(3));
  } else {
    const t = r.end;
    const nearest = words.reduce((a, w) => (Math.abs(w.end - t) < Math.abs(a.end - t) ? w : a));
    r.end = +(nearest.end + pad).toFixed(3);
  }
  if (r.start >= r.end) r.start = Math.max(0, r.end - 0.2);
  markDirty();
}

function nudge(r, boundary, delta) {
  const media = state.data.media.sources[sourceStem(r)];
  const max = media ? media.duration : Infinity;
  if (boundary === "start") r.start = Math.min(Math.max(0, +(r.start + delta).toFixed(3)), r.end - 0.05);
  else r.end = Math.max(Math.min(max, +(r.end + delta).toFixed(3)), r.start + 0.05);
  markDirty();
}

function renderBoundary(el, r, boundary) {
  const t = boundary === "start" ? r.start : Math.max(0, r.end - 0.04);
  el.innerHTML = `
    <div><b>${boundary === "start" ? "Początek" : "Koniec"}</b></div>
    <img src="${frameUrl(r, t, 200)}" alt="">
    <div class="words">${wordContext(r, boundary, boundary === "start" ? r.start : r.end)}</div>
    <div class="btns">
      <button data-d="-0.5">−0,5</button><button data-d="-0.1">−0,1</button>
      <button data-d="0.1">+0,1</button><button data-d="0.5">+0,5</button>
      <button data-snap="1">do granicy słowa</button>
      <span class="tval">${(boundary === "start" ? r.start : r.end).toFixed(2)} s</span>
    </div>`;
  el.querySelectorAll("button[data-d]").forEach((b) =>
    b.addEventListener("click", () => nudge(r, boundary, parseFloat(b.dataset.d))));
  el.querySelector("button[data-snap]").addEventListener("click", () => snapToWord(r, boundary));
}

function renderTrimPanel() {
  const panel = $("trimPanel");
  if (!state.selected || !rangeById(state.selected)) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  const r = rangeById(state.selected);
  $("trimId").textContent = `${r.id} (${r.source})`;
  renderBoundary($("boundaryStart"), r, "start");
  renderBoundary($("boundaryEnd"), r, "end");

  const hasCrop = primaryFormat() !== "16x9";
  $("cropTools").classList.toggle("hidden", !hasCrop);
  if (hasCrop) {
    $("cropVal").textContent = `crop_x = ${(r.crop_x ?? 0.5).toFixed(2)}`;
    $("btnCropAll").onclick = () => {
      edl().ranges.filter((x) => x.source === r.source).forEach((x) => { x.crop_x = r.crop_x ?? 0.5; });
      markDirty();
    };
  }
}

/* ---------- ramka kadru na podglądzie ---------- */

function renderCropFrame() {
  const frame = $("cropFrame");
  const r = state.selected && rangeById(state.selected);
  const fmt = primaryFormat();
  if (!r || fmt === "16x9" || state.player.playing) { frame.classList.add("hidden"); return; }
  frame.classList.remove("hidden");
  const wrap = $("videoWrap");
  const H = wrap.clientHeight, W = wrap.clientWidth;
  const ratio = fmt === "9x16" ? 9 / 16 : 1; // szerokość kadru względem wysokości
  const fw = H * ratio;
  frame.style.width = `${fw}px`;
  frame.style.left = `${(W - fw) * (r.crop_x ?? 0.5)}px`;

  frame.onpointerdown = (e) => {
    e.preventDefault();
    frame.setPointerCapture(e.pointerId);
    const startX = e.clientX, startLeft = parseFloat(frame.style.left);
    frame.onpointermove = (ev) => {
      let left = Math.min(Math.max(0, startLeft + ev.clientX - startX), W - fw);
      frame.style.left = `${left}px`;
      r.crop_x = +(W - fw > 0 ? left / (W - fw) : 0.5).toFixed(3);
      $("cropVal").textContent = `crop_x = ${r.crop_x.toFixed(2)}`;
    };
    frame.onpointerup = () => {
      frame.onpointermove = frame.onpointerup = null;
      markDirty();
    };
  };
}

/* ---------- podgląd wirtualny ---------- */

function playSequence() {
  const order = edl().order;
  if (!order.length) return;
  state.player.playing = true;
  state.player.idx = -1;
  nextSegment();
}

function nextSegment() {
  const p = state.player;
  p.idx += 1;
  if (p.idx >= edl().order.length) { stopSequence(); return; }
  const r = rangeById(edl().order[p.idx]);
  p.events = r.subtitles ? chunkEvents(r) : [];
  const video = $("preview");
  const src = `/media/proxy/${encodeURIComponent(sourceStem(r))}.mp4`;
  const play = () => {
    video.currentTime = r.start;
    video.play();
    $("playInfo").textContent = `${p.idx + 1}/${edl().order.length} · ${r.id}`;
  };
  if (!video.src.endsWith(src)) {
    video.src = src;
    video.onloadedmetadata = play;
  } else {
    play();
  }
}

function stopSequence() {
  state.player.playing = false;
  state.player.idx = -1;
  const video = $("preview");
  video.pause();
  video.onloadedmetadata = null;
  $("subOverlay").textContent = "";
  $("playInfo").textContent = "";
  renderCropFrame();
}

function onTimeUpdate() {
  const p = state.player;
  if (!p.playing || p.idx < 0) return;
  const r = rangeById(edl().order[p.idx]);
  const t = $("preview").currentTime;
  const ev = p.events.find((e) => t >= e.start && t <= e.end);
  applySubStyle();
  $("subOverlay").textContent = ev ? ev.text : "";
  if (t >= r.end - 0.03) nextSegment(); // pauza-cięcie-play
}

function applySubStyle() {
  const s = prefs().subtitles;
  const o = $("subOverlay");
  const scale = $("videoWrap").clientHeight / 1080; // przybliżenie stylu z preferences
  o.style.fontFamily = s.font_family;
  o.style.fontSize = `${Math.max(12, s.font_size * 2.4 * scale)}px`;
  o.style.color = s.primary_color;
  o.style.webkitTextStroke = `${Math.min(2, s.outline)}px ${s.outline_color}`;
}

/* ---------- preferencje ---------- */

let fontsCache = null;
async function renderPrefsPanel() {
  const panel = $("prefsPanel");
  const s = prefs().subtitles;
  if (!fontsCache) {
    try { fontsCache = (await (await fetch("/api/fonts")).json()).fonts; }
    catch { fontsCache = []; }
  }
  const fontOpts = [s.font_family, ...fontsCache.filter((f) => f !== s.font_family)]
    .map((f) => `<option value="${escapeHtml(f)}" ${f === s.font_family ? "selected" : ""}>${escapeHtml(f)}</option>`)
    .join("");
  const fmts = ["9x16", "16x9", "1x1"];
  panel.innerHTML = `
    <label>Font <select id="pfFont">${fontOpts}</select></label>
    <label>Rozmiar <input id="pfSize" type="number" min="8" max="60" value="${s.font_size}"></label>
    <label>Wielkość liter
      <select id="pfCase">
        <option value="natural" ${s.case === "natural" ? "selected" : ""}>naturalna</option>
        <option value="upper" ${s.case === "upper" ? "selected" : ""}>WERSALIKI</option>
      </select></label>
    <label>Słów na linię <input id="pfChunk" type="number" min="1" max="8" value="${s.chunk_words}"></label>
    <label>Napisy domyślnie <input id="pfDefault" type="checkbox" ${s.default ? "checked" : ""}></label>
    <div class="fmt-row">${fmts.map((f) =>
      `<label><input type="checkbox" data-fmt="${f}" ${prefs().output.formats.includes(f) ? "checked" : ""}> ${f}</label>`).join("")}
    </div>
    <label>Grade
      <select id="pfGrade">
        ${["none", "neutral_punch", "warm_cinematic"].map((g) =>
          `<option value="${g}" ${prefs().grade === g ? "selected" : ""}>${g}</option>`).join("")}
      </select></label>`;
  $("pfFont").onchange = (e) => { s.font_family = e.target.value; savePrefsDebounced(); };
  $("pfSize").onchange = (e) => { s.font_size = +e.target.value; savePrefsDebounced(); };
  $("pfCase").onchange = (e) => { s.case = e.target.value; savePrefsDebounced(); };
  $("pfChunk").onchange = (e) => { s.chunk_words = +e.target.value; savePrefsDebounced(); };
  $("pfDefault").onchange = (e) => { s.default = e.target.checked; savePrefsDebounced(); };
  $("pfGrade").onchange = (e) => { prefs().grade = e.target.value; savePrefsDebounced(); };
  panel.querySelectorAll("input[data-fmt]").forEach((cb) => {
    cb.onchange = () => {
      const on = [...panel.querySelectorAll("input[data-fmt]:checked")].map((x) => x.dataset.fmt);
      if (on.length) { prefs().output.formats = on; savePrefsDebounced(); }
      else cb.checked = true;
    };
  });
}

/* ---------- render + wersje ---------- */

async function startRender(proxy) {
  edl().approved = true; // przycisk w UI = zatwierdzenie renderu
  clearTimeout(state.saveTimer);
  await saveEdl();
  if (state.pendingEdl) return; // konflikt — najpierw rozwiąż
  const res = await fetch("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proxy, note: $("renderNote").value || "" }),
  });
  if (!res.ok) { alert("Render odrzucony: " + (await res.json()).detail); return; }
  $("renderProgress").classList.remove("hidden");
  pollRenderStatus();
}

async function pollRenderStatus() {
  const st = await (await fetch("/api/render/status")).json();
  $("renderBar").style.width = `${st.progress_pct}%`;
  $("renderPct").textContent = st.error ? `BŁĄD` : `${st.progress_pct}%`;
  $("renderLog").textContent = st.error || st.log_tail;
  if (st.running) { setTimeout(pollRenderStatus, 1000); return; }
  if (!st.error) {
    setTimeout(() => $("renderProgress").classList.add("hidden"), 1500);
    await fetchState();
    if (st.last_version) playVersion(st.last_version);
  }
}

function renderVersions() {
  const list = $("versionsList");
  list.innerHTML = "";
  state.data.versions.forEach((v) => {
    const chip = document.createElement("span");
    chip.className = "version-chip";
    const note = v.manifest.note ? `<span class="note" title="${escapeHtml(v.manifest.note)}">${escapeHtml(v.manifest.note)}</span>` : "";
    chip.innerHTML = `<button data-play title="odtwórz (shift-klik: porównaj obok)"><b>${v.version}</b></button>
      ${v.manifest.proxy ? '<span class="note">proxy</span>' : ""}${note}
      <button data-restore title="przywróć EDL z tej wersji">⤺</button>`;
    chip.querySelector("[data-play]").addEventListener("click", (e) =>
      e.shiftKey ? compareVersion(v) : playVersion(v.version));
    chip.querySelector("[data-restore]").addEventListener("click", () => restoreVersion(v.version));
    list.appendChild(chip);
  });
}

function versionOutput(v) {
  const fmt = primaryFormat();
  return v.outputs[fmt] || Object.values(v.outputs)[0];
}

function playVersion(name) {
  const v = state.data.versions.find((x) => x.version === name);
  if (!v) return;
  stopSequence();
  state.selected = null;
  const video = $("preview");
  video.src = versionOutput(v);
  video.controls = true;
  video.play();
  $("playInfo").textContent = `wersja ${name} (${v.manifest.durations_s?.[primaryFormat()] ?? "?"} s)`;
  renderSegments();
  renderTrimPanel();
  renderCropFrame();
}

function compareVersion(v) {
  $("compareWrap").classList.remove("hidden");
  $("compareVideo").src = versionOutput(v);
  $("compareLabel").textContent = `porównanie: ${v.version}`;
}

async function restoreVersion(name) {
  if (!confirm(`Przywrócić edl.json z wersji ${name}? Obecny stan zostanie nadpisany.`)) return;
  const res = await fetch(`/media/versions/${name}/edl.json`);
  const versionEdl = await res.json();
  const put = await fetch("/api/edl?force=true", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(versionEdl),
  });
  if (!put.ok) { alert("Nie udało się przywrócić: " + (await put.json()).detail); return; }
  await fetchState();
}

/* ---------- render całości ---------- */

function renderTotalTime() {
  const total = edl() ? edl().order.reduce((acc, id) => acc + dur(rangeById(id)), 0) : 0;
  $("totalTime").textContent = fmtTime(total);
}

function renderAll() {
  if (!state.data) return;
  $("projectName").textContent = state.data.project;
  if (!edl()) {
    $("segmentsList").innerHTML = '<p style="color:var(--fg-dim)">Brak edl.json — użyj <code>kadr plan --auto</code> albo agenta.</p>';
    renderVersions();
    return;
  }
  renderTotalTime();
  renderSegments();
  renderTrimPanel();
  renderVersions();
  renderPrefsPanel();
  renderCropFrame();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- init ---------- */

$("btnPlay").addEventListener("click", () => { $("preview").controls = false; playSequence(); });
$("btnStop").addEventListener("click", stopSequence);
$("preview").addEventListener("timeupdate", onTimeUpdate);
$("btnRenderProxy").addEventListener("click", () => startRender(true));
$("btnRenderFinal").addEventListener("click", () => startRender(false));
$("btnReload").addEventListener("click", fetchState);
$("btnConflictReload").addEventListener("click", async () => {
  $("conflictDialog").close();
  state.pendingEdl = null;
  state.dirty = false;
  await fetchState();
  setSaveIndicator("zapisano", "save-ok");
});
$("btnConflictOverwrite").addEventListener("click", async () => {
  $("conflictDialog").close();
  await saveEdl(true);
  renderAll();
});
window.addEventListener("resize", renderCropFrame);

fetchState();
