// 実行: node --test app/invite-ui/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const { formatExpires, remainingLabel, describeUsage } = require("../app.js");

test("formats expires as local month/day time", () => {
  const iso = new Date(2026, 9, 22, 9, 5).toISOString();
  assert.equal(formatExpires(iso), "10/22 09:05 まで");
});

test("returns empty string for invalid expires", () => {
  assert.equal(formatExpires("invalid"), "");
  assert.equal(remainingLabel("invalid"), "");
});

test("describes remaining time in days, hours, or soon", () => {
  const now = new Date(2026, 9, 15, 12, 0);
  const later = (hours) => new Date(now.getTime() + hours * 3600000).toISOString();
  assert.equal(remainingLabel(later(24 * 7 - 0.1), now), "あと7日");
  assert.equal(remainingLabel(later(5.5), now), "あと5時間");
  assert.equal(remainingLabel(later(0.5), now), "まもなく期限切れ");
});

test("describes usage", () => {
  assert.equal(describeUsage(true), "1人だけ");
  assert.equal(describeUsage(false), "期限内なら何人でも");
});
