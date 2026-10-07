(() => {
  "use strict";

  // portal.lab.local/points/ 配下に置くため相対パスで呼ぶ（Caddyが /points/api/* をAPIへ転送）。
  const API_URL = "api/points";

  function formatNumber(value) {
    return Number(value || 0).toLocaleString("ja-JP");
  }

  // APIの updated_at（UNIX秒）を「10/7 14:05 時点」の形にする。
  function formatUpdatedAt(seconds) {
    const date = new Date(seconds * 1000);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())} 時点`;
  }

  function describeRules(rules) {
    return [
      `公開した文書1件につき ${formatNumber(rules.points_per_document)} pt`,
      `本文 ${formatNumber(rules.characters_per_point)} 文字ごとに +1 pt（文書ごとに計算）`,
    ];
  }

  // 1〜3位はメダル表示用のクラスを付ける。
  function rankClass(rank) {
    return rank >= 1 && rank <= 3 ? `rank-${rank}` : "";
  }

  // Node.jsの単体テスト（app/points-ui/tests/）から純関数だけを読み込めるようにする。
  if (typeof module === "object" && module.exports) {
    module.exports = { formatNumber, formatUpdatedAt, describeRules, rankClass };
  }
  if (typeof document === "undefined") return;

  const rulesList = document.getElementById("rules-list");
  const updatedAt = document.getElementById("updated-at");
  const status = document.getElementById("status");
  const ranking = document.getElementById("ranking");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderRules(rules) {
    for (const line of describeRules(rules)) {
      rulesList.appendChild(el("li", "", line));
    }
  }

  function renderUser(user) {
    const item = el("li", ["rank-item", rankClass(user.rank)].filter(Boolean).join(" "));
    item.appendChild(el("span", "rank-badge", String(user.rank)));
    const body = el("span", "rank-body");
    body.appendChild(el("span", "rank-name", user.name || "（名前未設定）"));
    body.appendChild(
      el(
        "span",
        "rank-meta",
        `文書 ${formatNumber(user.documents)} 件 ・ ${formatNumber(user.characters)} 文字`,
      ),
    );
    item.appendChild(body);
    const points = el("span", "rank-points", formatNumber(user.points));
    points.appendChild(el("span", "rank-unit", " pt"));
    item.appendChild(points);
    return item;
  }

  async function load() {
    try {
      const resp = await fetch(API_URL);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      renderRules(body.rules);
      updatedAt.textContent = formatUpdatedAt(body.updated_at);
      if (body.users.length === 0) {
        status.textContent = "まだ公開された文書がありません。最初の1件を書いてみましょう！";
        return;
      }
      ranking.replaceChildren(...body.users.map(renderUser));
      ranking.hidden = false;
      status.hidden = true;
    } catch (error) {
      console.error(error);
      status.textContent = "ランキングを読み込めませんでした。時間をおいて再読み込みしてください。";
      status.classList.add("status-error");
    }
  }

  load();
})();
