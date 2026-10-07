// 実行: node --test app/search-ui/tests/*.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  splitCitations,
  parseMarkdown,
  parseInline,
  deriveTitle,
  upsertConversation,
  parseConversations,
  toAiMessage,
  buildChatHistory,
  createConversationStore,
} = require("../app.js");

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

test("parseMarkdown splits paragraphs, headings, lists and rules", () => {
  const answer = [
    "## 手順",
    "準備します[S1]。",
    "続けて確認します。",
    "",
    "- 試薬を用意する",
    "  （冷蔵庫の上段）",
    "* 器具を洗う",
    "1. 混ぜる",
    "2) 待つ",
    "---",
    "以上です。",
  ].join("\n");
  assert.deepEqual(parseMarkdown(answer), [
    { type: "heading", level: 2, text: "手順" },
    { type: "paragraph", text: "準備します[S1]。\n続けて確認します。" },
    { type: "list", ordered: false, start: 1, items: ["試薬を用意する\n（冷蔵庫の上段）", "器具を洗う"] },
    { type: "list", ordered: true, start: 1, items: ["混ぜる", "待つ"] },
    { type: "hr" },
    { type: "paragraph", text: "以上です。" },
  ]);
});

test("parseMarkdown keeps code block contents verbatim with language", () => {
  const answer = "次を実行します[S1]。\n```bash\ndocker compose up -d  # [S2]\n\n**not bold**\n```\n終わり。";
  assert.deepEqual(parseMarkdown(answer), [
    { type: "paragraph", text: "次を実行します[S1]。" },
    { type: "code", lang: "bash", text: "docker compose up -d  # [S2]\n\n**not bold**" },
    { type: "paragraph", text: "終わり。" },
  ]);
});

test("parseMarkdown handles indented, tilde, citation-suffixed and unclosed fences", () => {
  assert.deepEqual(parseMarkdown("1. 実行する\n   ```\n   ls -la\n   ```"), [
    { type: "list", ordered: true, start: 1, items: ["実行する"] },
    { type: "code", lang: "", text: "ls -la" },
  ]);
  assert.deepEqual(parseMarkdown("~~~python\nprint(1)\n~~~"), [
    { type: "code", lang: "python", text: "print(1)" },
  ]);
  assert.deepEqual(parseMarkdown("```\nmake\n``` [S1][S2]"), [
    { type: "code", lang: "", text: "make" },
    { type: "paragraph", text: "[S1][S2]" },
  ]);
  assert.deepEqual(parseMarkdown("```sh\nmake\nmake install"), [
    { type: "code", lang: "sh", text: "make\nmake install" },
  ]);
});

test("parseMarkdown returns [] for empty answer and normalizes CRLF", () => {
  assert.deepEqual(parseMarkdown(""), []);
  assert.deepEqual(parseMarkdown("a\r\nb"), [{ type: "paragraph", text: "a\nb" }]);
});

test("parseInline splits code, bold and citations", () => {
  assert.deepEqual(parseInline("`ls [S1]` で確認し、**必ず[S2]**保存します[S1]。", ["S1", "S2"]), [
    { type: "code", value: "ls [S1]" },
    { type: "text", value: " で確認し、" },
    { type: "strong", children: [{ type: "text", value: "必ず" }, { type: "cite", value: "S2" }] },
    { type: "text", value: "保存します" },
    { type: "cite", value: "S1" },
    { type: "text", value: "。" },
  ]);
});

test("parseInline leaves unmatched markers and HTML as text", () => {
  assert.deepEqual(parseInline("a * b ** c `d <b>x</b>", []), [
    { type: "text", value: "a * b ** c `d <b>x</b>" },
  ]);
  assert.deepEqual(parseInline("``a`b``", []), [{ type: "code", value: "a`b" }]);
});

test("deriveTitle collapses whitespace and truncates long questions", () => {
  assert.equal(deriveTitle("  PCRの\n  条件は？ "), "PCRの 条件は？");
  assert.equal(deriveTitle("あ".repeat(40), 30), `${"あ".repeat(30)}…`);
  assert.equal(deriveTitle("   "), "新しいチャット");
});

