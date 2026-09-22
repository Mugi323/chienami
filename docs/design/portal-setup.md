# Chienami ポータルの動作確認（Issue #40）

`app/portal/` に追加した静的ページ（素のHTML/CSS、JSなし）を、Caddyが
`portal.lab.local` として配信する。Outline（`knowledge.lab.local`）とChienami Search
（`search.lab.local`、Issue #36）のどちらを開くか選ぶための入口ページ。

Dockerコンテナの起動/停止操作は含まない（サーバは常時起動している前提。関連する
検討は別Issue #20を参照）。

## 前提

- Issue #26（Reverse ProxyのHTTPS化）・#36（Chienami Search UI）が導入済みであること。
- クライアント側の証明書信頼・hosts設定（`portal.lab.local` 含む）は
  [reverse-proxy-setup.md](reverse-proxy-setup.md) の手順に従うこと。
  `app/scripts/setup-client.bat` は本Issueで `portal.lab.local` のhosts追記にも対応済み。

## 1. サーバ側の起動確認

```bash
docker compose up -d --force-recreate caddy
docker compose ps caddy
```

## 2. ブラウザでの確認

1. `https://portal.lab.local/` を開く（証明書エラーが出る場合はルートCAの信頼登録を確認）。
2. 「Outline」カードをクリックし、`https://knowledge.lab.local/` へ遷移することを確認する。
3. `https://portal.lab.local/` に戻り、「Chienami Search」カードをクリックし、
   `https://search.lab.local/` へ遷移することを確認する。

## 既知の制約

- 本Issueの時点で実際のCaddy起動・ブラウザでの表示確認は未実施（開発環境にDockerが無く、
  `portal.lab.local` の名前解決・証明書配布も実サーバ前提のため）。実サーバでの動作確認が
  別途必要。
- Dockerコンテナ自体の起動/停止をGUIから行う機能は対象外（Issue #20で別途検討）。
