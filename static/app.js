/* AI Jukebox frontend: generation forms, library, queue, and the player. */
"use strict";

/* ------------------------------------------------------- state ---------- */
const audio = document.getElementById("player");
const state = {
  queue: [],          // items: {kind:'song'|'dj', ...}
  index: -1,
  songs: [],
};

const $ = (id) => document.getElementById(id);
const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = data && (typeof data.detail === "string"
      ? data.detail
      : JSON.stringify(data.detail || data));
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
};

/* ------------------------------------------------------- helpers -------- */
function fmtTime(sec) {
  if (!isFinite(sec)) return "0:00";
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

let toastTimer;
function toast(msg, isErr = false) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 4200);
}

function songFormPayload() {
  return {
    genre: $("genre").value,
    mood: $("mood").value,
    theme: $("theme").value.trim() || "a moment in time",
    duration: Number($("duration").value),
    vocals: $("vocals").checked,
    language: $("language").value,
    bpm: $("bpm").value ? Number($("bpm").value) : null,
    key_scale: $("key").value,
    cover_style: $("cover-style").value,
    artist: $("artist").value.trim(),
    title: $("title").value.trim(),
  };
}

/* ------------------------------------------------- busy overlay --------- */
const BUSY_STAGES = [
  "warming up the vocals",
  "writing lyrics…",
  "composing harmonies…",
  "painting the cover art…",
  "mixing the master…",
  "polishing the vinyl…",
];
function busy(title, on) {
  $("busy-overlay").classList.toggle("hidden", !on);
  $("make-song-btn").disabled = on;
  $("make-show-btn").disabled = on;
  if (on) {
    $("busy-title").textContent = title;
    let i = 0;
    $("busy-stage").textContent = BUSY_STAGES[0];
    const bar = $("busy-bar");
    bar.style.width = "8%";
    state._busyTimer = setInterval(() => {
      i = (i + 1) % BUSY_STAGES.length;
      $("busy-stage").textContent = BUSY_STAGES[i];
      bar.style.width = Math.min(88, 8 + i * 14) + "%";
    }, BUSY_STAGES.length > 0 ? 4500 : 0);
  } else {
    clearInterval(state._busyTimer);
  }
}

/* ------------------------------------------------------- player --------- */
function renderNowPlaying() {
  const item = state.index >= 0 ? state.queue[state.index] : null;
  const isDj = item && item.kind === "dj";

  $("dj-banner").classList.toggle("hidden", !isDj);
  if (isDj) $("dj-script").textContent = item.script || "";

  if (!item || isDj) {
    if (!isDj) {
      $("np-status").textContent = "Nothing playing";
      $("np-title").textContent = "—";
      $("np-artist").textContent = "—";
      $("np-chips").innerHTML = "";
      $("lyrics-text").textContent = "";
    } else {
      $("np-status").textContent = "the DJ is talking…";
    }
    return;
  }
  if (item.kind === "song") {
    $("np-status").textContent = isNaN(audio.currentTime) || !audio.currentTime ? "now playing" : "now playing";
    $("np-title").textContent = item.title || "Untitled";
    $("np-artist").textContent = item.artist || "";
    $("np-cover").src = item.cover_url || $("np-cover").src;
    $("np-spinner").classList.add("hidden");
    $("np-chips").innerHTML = [
      item.genre, item.mood, item.bpm ? `${item.bpm} BPM` : "",
      item.key, item.language && item.language !== "English" ? item.language : "",
      item.vocals === false ? "instrumental" : "",
    ].filter(Boolean).map((c) => `<span>${c}</span>`).join("");
    $("lyrics-text").textContent = item.lyrics || "";
  }
}

function playIndex(idx) {
  if (idx < 0 || idx >= state.queue.length) { stopPlayback(); return; }
  state.index = idx;
  const item = state.queue[idx];
  renderNowPlaying();
  renderQueue();
  audio.src = item.audio_url;
  audio.play().catch((e) => toast("Playback blocked: " + e.message, true));
}

function stopPlayback() {
  state.index = -1;
  audio.pause();
  audio.removeAttribute("src");
  renderNowPlaying();
  renderQueue();
}

function enqueue(item, { autoplay = false } = {}) {
  state.queue.push(item);
  if (autoplay || state.index < 0) playIndex(state.queue.length - 1);
  else renderQueue();
}

function loadQueue(items, startAt = 0) {
  state.queue = items.slice();
  playIndex(Math.min(startAt, items.length - 1));
}

