// 実行: node --test app/search-ui/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const { splitCitations } = require("../app.js");

test("splits answer into text and known citations", () => {
  assert.deepEqual(splitCitations("58度です[S1]。確認します[S1][S2]。", ["S1", "S2"]), [
    { type: "text", value: "58度です" },
    { type: "cite", value: "S1" },
    { type: "text", value: "。確認します" },
    { type: "cite", value: "S1" },
    { type: "cite", value: "S2" },
    { type: "text", value: "。" },
  ]);
});

test("keeps unknown citation numbers as plain text", () => {
  assert.deepEqual(splitCitations("答え[S9]。", ["S1"]), [{ type: "text", value: "答え[S9]。" }]);
});

test("returns single text part when there are no citations", () => {
  assert.deepEqual(splitCitations("資料からは分かりません。", []), [
    { type: "text", value: "資料からは分かりません。" },
  ]);
});

test("handles empty answer", () => {
  assert.deepEqual(splitCitations("", ["S1"]), []);
});

test("does not treat HTML in answer specially (rendered as text nodes)", () => {
  assert.deepEqual(splitCitations("<b>x</b>[S1]", ["S1"]), [
    { type: "text", value: "<b>x</b>" },
    { type: "cite", value: "S1" },
  ]);
});
