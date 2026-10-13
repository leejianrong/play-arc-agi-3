import assert from "node:assert/strict";
import test from "node:test";

import { KEY_TO_ACTION_ID } from "../../frontend/input_mapping.js";
import { PHASES, annotationHotkey, isTypingTarget } from "../../frontend/hotkeys.js";

test("digits 1-5 select the five phases in protocol order", () => {
  assert.deepEqual(
    ["1", "2", "3", "4", "5"].map((k) => annotationHotkey(k).phase),
    PHASES,
  );
});

test("M mutes and T focuses the note box, case-insensitively", () => {
  assert.deepEqual(annotationHotkey("m"), { kind: "mute" });
  assert.deepEqual(annotationHotkey("M"), { kind: "mute" });
  assert.deepEqual(annotationHotkey("t"), { kind: "note" });
  assert.deepEqual(annotationHotkey("T"), { kind: "note" });
});

test("other keys, including 0, 6 and game keys, are not annotation hotkeys", () => {
  for (const k of ["0", "6", "a", "w", " ", "Enter", "ArrowUp", "Escape", "x"]) {
    assert.equal(annotationHotkey(k), null, k);
  }
});

test("no annotation hotkey shadows a game key", () => {
  for (const k of Object.keys(KEY_TO_ACTION_ID)) assert.equal(annotationHotkey(k), null, `clash on ${k}`);
});

test("typing targets are inputs, textareas, selects and contenteditable only", () => {
  assert.equal(isTypingTarget({ tagName: "INPUT" }), true);
  assert.equal(isTypingTarget({ tagName: "textarea" }), true);
  assert.equal(isTypingTarget({ tagName: "SELECT" }), true);
  assert.equal(isTypingTarget({ tagName: "DIV", isContentEditable: true }), true);
  assert.equal(isTypingTarget({ tagName: "CANVAS" }), false);
  assert.equal(isTypingTarget(null), false);
});

test("H opens a hypothesis; Y confirms and N refutes, case-insensitively", () => {
  assert.deepEqual(annotationHotkey("h"), { kind: "hypothesis" });
  assert.deepEqual(annotationHotkey("H"), { kind: "hypothesis" });
  assert.deepEqual(annotationHotkey("y"), { kind: "verdict", verdict: "confirmed" });
  assert.deepEqual(annotationHotkey("N"), { kind: "verdict", verdict: "refuted" });
});
