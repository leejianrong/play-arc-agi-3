import { keyToActionId, clickToGridCoords } from "/static/input_mapping.js";
import { PALETTE } from "/static/palette.js";

const pickerEl = document.getElementById("picker");
const playEl = document.getElementById("play");
const canvas = document.getElementById("grid");
const ctx = canvas.getContext("2d");
const stateEl = document.getElementById("state");
const levelsEl = document.getElementById("levels");
const errorEl = document.getElementById("error");

const CELL_PX = canvas.width / 64;

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
    pickerEl.textContent = "No games available for this API key.";
    return;
  }
  for (const game of games) {
    const button = document.createElement("button");
    button.textContent = game.title ? `${game.title} (${game.game_id})` : game.game_id;
    button.addEventListener("click", () => startGame(game.game_id));
    pickerEl.appendChild(button);
  }
}

function startGame(gameId) {
  ws.send(JSON.stringify({ type: "start", game_id: gameId }));
  pickerEl.style.display = "none";
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
