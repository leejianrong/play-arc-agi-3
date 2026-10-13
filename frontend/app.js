import { keyToActionId, clickToGridCoords } from "/static/input_mapping.js";
import { PALETTE } from "/static/palette.js";
import { swatchGrid } from "/static/identicon.js";
import { createAnnotationUI } from "/static/annotation_ui.js";
import { annotationHotkey, isTypingTarget } from "/static/hotkeys.js";

const pickerEl = document.getElementById("picker");
const playEl = document.getElementById("play");
const canvas = document.getElementById("grid");
const ctx = canvas.getContext("2d");
const stateEl = document.getElementById("state");
const levelsEl = document.getElementById("levels");
const errorEl = document.getElementById("error");
const recordModeEl = document.getElementById("record-mode");
const controlsEl = document.querySelector(".controls");
const annotateEl = document.getElementById("annotate");
const noticeEl = document.getElementById("notice");
const endEl = document.getElementById("end");
const annotation = createAnnotationUI(document.getElementById("transcript"), {
  sendNote: (text) => ws.send(JSON.stringify({ type: "note", text })),
  sendPhase: (phase) => ws.send(JSON.stringify({ type: "phase", phase })),
});

const CELL_PX = canvas.width / 64;
const SWATCH_CELL_PX = 8;

let availableActions = [];
let errorTimer = null;
let noticeTimer = null;
let frameSeen = false; // distinguishes 'start failed' from 'error mid-game'

const ws = new WebSocket(`ws://${location.host}/ws/session`);

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "games") {
    renderPicker(message.games);
  } else if (message.type === "frame") {
    renderFrame(message.frame_data);
  } else if (message.type === "annotation") {
    annotation.start(message.session_id);
  } else if (message.type === "phase") {
    annotation.setPhase(message.phase);
  } else if (message.type === "note_saved") {
    annotation.addNote(message);
  } else if (message.type === "ended") {
    showPicker();
    const files = [message.recording, message.annotations, message.audio].filter(Boolean);
    if (files.length) showNotice(`Session saved in recordings/: ${files.join("  \u00b7  ")}`);
  } else if (message.type === "error") {
    showError(message.message);
    if (!frameSeen) showPicker(); // the game never started (e.g. annotation refused)
  }
});

// Annotations need a recording to align to (ADR-0007); the server promotes Off to Lean, and we
// show the same thing in the control so nobody is surprised.
annotateEl.addEventListener("change", () => {
  if (annotateEl.checked && recordModeEl.value === "off") recordModeEl.value = "lean";
});
recordModeEl.addEventListener("change", () => {
  if (annotateEl.checked && recordModeEl.value === "off") recordModeEl.value = "lean";
});

ws.addEventListener("close", () => showError("Connection to the local server closed."));

function renderPicker(games) {
  pickerEl.innerHTML = "";
  if (games.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No games available for this API key.";
    pickerEl.appendChild(empty);
    return;
  }
  for (const game of games) {
    pickerEl.appendChild(buildPickerRow(game));
  }
}

function buildPickerRow(game) {
  const row = document.createElement("button");
  row.className = "picker-row";
  row.type = "button";
  const heldOut = game.data_use === "heldout";
  row.addEventListener("click", () => startGame(game.game_id, heldOut));

  row.appendChild(buildSwatch(game.game_id));

  const text = document.createElement("div");
  text.className = "picker-row-text";

  const title = document.createElement("div");
  title.className = "picker-row-title";
  title.textContent = game.title || game.game_id;
  text.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "picker-row-meta";
  const id = document.createElement("span");
  id.textContent = game.game_id;
  meta.appendChild(id);
  for (const tag of game.tags || []) {
    const pill = document.createElement("span");
    pill.className = "tag";
    pill.textContent = tag;
    pill.style.color = PALETTE[1 + (hashTag(tag) % 9)];
    meta.appendChild(pill);
  }
  if (heldOut) {
    const pill = document.createElement("span");
    pill.className = "tag heldout";
    pill.textContent = "held-out";
    pill.title = "Held out for evaluation: you can play it, but it is never annotated (data_policy.json)";
    meta.appendChild(pill);
  }
  text.appendChild(meta);

  row.appendChild(text);
  return row;
}

