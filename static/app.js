/* AI Jukebox frontend: generation forms, library, queue, and the player. */
"use strict";

/* ------------------------------------------------------- state ---------- */
const audio = document.getElementById("player");
const state = {
  queue: [],          // items: {kind:'song'|'dj', ...}
  index: -1,
  songs: [],
};

/* DJ languages supported by the Chatterbox endpoint (backend config). */
const DJ_LANGUAGES = {
  en: "English", es: "Spanish", fr: "French", de: "German", it: "Italian",
  pt: "Portuguese", ja: "Japanese", ko: "Korean", zh: "Chinese", hi: "Hindi",
  ar: "Arabic", ru: "Russian", nl: "Dutch", pl: "Polish", sv: "Swedish",
  tr: "Turkish", da: "Danish", fi: "Finnish", el: "Greek", he: "Hebrew",
  ms: "Malay", no: "Norwegian", sw: "Swahili",
};

const $ = (id) => document.getElementById(id);
const COVER_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'%3E%3Crect fill='%23191f2e' width='200' height='200'/%3E%3C/svg%3E";
const api = async (path, opts = {}) => {
  const headers = opts.body ? { "Content-Type": "application/json" } : {};
  const name = localStorage.getItem("jukebox_user") || "";
  if (name) headers["X-Username"] = name;  // lightweight identity for playlists
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers,
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
        <button class="sc-btn" data-act="pl" title="Add to playlist">📃</button>
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
    card.querySelector('[data-act="pl"]').onclick = (e) => {
      e.stopPropagation();
      openAddModal("song", song.id);
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
        <button class="sc-btn" data-act="pl" title="Add to playlist">📃</button>
        <button class="sc-btn" data-act="del" title="Delete">🗑</button>
      </span>`;
    li.querySelector('[data-act="play"]').onclick = async (e) => {
      e.stopPropagation();
      const full = await api(`/api/shows/${show.id}`);
      loadShowQueue(full);
    };
    li.querySelector('[data-act="pl"]').onclick = (e) => {
      e.stopPropagation();
      openAddModal("show", show.id);
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
    dj_language: $("dj-language").value,
    dj_speed: Number($("dj-speed").value),
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
$("dj-speed").addEventListener("input", () => {
  $("dj-speed-val").textContent = Number($("dj-speed").value).toFixed(2) + "×";
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

/* ------------------------------------------------------ playlists ------- */
const pl = { mine: [], detail: null, addKind: null, addId: null };

function myName() {
  return localStorage.getItem("jukebox_user") || "";
}

function renderNickname() {
  $("nickname").value = myName();
}

$("save-nickname").onclick = () => {
  const name = $("nickname").value.trim();
  if (!name) { toast("Enter a name first", true); return; }
  localStorage.setItem("jukebox_user", name);
  renderNickname();
  toast(`You are now “${name}” — your playlists will be attributed to this name.`);
  refreshPlaylists();
};

$("create-playlist").onclick = async () => {
  if (!myName()) { toast("Set a name first (above)", true); return; }
  const name = $("new-pl-name").value.trim();
  if (!name) { toast("Give the playlist a name", true); return; }
  try {
    await api("/api/playlists", { method: "POST", body: { name, public: $("new-pl-public").checked } });
    $("new-pl-name").value = "";
    toast(`“${name}” created`);
    await refreshPlaylists();
  } catch (err) { toast(err.message, true); }
};

async function refreshPlaylists() {
  const name = myName();
  const [mineData, communityData] = await Promise.all([
    api("/api/playlists" + (name ? `?owner=${encodeURIComponent(name)}` : "")),
    api("/api/playlists"),
  ]);
  pl.mine = mineData.playlists || [];
  pl.community = (communityData.playlists || []).filter((p) => p.owner !== name);
  renderMyPlaylists();
  renderCommunity();
}

function renderMyPlaylists() {
  $("my-pl-count").textContent = pl.mine.length;
  const ul = $("my-playlists");
  ul.innerHTML = "";
  if (!pl.mine.length) {
    ul.innerHTML = '<p class="muted small">No playlists yet — create one above, or add a song with 📃.</p>';
    return;
  }
  pl.mine.forEach((p) => {
    const li = document.createElement("li");
    li.className = "pl-row";
    li.innerHTML = `
      <img class="pl-thumb" src="${p.cover_url || COVER_PLACEHOLDER}" alt="">
      <div class="pl-info">
        <div class="pl-name">${escapeHtml(p.name)}</div>
        <div class="pl-sub">${p.item_count} item(s)</div>
      </div>
      <span class="badge ${p.public ? "public" : "private"}">${p.public ? "public" : "private"}</span>
      <span class="pl-btns">
        <button class="sc-btn" data-act="open" title="Open">📂</button>
        <button class="sc-btn" data-act="del" title="Delete">🗑</button>
      </span>`;
    li.querySelector('[data-act="open"]').onclick = (e) => { e.stopPropagation(); openPlaylist(p.id); };
    li.querySelector('[data-act="del"]').onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete playlist “${p.name}”?`)) return;
      try {
        await api(`/api/playlists/${p.id}`, { method: "DELETE" });
        toast("Playlist deleted");
        await refreshPlaylists();
      } catch (err) { toast(err.message, true); }
    };
    li.onclick = () => openPlaylist(p.id);
    ul.appendChild(li);
  });
}

