(() => {
  "use strict";

  const form = document.getElementById("search-form");
  const input = document.getElementById("search-input");
  const status = document.getElementById("status");
  const resultsEl = document.getElementById("results");

  function setStatus(text, isError) {
    status.textContent = text;
    status.classList.toggle("error", Boolean(isError));
  }

  function clearResults() {
    resultsEl.innerHTML = "";
  }

  function renderResults(results) {
    clearResults();
    if (results.length === 0) {
      setStatus("一致する文書が見つかりませんでした。");
      return;
    }
    setStatus(`${results.length}件の結果`);

    for (const result of results) {
      const li = document.createElement("li");
      li.className = "result-card";

      const header = document.createElement("div");
      header.className = "result-header";

      const title = document.createElement("h2");
      title.className = "result-title";
      const titleLink = document.createElement("a");
      titleLink.href = result.url;
      titleLink.target = "_blank";
      titleLink.rel = "noopener noreferrer";
      titleLink.textContent = result.title || "(無題)";
      title.appendChild(titleLink);

      const score = document.createElement("span");
      score.className = "result-score";
      score.textContent = `score ${result.score.toFixed(3)}`;

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
      resultsEl.appendChild(li);
    }
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

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) {
      setStatus("検索キーワードを入力してください。", true);
      return;
    }
    runSearch(query);
  });
})();
