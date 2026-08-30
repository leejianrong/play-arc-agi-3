// 0-9 match ARC-AGI's established visual convention. 10-15 are a provisional
// extension (ARC-AGI-3 uses the full 4-bit range but no authoritative
// palette for the extra 6 was found during planning — QUESTIONS.md Q17).
// Wrong values here are purely cosmetic and immediately visible.
export const PALETTE = Object.freeze([
  "#000000", // 0 black
  "#0074D9", // 1 blue
  "#FF4136", // 2 red
  "#2ECC40", // 3 green
  "#FFDC00", // 4 yellow
  "#AAAAAA", // 5 grey
  "#F012BE", // 6 magenta
  "#FF851B", // 7 orange
  "#7FDBFF", // 8 cyan
  "#870C25", // 9 maroon
  "#F5F5F5", // 10 white (provisional)
  "#39CCCC", // 11 teal (provisional)
  "#001F3F", // 12 navy (provisional)
  "#01FF70", // 13 lime (provisional)
  "#3D9970", // 14 olive (provisional)
  "#DDDDDD", // 15 silver (provisional)
]);