function renderCommunity() {
  const ul = $("community-playlists");
  ul.innerHTML = "";
  if (!pl.community.length) {
    ul.innerHTML = '<p class="muted small">No public playlists yet — be the first!</p>';
    return;
  }
  pl.community.forEach((p) => {
    const li = document.createElement("li");
    li.className = "pl-row";
    li.innerHTML = `
      <img class="pl-thumb" src="${p.cover_url || COVER_PLACEHOLDER}" alt="">
      <div class="pl-info">
        <div class="pl-name">${escapeHtml(p.name)}</div>
        <div class="pl-sub">by ${escapeHtml(p.owner)} · ${p.item_count} item(s)</div>
      </div>
      <span class="badge public">public</span>`;
    li.onclick = () => openPlaylist(p.id);
    ul.appendChild(li);
  });
}

async function openPlaylist(id) {
  try {
    pl.detail = await api(`/api/playlists/${id}`);
    renderPlaylistModal(pl.detail);
    $("playlist-modal").classList.remove("hidden");
  } catch (err) { toast(err.message, true); }
}

function renderPlaylistModal(p) {
  $("pl-name").textContent = p.name;
  $("pl-meta").textContent = `by ${p.owner} · ${p.items.length} item(s) · ${p.public ? "public" : "private"}`;
  $("pl-public").checked = p.public;
  $("pl-public-wrap").style.display = p.is_owner ? "" : "none";
  $("pl-add-items").style.display = p.is_owner ? "" : "none";
  $("pl-rename").style.display = p.is_owner ? "" : "none";
  $("pl-delete").style.display = p.is_owner ? "" : "none";
  $("pl-empty").style.display = p.items.length ? "none" : "";
  const ul = $("pl-items");
  ul.innerHTML = "";
  p.items.forEach((item) => {
    const isSong = item.kind === "song";
    const ref = item.ref;
    const title = ref ? (isSong ? ref.title : ref.name) : "(deleted)";
    const sub = !ref
      ? (isSong ? "song no longer in the library" : "show no longer in the library")
      : (isSong ? `${ref.artist || "unknown artist"} · ${ref.duration || "?"}s` : `radio show · ${ref.segments} segments`);
    const thumb = isSong && ref && ref.cover_url ? ref.cover_url : COVER_PLACEHOLDER;
    const vis = p.is_owner
      ? `<label class="item-vis" title="Visible to everyone, or just you"><input type="checkbox" data-act="vis" ${item.public ? "checked" : ""}> visible</label>`
      : `<span class="badge ${item.public ? "public" : "private"}">${item.public ? "public" : "private"}</span>`;
    const li = document.createElement("li");
    li.className = "pl-item";
    li.innerHTML = `
      <span class="kind-chip">${isSong ? "song" : "show"}</span>
      <img class="pl-thumb" src="${thumb}" alt="">
      <div class="pl-info">
        <div class="pl-title">${escapeHtml(title)}</div>
        <div class="pl-sub">${escapeHtml(sub)}</div>
      </div>
      ${vis}
      <span class="pl-btns">
        <button class="sc-btn" data-act="play" title="Play">▶</button>
        ${p.is_owner ? '<button class="sc-btn" data-act="rm" title="Remove from playlist">✕</button>' : ""}
      </span>`;
    li.querySelector('[data-act="play"]').onclick = () => playPlaylistItem(item);
    if (p.is_owner) {
      li.querySelector('[data-act="vis"]').onchange = async (e) => {
        try {
          await api(`/api/playlists/${p.id}/items/${item.uid}`, { method: "PATCH", body: { public: e.target.checked } });
          toast(e.target.checked ? "Visible to everyone" : "Hidden — only you can see this");
          openPlaylist(p.id);
        } catch (err) { toast(err.message, true); }
      };
      li.querySelector('[data-act="rm"]').onclick = async () => {
        try {
          await api(`/api/playlists/${p.id}/items/${item.uid}`, { method: "DELETE" });
          toast("Removed from playlist");
          openPlaylist(p.id);
        } catch (err) { toast(err.message, true); }
      };
    }
    ul.appendChild(li);
  });
}

