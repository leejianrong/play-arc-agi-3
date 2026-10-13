// Annotation hotkeys (ADR-0008, Q32). Pure, so tests/unit/hotkeys.test.mjs covers it. None of these
// collide with the game keys in input_mapping.js (arrows, WASD, space, Enter, Backspace, R).

export const PHASES = ["observe", "probe", "plan", "execute", "reflect"];

const PHASE_BY_KEY = Object.freeze({ 1: "observe", 2: "probe", 3: "plan", 4: "execute", 5: "reflect" });

export function annotationHotkey(key) {
  if (Object.prototype.hasOwnProperty.call(PHASE_BY_KEY, key)) {
    return { kind: "phase", phase: PHASE_BY_KEY[key] };
  }
  if (key === "m" || key === "M") return { kind: "mute" };
  if (key === "t" || key === "T") return { kind: "note" };
  if (key === "h" || key === "H") return { kind: "hypothesis" }; // focus the add-hypothesis box
  if (key === "v" || key === "V") return { kind: "dictate" }; // voice: every sentence becomes one
  if (key === "y" || key === "Y") return { kind: "verdict", verdict: "confirmed" };
  if (key === "n" || key === "N") return { kind: "verdict", verdict: "refuted" };
  return null;
}

// True when keystrokes belong to a text field, so neither game nor annotation hotkeys may fire.
export function isTypingTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true;
}