audio.addEventListener("timeupdate", () => {
  $("progress-label").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
  const i = state.index;
  if (i >= 0 && state.queue[i] && state.queue[i].kind === "song") {
    $("np-status").textContent = "now playing";
  }
});
audio.addEventListener("ended", () => {
  if (state.index < state.queue.length - 1) playIndex(state.index + 1);
  else stopPlayback();
});
audio.addEventListener("error", () => {
  if (state.index >= 0) {
    toast("Couldn't play an item — skipping.", true);
    if (state.index < state.queue.length - 1) playIndex(state.index + 1);
  }
});
audio.addEventListener("play", () => { $("btn-play").textContent = "⏸"; });
audio.addEventListener("pause", () => { $("btn-play").textContent = "▶"; });

$("btn-play").onclick = () => {
  if (state.index < 0) { if (state.queue.length) playIndex(0); return; }
  audio.paused ? audio.play() : audio.pause();
};
$("btn-next").onclick = () => playIndex(Math.min(state.index + 1, state.queue.length - 1));
$("btn-prev").onclick = () => playIndex(Math.max(state.index - 1, 0));
$("btn-lyrics").onclick = () => $("lyrics-panel").classList.toggle("hidden");
$("btn-clear-queue").onclick = () => { state.queue = []; stopPlayback(); };

function renderQueue() {
  const ul = $("queue");
  ul.innerHTML = "";
  state.queue.forEach((item, i) => {
    const li = document.createElement("li");
    if (i === state.index) li.classList.add("active");
    if (item.kind === "song") {
      const img = document.createElement("img");
      img.className = "thumb";
      img.src = item.cover_url || "";
      li.appendChild(img);
      const kind = document.createElement("span");
      kind.className = "q-kind song";
      kind.textContent = "track";
      li.appendChild(kind);
      const name = document.createElement("span");
      name.textContent = `${item.title || "Untitled"} — ${item.artist || ""}`;
      li.appendChild(name);
    } else {
      const kind = document.createElement("span");
      kind.className = "q-kind dj";
      kind.textContent = "DJ";
      li.appendChild(kind);
      const name = document.createElement("span");
      name.textContent = item.label || "segue";
      li.appendChild(name);
    }
    const sub = document.createElement("span");
    sub.className = "q-sub";
    sub.textContent = "…";
    li.appendChild(sub);
    li.onclick = () => playIndex(i);
    ul.appendChild(li);
  });
  $("queue-count").textContent = state.queue.length;
}