async function playPlaylistItem(item) {
  if (item.kind === "song") {
    if (!item.ref || !item.ref.audio_url) { toast("Song no longer in the library", true); return; }
    enqueue({ kind: "song", ...item.ref }, { autoplay: true });
    return;
  }
  try {
    const show = await api(`/api/shows/${item.id}`);
    loadShowQueue(show);
  } catch (err) { toast(err.message, true); }
}

$("pl-public").onchange = async (e) => {
  try {
    await api(`/api/playlists/${pl.detail.id}`, { method: "PATCH", body: { public: e.target.checked } });
    toast(e.target.checked ? "Playlist is public — everyone can browse it" : "Playlist is now private");
    openPlaylist(pl.detail.id);
    refreshPlaylists();
  } catch (err) { toast(err.message, true); }
};

$("pl-rename").onclick = async () => {
  const name = prompt("Playlist name", pl.detail.name);
  if (!name || !name.trim()) return;
  try {
    await api(`/api/playlists/${pl.detail.id}`, { method: "PATCH", body: { name: name.trim() } });
    toast("Renamed");
    openPlaylist(pl.detail.id);
    refreshPlaylists();
  } catch (err) { toast(err.message, true); }
};

$("pl-delete").onclick = async () => {
  if (!confirm(`Delete playlist “${pl.detail.name}”?`)) return;
  try {
    await api(`/api/playlists/${pl.detail.id}`, { method: "DELETE" });
    $("playlist-modal").classList.add("hidden");
    toast("Playlist deleted");
    refreshPlaylists();
  } catch (err) { toast(err.message, true); }
};

$("close-playlist").onclick = () => $("playlist-modal").classList.add("hidden");
// click the backdrop (but not the box) or press Esc to close either modal
$("playlist-modal").addEventListener("click", (e) => {
  if (e.target === $("playlist-modal")) $("playlist-modal").classList.add("hidden");
});
$("add-modal").addEventListener("click", (e) => {
  if (e.target === $("add-modal")) closeAddModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("add-modal").classList.add("hidden");
    $("playlist-modal").classList.add("hidden");
  }
});

function closeAddModal() {
  $("add-modal").classList.add("hidden");
  pl.addKind = null;
  pl.addId = null;
}

/* --- add-to-playlist chooser / library picker --- */
// Two modes, one modal:
//  - from a library card:   openAddModal("song"|"show", id)  => pick a playlist
//  - from a playlist (＋ Add songs): openAddModal(null, null) => pick library items
function openAddModal(kind, id) {
  if (!myName()) { toast("Set a name first (My playlists card)", true); return; }
  pl.addKind = kind;
  pl.addId = id;
  $("add-new-name").value = "";
  $("add-modal").classList.remove("hidden");
  if (kind) {
    $("add-modal-title").textContent = "Add to playlist";
    $("add-new-name").placeholder = "…or a new playlist name";
    $("add-new-row").style.display = "";
    renderPlaylistChooser();
  } else {
    $("add-modal-title").textContent = `Add songs & shows to “${pl.detail ? pl.detail.name : "…"}”`;
    $("add-new-name").placeholder = "";
    $("add-new-row").style.display = "none";
    renderLibraryPicker();
  }
}

