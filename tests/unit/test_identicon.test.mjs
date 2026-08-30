import { test } from "node:test";
import assert from "node:assert/strict";
import { swatchGrid } from "../../frontend/identicon.js";

test("same game id always produces the same grid", () => {
  assert.deepEqual(swatchGrid("ls20"), swatchGrid("ls20"));
});

test("different game ids usually produce different grids", () => {
  assert.notDeepEqual(swatchGrid("ls20"), swatchGrid("re86"));
});

test("grid is size x size and every cell is a valid palette index", () => {
  const grid = swatchGrid("cd82", 6);
  assert.equal(grid.length, 6);
  for (const row of grid) {
    assert.equal(row.length, 6);
    for (const cell of row) {
      assert.ok(cell >= 0 && cell <= 9);
    }
  }
});

test("respects a custom size and cell count", () => {
  const grid = swatchGrid("wa30", 4, 3);
  assert.equal(grid.length, 4);
  const nonZero = grid.flat().filter((c) => c !== 0);
  assert.equal(nonZero.length, 3);
});
