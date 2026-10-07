(() => {
  "use strict";

  const STORAGE_KEY = "chienami.conversations.v1";
  const MAX_CONVERSATIONS = 50;
  const SNIPPET_MAX_LENGTH = 280;

  // 回答本文を、通常のテキストと出典参照（[S1] 等）に分ける。
  // sourceIdsに含まれない番号はテキストのまま残す（LLMが存在しない番号を書いた場合）。
  function splitCitations(answer, sourceIds) {
    const known = new Set(sourceIds);
    const parts = [];
    const pattern = /\[(S\d+)\]/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(answer)) !== null) {
      if (!known.has(match[1])) continue;
      if (match.index > last) {
        parts.push({ type: "text", value: answer.slice(last, match.index) });
      }
      parts.push({ type: "cite", value: match[1] });
      last = pattern.lastIndex;
    }
    if (last < answer.length) {
      parts.push({ type: "text", value: answer.slice(last) });
    }
    return parts;
  }

  // 回答本文（LLMが書くMarkdown）をブロックの配列に分ける。対応するのはLLMがよく使う記法だけ:
  // コードブロック（```/~~~）、見出し、箇条書き・番号付きリスト、区切り線、段落。
  // HTMLへは変換せず、描画側でDOMノードとして組み立てる（HTMLを解釈しないため安全）。
  function parseMarkdown(answer) {
    const lines = String(answer || "").replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let paragraph = null;
    let list = null;

    function closeOpenBlocks() {
      paragraph = null;
      list = null;
    }

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];

      const fence = line.match(/^(\s*)(`{3,}|~{3,})\s*([^\s`]*)/);
      if (fence) {
        closeOpenBlocks();
        const [, indent, marker, lang] = fence;
        const code = [];
        let after = "";
        for (i += 1; i < lines.length; i += 1) {
          // 閉じフェンスの後ろに出典（```[S1] など）が続く書き方も許す。
          const close = lines[i].match(/^\s*(`{3,}|~{3,})\s*((?:\[S\d+\]\s*)*)$/);
          if (close && close[1][0] === marker[0] && close[1].length >= marker.length) {
            after = close[2].trim();
            break;
          }
          code.push(lines[i].startsWith(indent) ? lines[i].slice(indent.length) : lines[i].trimStart());
        }
        blocks.push({ type: "code", lang, text: code.join("\n") });
        if (after) blocks.push({ type: "paragraph", text: after });
        continue;
      }

      if (!line.trim()) {
        closeOpenBlocks();
        continue;
      }

      const heading = line.match(/^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/);
      if (heading) {
        closeOpenBlocks();
        blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
        continue;
      }

      if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) {
        closeOpenBlocks();
        blocks.push({ type: "hr" });
        continue;
      }

      // 入れ子のリストは平坦にする（字下げは無視）。
      const item = line.match(/^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/);
      if (item) {
        const ordered = item[2] !== undefined;
        if (!list || list.ordered !== ordered) {
          paragraph = null;
          list = { type: "list", ordered, start: ordered ? Number(item[2]) : 1, items: [] };
          blocks.push(list);
        }
        list.items.push(item[3]);
        continue;
      }

      if (list) {
        // リスト項目の折り返し行。
        list.items[list.items.length - 1] += `\n${line.trim()}`;
        continue;
      }
      if (paragraph) {
        paragraph.text += `\n${line}`;
      } else {
        paragraph = { type: "paragraph", text: line };
        blocks.push(paragraph);
      }
    }
    return blocks;
  }

  // ブロック内の文字列を、テキスト・インラインコード・太字・出典参照に分ける。
  // インラインコードの中は記号も [S1] もそのまま表示する。太字の中では出典参照だけを解釈する。
  function parseInline(text, sourceIds) {
    const parts = [];
    const pattern = /(`+)([\s\S]+?)\1(?!`)|\*\*(?=\S)([\s\S]+?)\*\*/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > last) {
        parts.push(...splitCitations(text.slice(last, match.index), sourceIds));
      }
      if (match[1]) {
        parts.push({ type: "code", value: match[2].trim() || match[2] });
      } else {
        parts.push({ type: "strong", children: splitCitations(match[3], sourceIds) });
      }
      last = pattern.lastIndex;
    }
    if (last < text.length) {
      parts.push(...splitCitations(text.slice(last), sourceIds));
    }
    return parts;
  }

  function truncate(text, maxLength) {
    const chars = Array.from(text);
    if (chars.length <= maxLength) return text;
    return `${chars.slice(0, maxLength).join("")}…`;
  }

  // 会話のタイトル（サイドバー表示用）を最初の質問から作る。
  function deriveTitle(question, maxLength = 30) {
    const normalized = String(question || "").replace(/\s+/g, " ").trim();
    if (!normalized) return "新しいチャット";
    return truncate(normalized, maxLength);
  }

  // 会話一覧に1件を追加・置換し、更新日時の新しい順にmax件までに切り詰めた新しい配列を返す。
  function upsertConversation(list, conversation, max = MAX_CONVERSATIONS) {
    return [conversation, ...list.filter((c) => c.id !== conversation.id)]
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, max);
  }

  // localStorageの文字列を会話一覧に戻す。壊れたデータは捨てる（画面を壊さないことを優先）。
  function parseConversations(raw) {
    if (typeof raw !== "string") return [];
    let data;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      return [];
    }
    if (!Array.isArray(data)) return [];
    return data
      .filter(
        (c) =>
          c &&
          typeof c.id === "string" &&
          typeof c.title === "string" &&
          typeof c.updatedAt === "number" &&
          Array.isArray(c.messages)
      )
      .sort((a, b) => b.updatedAt - a.updatedAt);
  }

  // /chatのレスポンスを、履歴に保存するAIメッセージの形にする。
  // 出典は簡易表示で本文を使わないため、localStorageの容量節約のため本文（snippet）は保存しない。
  function toAiMessage(body) {
    return {
      role: "ai",
      answer: body.answer || "",
      abstained: Boolean(body.abstained),
      sources: (body.sources || []).map((s) => ({
        id: s.id,
        title: s.title,
        url: s.url,
        score: s.score,
        cited: Boolean(s.cited),
      })),
      timings: body.timings || null,
    };
  }

  // 会話履歴の保存先。現在はブラウザのlocalStorageだが、将来サーバ保存へ差し替えられるよう
  // load/save/removeの3操作に閉じ込めている。storageが使えない場合はメモリ上だけで動く。
  function createConversationStore(storage, key = STORAGE_KEY) {
    let memory = [];
    let useMemory = !storage;

    function load() {
      if (useMemory) return memory;
      try {
        memory = parseConversations(storage.getItem(key));
      } catch (err) {
        useMemory = true;
      }
      return memory;
    }

    function write(list) {
      memory = list;
      if (useMemory) return;
      try {
        storage.setItem(key, JSON.stringify(list));
      } catch (err) {
        useMemory = true;
      }
    }

    return {
      load,
      save(conversation) {
        const list = upsertConversation(load(), conversation);
        write(list);
        return list;
      },
      remove(id) {
        const list = load().filter((c) => c.id !== id);
        write(list);
        return list;
      },
    };
  }

  // Node.jsの単体テスト（app/search-ui/tests/）から純関数だけを読み込めるようにする。
  if (typeof module === "object" && module.exports) {
    module.exports = {
      splitCitations,
      parseMarkdown,
      parseInline,
      deriveTitle,
      upsertConversation,
      parseConversations,
      toAiMessage,
      createConversationStore,
    };
  }
  if (typeof document === "undefined") return;

  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  const menuBtn = document.getElementById("menu-btn");
  const newChatBtn = document.getElementById("new-chat-btn");
  const convList = document.getElementById("conv-list");
  const navModeLinks = document.querySelectorAll(".nav-link[data-mode]");
  const chatScroll = document.getElementById("chat-scroll");
  const thread = document.getElementById("thread");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const inputNote = document.getElementById("input-note");

  const INPUT_MAX_HEIGHT = 160;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    chat: "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z",
    search:
      "M21.71 20.29l-5.4-5.39A8 8 0 1 0 14.9 16.3l5.39 5.4a1 1 0 0 0 1.42-1.41zM4 10a6 6 0 1 1 6 6 6 6 0 0 1-6-6z",
    spark: "M12 2l2.2 6.6L21 11l-6.8 2.4L12 20l-2.2-6.6L3 11l6.8-2.4L12 2z",
    close:
      "M6.4 5L12 10.6 17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6 10.6 12 5 6.4 6.4 5z",
  };
  const MODE_TEXT = {
    ai: {
      placeholder: "研究室の知識について質問する",
      note: "研究室の知識ベースだけを根拠に回答します。回答には必ず出典を確認してください。",
      emptyTitle: "研究室の知識に質問する",
      emptyBody:
        "Outlineに蓄積された研究室の知識だけを根拠に、出典付きで回答します。Enterで送信、Shift+Enterで改行できます。",
    },
    search: {
      placeholder: "研究室の知識を検索する",
      note: "結果のタイトルから、元のOutlineページを開けます。",
      emptyTitle: "研究室の知識を検索する",
      emptyBody: "キーワードや文章を入力すると、意味の近いOutlineの文書を探します。",
    },
  };

  let storage = null;
  try {
    storage = window.localStorage;
  } catch (err) {
    storage = null;
  }
  const store = createConversationStore(storage);

  const state = {
    mode: "ai",
    conversation: null, // 表示中の会話（未保存の新しい会話も含む）
    busy: false,
    search: null, // { query, status: "loading" | "done" | "error", results, message }
  };

  // --- DOMヘルパー ---

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function icon(name, size) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", ICONS[name]);
    svg.appendChild(path);
    return svg;
  }

  function newId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function scrollToBottom() {
    chatScroll.scrollTop = chatScroll.scrollHeight;
  }

  // --- メッセージ描画 ---

  function renderEmpty() {
    const text = MODE_TEXT[state.mode];
    const wrap = el("div", "chat-empty");
    const iconWrap = el("div", "chat-empty-icon");
    iconWrap.appendChild(icon(state.mode === "ai" ? "chat" : "search", 26));
    wrap.appendChild(iconWrap);
    wrap.appendChild(el("h3", null, text.emptyTitle));
    wrap.appendChild(el("p", null, text.emptyBody));
    return wrap;
  }

  function renderUserMessage(text, animate) {
    const wrap = el("div", animate ? "msg-user" : "msg-user static");
    wrap.appendChild(el("div", "msg-user-bubble", text));
    return wrap;
  }

  function aiShell(animate, extraClass) {
    const wrap = el("div", ["msg-ai", animate ? "" : "static", extraClass || ""].join(" ").trim());
    const avatar = el("div", "ai-avatar");
    avatar.appendChild(icon("spark", 14));
    const body = el("div", "msg-ai-body");
    wrap.appendChild(avatar);
    wrap.appendChild(body);
    return { wrap, body };
  }

  function renderPending() {
    const { wrap, body } = aiShell(true);
    const typing = el("div", "typing");
    typing.setAttribute("aria-label", "回答を作成しています");
    for (let i = 0; i < 3; i += 1) typing.appendChild(el("span"));
    body.appendChild(typing);
    body.appendChild(el("span", "typing-label", "回答を作成しています…（数十秒かかることがあります）"));
    return wrap;
  }

  function renderErrorMessage(text) {
    const { wrap, body } = aiShell(true, "msg-error");
    body.appendChild(el("div", "msg-ai-text", text));
    return wrap;
  }

  function highlightCard(card) {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("highlight");
    setTimeout(() => card.classList.remove("highlight"), 1600);
  }

  // 出典カードのidは、同じ会話内の複数の回答でS番号が重ならないようメッセージ番号を含める。
  function sourceCardId(messageIndex, sourceId) {
    return `src-${messageIndex}-${sourceId}`;
  }

  function renderCite(sourceId, messageIndex) {
    const cardId = sourceCardId(messageIndex, sourceId);
    const cite = el("a", "cite", sourceId);
    cite.href = `#${cardId}`;
    cite.addEventListener("click", (event) => {
      event.preventDefault();
      const card = document.getElementById(cardId);
      if (card) highlightCard(card);
    });
    return cite;
  }

  function appendInline(parent, text, sourceIds, messageIndex) {
    for (const part of parseInline(text, sourceIds)) {
      if (part.type === "text") {
        parent.appendChild(document.createTextNode(part.value));
      } else if (part.type === "cite") {
        parent.appendChild(renderCite(part.value, messageIndex));
      } else if (part.type === "code") {
        parent.appendChild(el("code", "md-inline-code", part.value));
      } else {
        const strong = el("strong");
        for (const child of part.children) {
          strong.appendChild(
            child.type === "cite"
              ? renderCite(child.value, messageIndex)
              : document.createTextNode(child.value)
          );
        }
        parent.appendChild(strong);
      }
    }
  }

  // http（非セキュアコンテキスト）などでClipboard APIが使えない場合は、execCommandで代替する。
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = el("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    if (!ok) throw new Error("copy failed");
  }

  function renderCodeBlock(block) {
    const wrap = el("div", "md-code-block");
    const header = el("div", "md-code-header");
    header.appendChild(el("span", "md-code-lang", block.lang || "code"));

    const copyBtn = el("button", "md-code-copy", "コピー");
    copyBtn.type = "button";
    copyBtn.setAttribute("aria-label", "コードをコピー");
    let resetTimer = null;
    copyBtn.addEventListener("click", async () => {
      try {
        await copyText(block.text);
        copyBtn.textContent = "コピーしました";
      } catch (err) {
        copyBtn.textContent = "コピーできませんでした";
      }
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        copyBtn.textContent = "コピー";
      }, 1600);
    });
    header.appendChild(copyBtn);

    const pre = el("pre", "md-code");
    pre.appendChild(el("code", null, block.text));
    wrap.appendChild(header);
    wrap.appendChild(pre);
    return wrap;
  }

  // 回答中の見出しは、画面全体の見出しより目立たないようh3以下に寄せる。
  const HEADING_TAGS = ["h3", "h4", "h5", "h5", "h5", "h5"];

  function renderAnswer(answer, sourceIds, messageIndex) {
    const text = el("div", "msg-ai-text md");
    for (const block of parseMarkdown(answer)) {
      if (block.type === "code") {
        text.appendChild(renderCodeBlock(block));
      } else if (block.type === "hr") {
        text.appendChild(el("hr", "md-hr"));
      } else if (block.type === "heading") {
        const heading = el(HEADING_TAGS[block.level - 1], "md-heading");
        appendInline(heading, block.text, sourceIds, messageIndex);
        text.appendChild(heading);
      } else if (block.type === "list") {
        const list = el(block.ordered ? "ol" : "ul", "md-list");
        if (block.ordered && block.start !== 1) list.start = block.start;
        for (const item of block.items) {
          const li = el("li");
          appendInline(li, item, sourceIds, messageIndex);
          list.appendChild(li);
        }
        text.appendChild(list);
      } else {
        const p = el("p", "md-paragraph");
        appendInline(p, block.text, sourceIds, messageIndex);
        text.appendChild(p);
      }
    }
    return text;
  }

  function renderAiMessage(message, messageIndex, question, animate) {
    const { wrap, body } = aiShell(animate);
    const sources = message.sources || [];

    body.appendChild(renderAnswer(message.answer, sources.map((s) => s.id), messageIndex));

    if (message.abstained && question) {
      const fallback = el("button", "answer-fallback", "通常の検索で探す →");
      fallback.type = "button";
      fallback.addEventListener("click", () => {
        setMode("search");
        runSearch(question);
      });
      body.appendChild(fallback);
    }

    const timing = formatTimings(message.timings);
    if (timing) body.appendChild(el("div", "msg-meta", timing));

    if (sources.length > 0) {
      body.appendChild(el("div", "section-label", "出典"));
      const list = el("ul", "source-list");
      for (const source of sources) {
        list.appendChild(createSourceItem(source, sourceCardId(messageIndex, source.id)));
      }
      body.appendChild(list);
    }
    return wrap;
  }

  // 出典は1件1行（S番号・タイトル・関連度）で簡易表示する。内容はタイトルからOutlineを開いて読む。
  function createSourceItem(source, cardId) {
    const li = el("li", "source-item");
    li.id = cardId;
    li.classList.toggle("uncited", !source.cited);

    li.appendChild(el("span", "source-badge", source.id));

    const title = el("a", "source-title", source.title || "(無題)");
    title.href = source.url;
    title.target = "_blank";
    title.rel = "noopener noreferrer";
    title.title = source.title || "";
    li.appendChild(title);

    li.appendChild(
      el(
        "span",
        "result-score",
        `関連度 ${Number(source.score).toFixed(2)}${source.cited ? "" : "・未引用"}`
      )
    );
    return li;
  }

  function createResultCard(result) {
    const li = el("li", "source-card");
    const header = el("div", "result-header");

    const title = el("h4", "result-title");
    const titleLink = el("a", null, result.title || "(無題)");
    titleLink.href = result.url;
    titleLink.target = "_blank";
    titleLink.rel = "noopener noreferrer";
    title.appendChild(titleLink);

    const score = el("span", "result-score", `score ${Number(result.score).toFixed(3)}`);

    header.appendChild(title);
    header.appendChild(score);

    const snippet = el("p", "result-snippet", truncate(result.snippet || "", SNIPPET_MAX_LENGTH));

    const link = el("a", "result-link", "Outlineで開く →");
    link.href = result.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    li.appendChild(header);
    li.appendChild(snippet);
    li.appendChild(link);
    return li;
  }

  function formatTimings(timings) {
    if (!timings) return "";
    const total = Object.values(timings).reduce((sum, ms) => sum + ms, 0);
    return `回答時間 ${(total / 1000).toFixed(1)}秒`;
  }

  function renderConversation() {
    const messages = state.conversation ? state.conversation.messages : [];
    if (messages.length === 0) {
      thread.appendChild(renderEmpty());
      return;
    }
    let lastQuestion = "";
    messages.forEach((message, index) => {
      if (message.role === "user") {
        lastQuestion = message.text;
        thread.appendChild(renderUserMessage(message.text, false));
      } else {
        thread.appendChild(renderAiMessage(message, index, lastQuestion, false));
      }
    });
  }

  function renderSearch() {
    const search = state.search;
    if (!search) {
      thread.appendChild(renderEmpty());
      return;
    }
    thread.appendChild(renderUserMessage(search.query, false));

    if (search.status === "loading") {
      thread.appendChild(el("p", "search-summary", "検索しています…"));
      return;
    }
    if (search.status === "error") {
      thread.appendChild(el("p", "search-summary error", search.message));
      return;
    }
    if (search.results.length === 0) {
      thread.appendChild(el("p", "search-summary", "一致する文書が見つかりませんでした。"));
      return;
    }
    thread.appendChild(el("p", "search-summary", `${search.results.length}件の結果`));
    const list = el("ul", "results");
    for (const result of search.results) {
      list.appendChild(createResultCard(result));
    }
    thread.appendChild(list);
  }

  function renderThread() {
    thread.innerHTML = "";
    if (state.mode === "ai") {
      renderConversation();
    } else {
      renderSearch();
    }
    scrollToBottom();
  }

  // --- サイドバー ---

  function renderSidebar() {
    const conversations = store.load();
    convList.innerHTML = "";
    if (conversations.length === 0) {
      convList.appendChild(el("li", "sidebar-empty", "まだ会話はありません"));
    }
    const activeId = state.mode === "ai" && state.conversation ? state.conversation.id : null;
    for (const conversation of conversations) {
      const wrap = el("li", "conv-item-wrap");

      const item = el("button", "conv-item", conversation.title);
      item.type = "button";
      item.title = conversation.title;
      if (conversation.id === activeId) {
        item.classList.add("active");
        item.setAttribute("aria-current", "true");
      }
      item.addEventListener("click", () => openConversation(conversation.id));

      const del = el("button", "conv-delete-btn");
      del.type = "button";
      del.setAttribute("aria-label", `「${conversation.title}」を削除`);
      del.appendChild(icon("close", 14));
      del.addEventListener("click", () => deleteConversation(conversation.id));

      wrap.appendChild(item);
      wrap.appendChild(del);
      convList.appendChild(wrap);
    }

    for (const link of navModeLinks) {
      const active = link.dataset.mode === state.mode;
      link.classList.toggle("active", active);
      if (active) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    }
  }

  function openSidebar() {
    sidebar.classList.add("sidebar-open");
    overlay.hidden = false;
    menuBtn.setAttribute("aria-expanded", "true");
  }

  function closeSidebar() {
    sidebar.classList.remove("sidebar-open");
    overlay.hidden = true;
    menuBtn.setAttribute("aria-expanded", "false");
  }

  // --- 状態遷移 ---

  function setMode(mode) {
    state.mode = mode;
    input.placeholder = MODE_TEXT[mode].placeholder;
    inputNote.textContent = MODE_TEXT[mode].note;
    renderSidebar();
    renderThread();
  }

  function startNewChat() {
    state.conversation = null;
    setMode("ai");
    closeSidebar();
    input.focus();
  }

  function openConversation(id) {
    const conversation = store.load().find((c) => c.id === id);
    if (!conversation) return;
    state.conversation = conversation;
    setMode("ai");
    closeSidebar();
  }

  function deleteConversation(id) {
    store.remove(id);
    if (state.conversation && state.conversation.id === id) {
      state.conversation = null;
      if (state.mode === "ai") renderThread();
    }
    renderSidebar();
  }

  function setBusy(busy) {
    state.busy = busy;
    sendBtn.disabled = busy;
  }

  function autoResize() {
    input.style.height = "auto";
    const height = Math.min(input.scrollHeight, INPUT_MAX_HEIGHT);
    input.style.height = `${height}px`;
    input.style.overflowY = input.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }

  function clearInput() {
    input.value = "";
    autoResize();
  }

  // --- API呼び出し ---

  async function runSearch(query) {
    const search = { query, status: "loading", results: [], message: "" };
    state.search = search;
    if (state.mode === "search") renderThread();

    try {
      let response;
      try {
        response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
      } catch (err) {
        throw new Error("検索APIに接続できませんでした。しばらくしてから再度お試しください。");
      }
      if (!response.ok) {
        throw new Error(`検索に失敗しました（HTTP ${response.status}）。`);
      }
      let body;
      try {
        body = await response.json();
      } catch (err) {
        throw new Error("検索結果の解析に失敗しました。");
      }
      search.status = "done";
      search.results = body.results || [];
    } catch (err) {
      search.status = "error";
      search.message = err.message;
    }

    // 待っている間に別の検索が始まっていれば、古い結果では描画しない。
    if (state.search === search && state.mode === "search") renderThread();
  }

  async function requestChat(question) {
    let response;
    try {
      response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
    } catch (err) {
      throw new Error("AI回答APIに接続できませんでした。しばらくしてから再度お試しください。");
    }
    if (response.status === 503) {
      throw new Error("AI回答機能は現在利用できません。サイドバーの「検索」をお使いください。");
    }
    if (!response.ok) {
      throw new Error(`AI回答に失敗しました（HTTP ${response.status}）。`);
    }
    try {
      return await response.json();
    } catch (err) {
      throw new Error("AI回答の解析に失敗しました。");
    }
  }

  async function runChat(question) {
    if (!state.conversation) {
      const now = Date.now();
      state.conversation = {
        id: newId(),
        title: deriveTitle(question),
        createdAt: now,
        updatedAt: now,
        messages: [],
      };
    }
    const conversation = state.conversation;
    const userMessage = { role: "user", text: question };
    conversation.messages.push(userMessage);

    const empty = thread.querySelector(".chat-empty");
    if (empty) empty.remove();
    thread.appendChild(renderUserMessage(question, true));
    const pending = renderPending();
    thread.appendChild(pending);
    scrollToBottom();
    setBusy(true);

    try {
      const body = await requestChat(question);
      const message = toAiMessage(body);
      const index = conversation.messages.length;
      conversation.messages.push(message);
      conversation.updatedAt = Date.now();
      store.save(conversation);

      if (pending.isConnected) {
        pending.replaceWith(renderAiMessage(message, index, question, true));
        scrollToBottom();
      } else if (state.mode === "ai" && state.conversation === conversation) {
        renderThread();
      }
    } catch (err) {
      // 失敗した質問は履歴に残さない（表示上は残し、入力欄へ戻して再送しやすくする）。
      const at = conversation.messages.lastIndexOf(userMessage);
      if (at !== -1) conversation.messages.splice(at, 1);
      if (pending.isConnected) {
        pending.replaceWith(renderErrorMessage(err.message));
        scrollToBottom();
      }
      if (!input.value) {
        input.value = question;
        autoResize();
      }
    } finally {
      setBusy(false);
      renderSidebar();
    }
  }

  // --- イベント ---

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (state.busy) return;
    const query = input.value.trim();
    if (!query) {
      input.focus();
      return;
    }
    clearInput();
    if (state.mode === "ai") {
      runChat(query);
    } else {
      runSearch(query);
    }
  });

  input.addEventListener("input", autoResize);
  input.addEventListener("keydown", (event) => {
    // IME変換確定のEnterでは送信しない。
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) {
      return;
    }
    event.preventDefault();
    form.requestSubmit();
  });

  newChatBtn.addEventListener("click", startNewChat);
  for (const link of navModeLinks) {
    link.addEventListener("click", () => {
      setMode(link.dataset.mode);
      closeSidebar();
      input.focus();
    });
  }

  menuBtn.addEventListener("click", () => {
    if (sidebar.classList.contains("sidebar-open")) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });
  overlay.addEventListener("click", closeSidebar);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });

  setMode("ai");
  autoResize();
})();
