(() => {
  "use strict";

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

  // Node.jsの単体テスト（app/search-ui/tests/）から純関数だけを読み込めるようにする。
  if (typeof module === "object" && module.exports) {
    module.exports = { splitCitations };
  }
  if (typeof document === "undefined") return;

  const form = document.getElementById("search-form");
  const input = document.getElementById("search-input");
  const status = document.getElementById("status");
  const resultsEl = document.getElementById("results");
  const modeNote = document.getElementById("mode-note");
  const answerEl = document.getElementById("answer");
  const answerText = document.getElementById("answer-text");
  const answerFallback = document.getElementById("answer-fallback");
  const sourcesHeading = document.getElementById("sources-heading");
  const modeInputs = document.querySelectorAll('input[name="mode"]');

  const PLACEHOLDERS = {
    search: "研究室の知識を検索する",
    ai: "研究室の知識について質問する",
  };

  function currentMode() {
    const checked = document.querySelector('input[name="mode"]:checked');
    return checked ? checked.value : "search";
  }

  function setMode(mode) {
    for (const el of modeInputs) {
      el.checked = el.value === mode;
    }
    input.placeholder = PLACEHOLDERS[mode];
    modeNote.hidden = mode !== "ai";
  }

  function setStatus(text, isError) {
    status.textContent = text;
    status.classList.toggle("error", Boolean(isError));
  }

  function clearResults() {
    resultsEl.innerHTML = "";
    answerEl.hidden = true;
    answerText.textContent = "";
    answerFallback.hidden = true;
    sourcesHeading.hidden = true;
  }

  // 検索結果・出典で共通のカード。sourceを渡すと出典用の表示（S番号・引用有無）になる。
  function createResultCard(result, source) {
    const li = document.createElement("li");
    li.className = "result-card";

    const header = document.createElement("div");
    header.className = "result-header";

    const title = document.createElement("h2");
    title.className = "result-title";
    if (source) {
      li.id = `source-${source.id}`;
      li.classList.toggle("uncited", !source.cited);
      const badge = document.createElement("span");
      badge.className = "source-badge";
      badge.textContent = source.id;
      title.appendChild(badge);
    }
    const titleLink = document.createElement("a");
    titleLink.href = result.url;
    titleLink.target = "_blank";
    titleLink.rel = "noopener noreferrer";
    titleLink.textContent = result.title || "(無題)";
    title.appendChild(titleLink);

    const score = document.createElement("span");
    score.className = "result-score";
    score.textContent = source
      ? `関連度 ${result.score.toFixed(2)}${source.cited ? "" : "・回答で未引用"}`
      : `score ${result.score.toFixed(3)}`;

    header.appendChild(title);
    header.appendChild(score);

    const snippet = document.createElement("p");
    snippet.className = "result-snippet";
    snippet.textContent = truncate(result.snippet || "", 280);

    const link = document.createElement("a");
    link.className = "result-link";
    link.href = result.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Outlineで開く →";

    li.appendChild(header);
    li.appendChild(snippet);
    li.appendChild(link);
    return li;
  }

  function renderResults(results) {
    clearResults();
    if (results.length === 0) {
      setStatus("一致する文書が見つかりませんでした。");
      return;
    }
    setStatus(`${results.length}件の結果`);

    for (const result of results) {
      resultsEl.appendChild(createResultCard(result));
    }
  }

  function renderAnswer(body) {
    clearResults();
    const sources = body.sources || [];
    answerEl.hidden = false;
    answerEl.classList.toggle("abstained", Boolean(body.abstained));

    const parts = splitCitations(
      body.answer || "",
      sources.map((s) => s.id)
    );
    for (const part of parts) {
      if (part.type === "text") {
        answerText.appendChild(document.createTextNode(part.value));
      } else {
        const cite = document.createElement("a");
        cite.className = "cite";
        cite.href = `#source-${part.value}`;
        cite.textContent = part.value;
        answerText.appendChild(cite);
      }
    }

    answerFallback.hidden = !body.abstained;
    setStatus(formatTimings(body.timings));

    if (sources.length > 0) {
      sourcesHeading.hidden = false;
      for (const source of sources) {
        resultsEl.appendChild(createResultCard(source, source));
      }
    }
  }

  function formatTimings(timings) {
    if (!timings) return "";
    const total = Object.values(timings).reduce((sum, ms) => sum + ms, 0);
    return `回答時間 ${(total / 1000).toFixed(1)}秒`;
  }

  function truncate(text, maxLength) {
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength)}…`;
  }

  async function runSearch(query) {
    clearResults();
    setStatus("検索しています…");

    let response;
    try {
      response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    } catch (err) {
      setStatus("検索APIに接続できませんでした。しばらくしてから再度お試しください。", true);
      return;
    }

    if (!response.ok) {
      setStatus(`検索に失敗しました（HTTP ${response.status}）。`, true);
      return;
    }

    let body;
    try {
      body = await response.json();
    } catch (err) {
      setStatus("検索結果の解析に失敗しました。", true);
      return;
    }

    renderResults(body.results || []);
  }

  async function runChat(question) {
    clearResults();
    setStatus("回答を作成しています…（数十秒かかることがあります）");
    form.classList.add("busy");

    try {
      let response;
      try {
        response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
      } catch (err) {
        setStatus("AI回答APIに接続できませんでした。しばらくしてから再度お試しください。", true);
        return;
      }

      if (response.status === 503) {
        setStatus("AI回答機能は現在利用できません。「検索」モードをお使いください。", true);
        return;
      }
      if (!response.ok) {
        setStatus(`AI回答に失敗しました（HTTP ${response.status}）。`, true);
        return;
      }

      let body;
      try {
        body = await response.json();
      } catch (err) {
        setStatus("AI回答の解析に失敗しました。", true);
        return;
      }

      renderAnswer(body);
    } finally {
      form.classList.remove("busy");
    }
  }

  for (const el of modeInputs) {
    el.addEventListener("change", () => {
      setMode(currentMode());
      input.focus();
    });
  }

  answerFallback.addEventListener("click", () => {
    setMode("search");
    const query = input.value.trim();
    if (query) runSearch(query);
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (form.classList.contains("busy")) return;
    const query = input.value.trim();
    if (!query) {
      setStatus(
        currentMode() === "ai" ? "質問を入力してください。" : "検索キーワードを入力してください。",
        true
      );
      return;
    }
    if (currentMode() === "ai") {
      runChat(query);
    } else {
      runSearch(query);
    }
  });

  setMode(currentMode());
})();
