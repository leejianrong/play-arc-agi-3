// Pure mapping logic (Q10 in QUESTIONS.md) — no DOM, so it's covered by an
// automated unit test (tests/unit/test_input_mapping.test.mjs) even though
// the rest of the frontend only gets a manual end-to-end pass.

export const KEY_TO_ACTION_ID = Object.freeze({
  ArrowUp: 1,
  w: 1,
  W: 1,
  ArrowDown: 2,
  s: 2,
  S: 2,
  ArrowLeft: 3,
  a: 3,
  A: 3,
  ArrowRight: 4,
  d: 4,
  D: 4,
  " ": 5,
  Enter: 5,
  Backspace: 7,
  r: 0,
  R: 0,
});

export function keyToActionId(key) {
  return Object.prototype.hasOwnProperty.call(KEY_TO_ACTION_ID, key)
    ? KEY_TO_ACTION_ID[key]
    : null;
}

const GRID_SIZE = 64;

export function clickToGridCoords(clickX, clickY, elementWidth, elementHeight) {
  const clampedX = Math.min(Math.max(clickX, 0), elementWidth - 1);
  const clampedY = Math.min(Math.max(clickY, 0), elementHeight - 1);
  return {
    x: Math.min(Math.floor((clampedX / elementWidth) * GRID_SIZE), GRID_SIZE - 1),
    y: Math.min(Math.floor((clampedY / elementHeight) * GRID_SIZE), GRID_SIZE - 1),
  };
}
