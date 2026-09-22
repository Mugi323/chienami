# Chienami Search UI の動作確認（Issue #36）

`app/search-ui/` に追加した静的ファイル（素のHTML/CSS/JS、ビルド不要）を、Caddyが
`search.lab.local` として配信する。`/api/*` は同一オリジンで `chienami-api`
（Issue #34）へリバースプロキシされるため、ブラウザ側のCORS設定は不要。

## 前提

- Issue #26（Reverse ProxyのHTTPS化）・#34（chienami-api）が導入済みであること。
- クライアント側の証明書信頼・hosts設定（`search.lab.local`含む）は
  [reverse-proxy-setup.md](reverse-proxy-setup.md) の手順に従うこと。
  `app/scripts/setup-client.bat` は本Issueで `search.lab.local` のhosts追記にも対応済み。

## 1. サーバ側の起動確認

```bash
docker compose up -d --force-recreate caddy
docker compose ps caddy
```

## 2. ブラウザでの確認

1. `https://search.lab.local/` を開く（証明書エラーが出る場合はルートCAの信頼登録を確認）。
2. 検索ボックスにキーワードを入力して送信する。
3. 結果カードが表示され、タイトルリンク・「Outlineで開く →」リンクの両方から該当の
   Outlineページ（`https://knowledge.lab.local/...`）を新しいタブで開けることを確認する。
4. 該当する文書が無いキーワードで検索し、「一致する文書が見つかりませんでした。」が
   表示されることを確認する。
5. `chienami-api` を一時的に停止し（`docker compose stop api`）、検索してエラー表示
   （「検索APIに接続できませんでした」等）になることを確認した後、再起動する
   （`docker compose start api`）。

## 既知の制約

- 本Issueの時点で実際のCaddy起動・ブラウザでの表示確認は未実施（開発環境にDockerが無く、
  `search.lab.local` の名前解決・証明書配布も実サーバ前提のため）。HTML/CSS/JSの構文確認
  （Node.jsによる `app.js` の構文チェック）のみ実施済み。実サーバでの動作確認が別途必要。
- キーワード補完・検索履歴・ページネーションは未実装（初期リリースの範囲外）。