const conv = (id, updatedAt) => ({ id, title: id, createdAt: 0, updatedAt, messages: [] });

test("upsertConversation replaces by id and sorts by updatedAt desc", () => {
  const list = [conv("a", 3), conv("b", 2), conv("c", 1)];
  const result = upsertConversation(list, conv("c", 4));
  assert.deepEqual(
    result.map((c) => c.id),
    ["c", "a", "b"]
  );
  assert.equal(list.length, 3);
  assert.equal(list[2].updatedAt, 1, "does not mutate the input list");
});

test("upsertConversation keeps at most max conversations", () => {
  const list = [conv("a", 3), conv("b", 2), conv("c", 1)];
  assert.deepEqual(
    upsertConversation(list, conv("d", 5), 2).map((c) => c.id),
    ["d", "a"]
  );
});

test("parseConversations returns [] for broken or non-array data", () => {
  assert.deepEqual(parseConversations(null), []);
  assert.deepEqual(parseConversations("{not json"), []);
  assert.deepEqual(parseConversations('{"id":"a"}'), []);
});

test("parseConversations drops malformed entries and sorts", () => {
  const raw = JSON.stringify([conv("old", 1), { id: "x" }, null, conv("new", 2)]);
  assert.deepEqual(
    parseConversations(raw).map((c) => c.id),
    ["new", "old"]
  );
});

test("toAiMessage keeps fields needed for display and drops snippets", () => {
  const message = toAiMessage({
    answer: "58度です[S1]。",
    abstained: false,
    sources: [
      { id: "S1", document_id: "d", title: "PCR", url: "u", snippet: "x".repeat(500), score: 0.9, chunk_index: 0, cited: true },
    ],
    timings: { llm: 1000 },
  });
  assert.equal(message.role, "ai");
  assert.deepEqual(message.sources[0], { id: "S1", title: "PCR", url: "u", score: 0.9, cited: true });
  assert.deepEqual(message.timings, { llm: 1000 });
});

function fakeStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
  };
}

test("conversation store saves, loads and removes via storage", () => {
  const storage = fakeStorage();
  const store = createConversationStore(storage);
  store.save(conv("a", 1));
  store.save(conv("b", 2));
  assert.deepEqual(
    createConversationStore(storage).load().map((c) => c.id),
    ["b", "a"]
  );
  store.remove("b");
  assert.deepEqual(
    createConversationStore(storage).load().map((c) => c.id),
    ["a"]
  );
});

test("conversation store falls back to memory when storage throws", () => {
  const broken = {
    getItem: () => {
      throw new Error("denied");
    },
    setItem: () => {
      throw new Error("denied");
    },
  };
  const store = createConversationStore(broken);
  store.save(conv("a", 1));
  assert.deepEqual(
    store.load().map((c) => c.id),
    ["a"]
  );
  const memoryOnly = createConversationStore(null);
  memoryOnly.save(conv("b", 1));
  assert.equal(memoryOnly.load().length, 1);
});

test("buildChatHistory maps messages to roles and keeps the latest max", () => {
  const messages = [
    { role: "user", text: "PCRとは？" },
    { role: "ai", answer: "DNAを増やす方法です[S1]。", sources: [] },
    { role: "user", text: "温度は？" },
    { role: "ai", answer: "58度です[S1]。", sources: [] },
  ];
  assert.deepEqual(buildChatHistory(messages, 3), [
    { role: "assistant", content: "DNAを増やす方法です[S1]。" },
    { role: "user", content: "温度は？" },
    { role: "assistant", content: "58度です[S1]。" },
  ]);
  assert.equal(buildChatHistory(messages).length, 4);
});

test("buildChatHistory skips empty entries and handles missing messages", () => {
  assert.deepEqual(buildChatHistory([{ role: "user", text: "" }, { role: "ai", answer: "" }]), []);
  assert.deepEqual(buildChatHistory(undefined), []);
  assert.deepEqual(buildChatHistory([{ role: "user", text: "q" }], 0), []);
});