function hashTag(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return h;
}

function buildSwatch(gameId) {
  const grid = swatchGrid(gameId);
  const swatch = document.createElement("canvas");
  swatch.className = "swatch";
  swatch.width = grid.length * SWATCH_CELL_PX;
  swatch.height = grid.length * SWATCH_CELL_PX;
  const sctx = swatch.getContext("2d");
  for (let row = 0; row < grid.length; row++) {
    for (let col = 0; col < grid[row].length; col++) {
      sctx.fillStyle = PALETTE[grid[row][col]];
      sctx.fillRect(col * SWATCH_CELL_PX, row * SWATCH_CELL_PX, SWATCH_CELL_PX, SWATCH_CELL_PX);
    }
  }
  return swatch;
}

function startGame(gameId, heldOut = false) {
  const annotate = annotateEl.checked && !heldOut;
  if (annotateEl.checked && heldOut) {
    showNotice("Held-out game: playing without annotation so the evaluation set stays clean.");
  }
  frameSeen = false;
  ws.send(JSON.stringify({ type: "start", game_id: gameId, record: recordModeEl.value, annotate }));
  pickerEl.style.display = "none";
  controlsEl.style.display = "none";
  playEl.style.display = "flex";
}

function showPicker() {
  annotation.stop();
  playEl.style.display = "none";
  pickerEl.style.display = "flex";
  controlsEl.style.display = "flex";
  frameSeen = false;
}

endEl.addEventListener("click", async () => {
  endEl.disabled = true;
  try {
    await annotation.finish(); // let the server write the sentence in progress first
    ws.send(JSON.stringify({ type: "end" }));
  } finally {
    endEl.disabled = false;
  }
});

function renderFrame(frameData) {
  frameSeen = true;
  availableActions = frameData.available_actions;
  stateEl.textContent = `state: ${frameData.state}`;
  levelsEl.textContent = `levels: ${frameData.levels_completed}/${frameData.win_levels}`;

  // Multiple grids can come back per response; the last one is the frame
  // actually resulting from the action (open risk, PLAN.md).
  const grid = frameData.frame[frameData.frame.length - 1];
  for (let row = 0; row < grid.length; row++) {
    for (let col = 0; col < grid[row].length; col++) {
      ctx.fillStyle = PALETTE[grid[row][col]] ?? "#FF00FF";
      ctx.fillRect(col * CELL_PX, row * CELL_PX, CELL_PX, CELL_PX);
    }
  }
}

function sendAction(actionId, x, y) {
  if (actionId !== 0 && !availableActions.includes(actionId)) return;
  const payload = { type: "action", action_id: actionId };
  if (x !== undefined) payload.x = x;
  if (y !== undefined) payload.y = y;
  ws.send(JSON.stringify(payload));
}

window.addEventListener("keydown", (event) => {
  if (playEl.style.display === "none") return;
  if (isTypingTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
  if (annotation.active) {
    const hotkey = annotationHotkey(event.key);
    if (hotkey) {
      event.preventDefault();
      if (hotkey.kind === "phase") ws.send(JSON.stringify({ type: "phase", phase: hotkey.phase }));
      else if (hotkey.kind === "mute") annotation.toggleMute();
      else if (hotkey.kind === "note") annotation.focusNote();
      return;
    }
  }
  const actionId = keyToActionId(event.key);
  if (actionId === null) return;
  event.preventDefault();
  sendAction(actionId);
});

canvas.addEventListener("click", (event) => {
  const rect = canvas.getBoundingClientRect();
  const { x, y } = clickToGridCoords(
    event.clientX - rect.left,
    event.clientY - rect.top,
    rect.width,
    rect.height
  );
  sendAction(6, x, y);
});

function showError(message) {
  errorEl.textContent = message;
  errorEl.style.display = "block";
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => (errorEl.style.display = "none"), 6000);
}

function showNotice(message) {
  noticeEl.textContent = message;
  noticeEl.style.display = "block";
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (noticeEl.style.display = "none"), 20000);
}
