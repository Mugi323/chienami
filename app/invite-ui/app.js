(() => {
  "use strict";

  // portal.lab.local/invite/ 配下に置くため相対パスで呼ぶ（Caddyが /invite/api/* をAPIへ転送）。
  const API_URL = "api/invitations";

  const pad = (n) => String(n).padStart(2, "0");

  // APIの expires（ISO 8601）を「10/22 14:05 まで」の形にする。
  function formatExpires(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())} まで`;
  }

  // 期限までの残りを「あと3日」「あと5時間」「まもなく期限切れ」の形にする。
  function remainingLabel(iso, now = new Date()) {
    const ms = new Date(iso).getTime() - now.getTime();
    if (Number.isNaN(ms)) return "";
    const hours = Math.floor(ms / 3600000);
    if (hours >= 24) return `あと${Math.round(hours / 24)}日`;
    if (hours >= 1) return `あと${hours}時間`;
    return "まもなく期限切れ";
  }

  function describeUsage(singleUse) {
    return singleUse ? "1人だけ" : "期限内なら何人でも";
  }

  // Node.jsの単体テスト（app/invite-ui/tests/）から純関数だけを読み込めるようにする。
  if (typeof module === "object" && module.exports) {
    module.exports = { formatExpires, remainingLabel, describeUsage };
  }
  if (typeof document === "undefined") return;

  const form = document.getElementById("create-form");
  const createButton = document.getElementById("create-button");
  const createStatus = document.getElementById("create-status");
  const status = document.getElementById("status");
  const list = document.getElementById("invitations");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showError(target, message) {
    target.textContent = message;
    target.classList.add("status-error");
  }

  // APIのエラーを管理者向けの文言にする。403はログインし直しで直ることが多い。
  function errorMessage(resp, action) {
    if (resp.status === 403) return `${action}できませんでした。ページを再読み込みしてログインし直してください。`;
    if (resp.status === 503) return `${action}できませんでした。サーバに CHIKEN_INVITE_API_TOKEN が設定されていません。`;
    return `${action}できませんでした。時間をおいて再度お試しください。`;
  }

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "コピーしました";
    } catch (error) {
      console.error(error);
      button.textContent = "コピーできませんでした";
    }
    setTimeout(() => {
      button.textContent = "コピー";
    }, 2000);
  }

  async function remove(invitation, item) {
    if (!window.confirm("この招待リンクを削除しますか？削除するとリンクから登録できなくなります。")) return;
    const resp = await fetch(`${API_URL}/${encodeURIComponent(invitation.id)}`, { method: "DELETE" });
    if (!resp.ok && resp.status !== 404) {
      window.alert(errorMessage(resp, "削除"));
      return;
    }
    item.remove();
    if (list.children.length === 0) {
      list.hidden = true;
      status.hidden = false;
      status.textContent = "有効な招待リンクはありません。";
    }
  }

  function renderInvitation(invitation, highlight = false) {
    const item = el("li", highlight ? "invitation invitation-new" : "invitation");
    const meta = el("div", "invitation-meta");
    meta.appendChild(el("span", "invitation-expires", formatExpires(invitation.expires)));
    meta.appendChild(el("span", "invitation-remaining", remainingLabel(invitation.expires)));
    meta.appendChild(el("span", "invitation-usage", describeUsage(invitation.single_use)));
    item.appendChild(meta);

    const row = el("div", "invitation-row");
    const url = el("input", "invitation-url");
    url.type = "text";
    url.readOnly = true;
    url.value = invitation.url;
    url.setAttribute("aria-label", "招待リンク");
    url.addEventListener("focus", () => url.select());
    row.appendChild(url);

    const copy = el("button", "button button-small", "コピー");
    copy.type = "button";
    copy.addEventListener("click", () => copyText(invitation.url, copy));
    row.appendChild(copy);

    const del = el("button", "button button-small button-danger", "削除");
    del.type = "button";
    del.addEventListener("click", () => remove(invitation, item));
    row.appendChild(del);

    item.appendChild(row);
    return item;
  }

  async function load() {
    try {
      const resp = await fetch(API_URL);
      if (!resp.ok) {
        showError(status, errorMessage(resp, "招待リンクを読み込み"));
        return;
      }
      const body = await resp.json();
      if (body.invitations.length === 0) {
        status.textContent = "有効な招待リンクはありません。";
        return;
      }
      list.replaceChildren(...body.invitations.map((i) => renderInvitation(i)));
      list.hidden = false;
      status.hidden = true;
    } catch (error) {
      console.error(error);
      showError(status, "招待リンクを読み込めませんでした。時間をおいて再読み込みしてください。");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    createButton.disabled = true;
    createStatus.classList.remove("status-error");
    createStatus.textContent = "発行中…";
    try {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          valid_days: Number(data.get("valid_days")),
          single_use: data.get("single_use") === "true",
        }),
      });
      if (!resp.ok) {
        showError(createStatus, errorMessage(resp, "発行"));
        return;
      }
      const invitation = await resp.json();
      list.prepend(renderInvitation(invitation, true));
      list.hidden = false;
      status.hidden = true;
      createStatus.textContent = "発行しました。下の一覧からリンクをコピーして渡してください。";
    } catch (error) {
      console.error(error);
      showError(createStatus, "発行できませんでした。時間をおいて再度お試しください。");
    } finally {
      createButton.disabled = false;
    }
  });

  load();
})();
