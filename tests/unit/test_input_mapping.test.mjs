import { test } from "node:test";
import assert from "node:assert/strict";
import { keyToActionId, clickToGridCoords } from "../../frontend/input_mapping.js";

test("arrow keys and WASD map to ACTION1-4", () => {
  assert.equal(keyToActionId("ArrowUp"), 1);
  assert.equal(keyToActionId("w"), 1);
  assert.equal(keyToActionId("ArrowDown"), 2);
  assert.equal(keyToActionId("s"), 2);
  assert.equal(keyToActionId("ArrowLeft"), 3);
  assert.equal(keyToActionId("a"), 3);
  assert.equal(keyToActionId("ArrowRight"), 4);
  assert.equal(keyToActionId("d"), 4);
});

test("space/enter map to ACTION5, backspace to ACTION7, r to RESET", () => {
  assert.equal(keyToActionId(" "), 5);
  assert.equal(keyToActionId("Enter"), 5);
  assert.equal(keyToActionId("Backspace"), 7);
  assert.equal(keyToActionId("r"), 0);
  assert.equal(keyToActionId("R"), 0);
});

test("unmapped keys return null", () => {
  assert.equal(keyToActionId("q"), null);
  assert.equal(keyToActionId("Escape"), null);
});

test("click at top-left maps to grid (0, 0)", () => {
  assert.deepEqual(clickToGridCoords(0, 0, 512, 512), { x: 0, y: 0 });
});

test("click at bottom-right maps to grid (63, 63), not 64", () => {
  assert.deepEqual(clickToGridCoords(511, 511, 512, 512), { x: 63, y: 63 });
});

test("click at exact center maps to grid (32, 32)", () => {
  assert.deepEqual(clickToGridCoords(256, 256, 512, 512), { x: 32, y: 32 });
});

test("click coordinates are clamped to the element bounds", () => {
  assert.deepEqual(clickToGridCoords(-10, 600, 512, 512), { x: 0, y: 63 });
});

test("mapping scales correctly for a differently-sized canvas", () => {
  assert.deepEqual(clickToGridCoords(128, 0, 256, 256), { x: 32, y: 0 });
});
