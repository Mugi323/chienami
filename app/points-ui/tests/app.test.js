// 実行: node --test app/points-ui/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const { formatNumber, formatUpdatedAt, describeRules, rankClass } = require("../app.js");

test("formats numbers with thousands separators", () => {
  assert.equal(formatNumber(12345), "12,345");
  assert.equal(formatNumber(undefined), "0");
});

test("formats updated_at as local month/day time", () => {
  const seconds = new Date(2026, 9, 7, 9, 5).getTime() / 1000;
  assert.equal(formatUpdatedAt(seconds), "10/7 09:05 時点");
});

test("returns empty string for invalid updated_at", () => {
  assert.equal(formatUpdatedAt(Number.NaN), "");
});

test("describes point rules", () => {
  assert.deepEqual(describeRules({ points_per_document: 10, characters_per_point: 1000 }), [
    "公開した文書1件につき 10 pt",
    "本文 1,000 文字ごとに +1 pt（文書ごとに計算）",
  ]);
});

test("adds medal class only for top three", () => {
  assert.equal(rankClass(1), "rank-1");
  assert.equal(rankClass(3), "rank-3");
  assert.equal(rankClass(4), "");
});
