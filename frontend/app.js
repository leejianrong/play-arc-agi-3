import { keyToActionId, clickToGridCoords } from "/static/input_mapping.js";
import { PALETTE } from "/static/palette.js";
import { swatchGrid } from "/static/identicon.js";

const pickerEl = document.getElementById("picker");
const playEl = document.getElementById("play");
const canvas = document.getElementById("grid");
const ctx = canvas.getContext("2d");
const stateEl = document.getElementById("state");
const levelsEl = document.getElementById("levels");
const errorEl = document.getElementById("error");
const recordModeEl = document.getElementById("record-mode");
const recordControlEl = document.querySelector(".record-control");

const CELL_PX = canvas.width / 64;
const SWATCH_CELL_PX = 8;

let availableActions = [];
let errorTimer = null;

const ws = new WebSocket(`ws://${location.host}/ws/session`);

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "games") {
    renderPicker(message.games);
  } else if (message.type === "frame") {
    renderFrame(message.frame_data);
  } else if (message.type === "error") {
    showError(message.message);
  }
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
  row.addEventListener("click", () => startGame(game.game_id));

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

function startGame(gameId) {
  ws.send(JSON.stringify({ type: "start", game_id: gameId, record: recordModeEl.value }));
  pickerEl.style.display = "none";
  recordControlEl.style.display = "none";
  playEl.style.display = "flex";
}

function renderFrame(frameData) {
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
