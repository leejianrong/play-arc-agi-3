// A deterministic per-game swatch: a sparse scatter of ARC-palette cells,
// not a real preview of the puzzle (that would mean downloading every
// game's source just to look at its list entry). The visual material is
// the same one ARC-AGI puzzles are made of -- colored grid cells -- so a
// generated swatch still looks native to the subject.

const GRID_SIZE = 6;
const CELL_COUNT = 5;

function hash32(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Returns a size x size grid of palette indices (0 = background); the same
// gameId always produces the same grid.
export function swatchGrid(gameId, size = GRID_SIZE, cellCount = CELL_COUNT) {
  const rand = mulberry32(hash32(gameId));
  const grid = Array.from({ length: size }, () => Array(size).fill(0));
  for (let i = 0; i < cellCount; i++) {
    const x = Math.floor(rand() * size);
    const y = Math.floor(rand() * size);
    grid[y][x] = 1 + Math.floor(rand() * 9); // skip 0 (background/black)
  }
  return grid;
}