/* ------------------------------------------------------ library --------- */
async function refreshLibrary() {
  const data = await api("/api/songs");
  state.songs = data.songs || [];
  $("lib-count").textContent = state.songs.length;
  const lib = $("library");
  lib.innerHTML = "";
  if (!state.songs.length) {
    lib.innerHTML = '<p class="muted">No songs yet. Generate your first one →</p>';
    return;
  }
  state.songs.forEach((song) => {
    const card = document.createElement("div");
    card.className = "song-card";
    card.innerHTML = `
      <img src="${song.cover_url}" alt="cover" loading="lazy">
      <div class="sc-actions">
        <button class="sc-btn" data-act="play" title="Play now">▶</button>
        <button class="sc-btn" data-act="queue" title="Add to queue">＋</button>
        <button class="sc-btn" data-act="del" title="Delete">🗑</button>
      </div>
      <div class="sc-meta">
        <div class="sc-title">${escapeHtml(song.title || "Untitled")}</div>
        <div class="sc-sub">${escapeHtml(song.artist || "")} · ${fmtTime(song.duration)}</div>
      </div>`;
    const img = card.querySelector("img");
    img.onclick = () => enqueue({ kind: "song", ...song }, { autoplay: true });
    card.querySelector('[data-act="play"]').onclick = (e) => {
      e.stopPropagation();
      enqueue({ kind: "song", ...song }, { autoplay: true });
    };
    card.querySelector('[data-act="queue"]').onclick = (e) => {
      e.stopPropagation();
      enqueue({ kind: "song", ...song });
      toast(`Added "${song.title}" to the queue`);
    };
    card.querySelector('[data-act="del"]').onclick = async (e) => {
      e.stopPropagation();
      await api(`/api/songs/${song.id}`, { method: "DELETE" });
      await refreshLibrary();
    };
    lib.appendChild(card);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ------------------------------------------------------- shows ---------- */
async function refreshShows() {
  const data = await api("/api/shows");
  const shows = data.shows || [];
  $("shows-count").textContent = shows.length;
  const ul = $("shows");
  ul.innerHTML = "";
  shows.forEach((show) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="show-name">📻 ${escapeHtml(show.name)}</span>
      <span class="show-meta">${show.segments ? show.segments.filter(s => s.kind === "song").length : 0} tracks</span>
      <span class="show-btns">
        <button class="sc-btn" data-act="play" title="Play show">▶</button>
        <button class="sc-btn" data-act="del" title="Delete">🗑</button>
      </span>`;
    li.querySelector('[data-act="play"]').onclick = async (e) => {
      e.stopPropagation();
      const full = await api(`/api/shows/${show.id}`);
      loadShowQueue(full);
    };
    li.querySelector('[data-act="del"]').onclick = async (e) => {
      e.stopPropagation();
      await api(`/api/shows/${show.id}`, { method: "DELETE" });
      await refreshShows();
    };
    ul.appendChild(li);
  });
}

function loadShowQueue(show) {
  const items = (show.segments || []).map((seg) =>
    seg.kind === "song"
      ? { kind: "song", ...seg }
      : { kind: "dj", ...seg });
  loadQueue(items, 0);
  toast(`On air: ${show.name}`);
}

/* ------------------------------------------------------- generation ------ */
async function generateSong() {
  busy("Composing your song…", true);
  try {
    const song = await api("/api/songs", { method: "POST", body: songFormPayload() });
    await refreshLibrary();
    enqueue({ kind: "song", ...song }, { autoplay: true });
    toast(`"${song.title}" by ${song.artist} is on air!`);
  } catch (err) {
    toast(err.message || "Song generation failed", true);
  } finally {
    busy("", false);
  }
}

async function generateShow() {
  const payload = {
    ...songFormPayload(),
    n_tracks: Number($("n-tracks").value),
    dj_vibe: $("dj-vibe").value,
  };
  busy("Broadcasting…", true);
  try {
    const show = await api("/api/shows", { method: "POST", body: payload });
    await refreshLibrary();
    await refreshShows();
    loadShowQueue(show);
  } catch (err) {
    toast(err.message || "Show generation failed", true);
  } finally {
    busy("", false);
  }
}

$("song-form").addEventListener("submit", (e) => { e.preventDefault(); generateSong(); });
$("show-form").addEventListener("submit", (e) => { e.preventDefault(); generateShow(); });
$("duration").addEventListener("input", () => {
  $("duration-val").textContent = fmtTime(Number($("duration").value));
});

/* ------------------------------------------------------- dice ------------ */
$("random-theme-btn").addEventListener("click", async () => {
  const btn = $("random-theme-btn");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "🎲 …";
  try {
    const data = await api("/api/themes/random");
    const theme = (data.theme || "").trim();
    if (!theme) throw new Error("empty theme");
    $("theme").value = theme;
    toast(`Rolled: “${theme}”`);
  } catch (err) {
    toast(err.message || "Couldn't roll a theme", true);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
});

$("random-names-btn").addEventListener("click", async () => {
  const btn = $("random-names-btn");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "🎲 …";
  try {
    const data = await api("/api/names/random");
    const artist = (data.artist || "").trim();
    const title = (data.title || "").trim();
    if (!artist || !title) throw new Error("empty names");
    $("artist").value = artist;
    $("title").value = title;
    toast(`Rolled: “${title}” by ${artist}`);
  } catch (err) {
    toast(err.message || "Couldn't roll names", true);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
});

/* ------------------------------------------------------- health --------- */
async function checkHealth() {
  try {
    const h = await api("/api/health");
    const el = $("service-status");
    el.classList.toggle("ok", h.status === "ok");
    el.classList.toggle("degraded", h.status !== "ok");
    const rows = Object.entries(h.services || {});
    el.innerHTML = rows.map(([k, v]) =>
      `<span>${k}: ${v === "ok" ? "✅" : "❌ " + v}</span>`).join("<br>");
  } catch {
    $("service-status").textContent = "backend unreachable";
    $("service-status").classList.add("degraded");
  }
}

/* ------------------------------------------------------- init ----------- */
(async function init() {
  checkHealth();
  setInterval(checkHealth, 30000);
  try {
    await refreshLibrary();
    await refreshShows();
  } catch (err) {
    toast(err.message, true);
  }
})();