function renderPlaylistChooser() {
  const list = $("add-pl-list");
  list.innerHTML = "";
  if (!pl.mine.length) {
    list.innerHTML = '<p class="muted small">No playlists yet — create one below.</p>';
    return;
  }
  pl.mine.forEach((p) => {
    const li = document.createElement("li");
    li.className = "pl-row";
    li.innerHTML = `
      <span class="pl-name" style="flex:1">${escapeHtml(p.name)}</span>
      <span class="badge ${p.public ? "public" : "private"}">${p.public ? "public" : "private"}</span>`;
    li.onclick = () => addToPlaylist(p);
    list.appendChild(li);
  });
}

async function renderLibraryPicker() {
  const list = $("add-pl-list");
  list.innerHTML = '<p class="muted small">Loading…</p>';
  let songs, shows;
  try {
    [songs, shows] = await Promise.all([api("/api/songs"), api("/api/shows")]);
  } catch (err) { list.innerHTML = ""; toast(err.message, true); return; }
  const inPlaylist = new Set((pl.detail?.items || []).map((it) => `${it.kind}:${it.id}`));
  list.innerHTML = "";
  const rows = [];
  (songs.songs || []).forEach((s) => rows.push({ kind: "song", id: s.id, title: s.title, sub: s.artist, thumb: s.cover_url }));
  (shows.shows || []).forEach((sh) => rows.push({ kind: "show", id: sh.id, title: sh.name, sub: `${(sh.segments || []).filter(x => x.kind === "song").length} tracks · show`, thumb: "" }));
  if (!rows.length) {
    list.innerHTML = '<p class="muted small">The library is empty — generate a song first!</p>';
    return;
  }
  rows.forEach((r) => {
    const isIn = inPlaylist.has(`${r.kind}:${r.id}`);
    const li = document.createElement("li");
    li.className = "pl-row";
    li.innerHTML = `
      <img class="pl-thumb" src="${r.thumb || COVER_PLACEHOLDER}" alt="">
      <div class="pl-info">
        <div class="pl-name">${escapeHtml(r.title)}</div>
        <div class="pl-sub">${escapeHtml(r.sub)}</div>
      </div>
      <span class="pl-btns">
        ${isIn ? '<span class="badge public">added</span>'
              : `<button class="sc-btn" data-add="yes" title="Add to playlist">＋</button>`}
      </span>`;
    li.querySelector('[data-add="yes"]')?.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        await api(`/api/playlists/${pl.detail.id}/items`, { method: "POST", body: { kind: r.kind, id: r.id } });
        toast(`Added “${r.title}”`);
        openPlaylist(pl.detail.id);   // refresh the detail view
        renderLibraryPicker();        // keep the picker in sync
      } catch (err) { toast(err.message, true); }
    });
    list.appendChild(li);
  });
}

async function addToPlaylist(p) {
  try {
    await api(`/api/playlists/${p.id}/items`, { method: "POST", body: { kind: pl.addKind, id: pl.addId } });
    closeAddModal();
    toast(`Added to “${p.name}”`);
    refreshPlaylists();
  } catch (err) { toast(err.message, true); }
}

$("pl-add-items").onclick = () => {
  if (!pl.detail || !pl.detail.is_owner) return;
  openAddModal(null, null);
};

$("add-new-btn").onclick = async () => {
  const name = $("add-new-name").value.trim();
  if (!name) { toast("Name the new playlist", true); return; }
  try {
    const created = await api("/api/playlists", { method: "POST", body: { name, public: true } });
    await api(`/api/playlists/${created.id}/items`, { method: "POST", body: { kind: pl.addKind, id: pl.addId } });
    $("add-modal").classList.add("hidden");
    toast(`Created “${name}” and added it`);
    refreshPlaylists();
  } catch (err) { toast(err.message, true); }
};

$("close-add").onclick = () => $("add-modal").classList.add("hidden");

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
  // Populate the DJ language selector (English first, rest alphabetical).
  const langSel = $("dj-language");
  Object.entries(DJ_LANGUAGES)
    .sort(([a], [b]) => (a === "en" ? -1 : b === "en" ? 1 : a.localeCompare(b)))
    .forEach(([code, name]) => {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = `${name} (${code})`;
      langSel.appendChild(opt);
    });

  checkHealth();
  setInterval(checkHealth, 30000);
  renderNickname();
  try {
    await Promise.all([refreshLibrary(), refreshShows(), refreshPlaylists()]);
  } catch (err) {
    toast(err.message, true);
  }
})();
