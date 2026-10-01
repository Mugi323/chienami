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

## 3. AI回答モード（Phase 4, Issue #63）

画面上部の切り替えで「AI回答」を選ぶと、入力した質問を `POST /api/chat`（[rag-setup.md](rag-setup.md)）へ送り、
研究室の知識ベースだけを根拠にした回答を表示する。「検索」モード（既定）の挙動は従来と同じ。

- 回答本文の `S1` などのラベルは、下に並ぶ同じ番号の出典カードへのリンクになっている
- 出典カードは、回答で引用されたものは通常表示、引用されなかったものは薄く表示する（「回答で未引用」）
- 根拠が見つからず回答を控えた場合は、その旨と「通常の検索で探す →」を表示する。押すと同じ文言で検索モードの検索を行う
- AIサービス（LLM/Reranker）が停止している場合（503）は、「検索」モードを使うよう案内する
- 回答生成中は送信ボタンを無効にする（二重送信の防止）
- 回答本文は、HTMLとして解釈せずテキストとして表示する

### GPU機での確認（未実施）

- [ ] 「AI回答」で知識ベースにある内容を質問し、回答・出典カードが表示され、`S1` 等のリンクで出典カードへ移動できる
- [ ] 出典カードの「Outlineで開く →」から、該当のOutlineページを開ける
- [ ] 知識ベースにない内容を質問すると、回答を控えた表示になり、「通常の検索で探す →」で検索結果に切り替わる
- [ ] `docker compose stop llm` の状態で「AI回答」を使うと案内が表示され、「検索」モードは使える
- [ ] スマートフォン幅でも表示が崩れない

## 4. 開発機での確認方法

UIの純関数（回答中の `[Sn]` の分解）は、Node.jsの単体テストで確認できる。

```bash
node --test app/search-ui/tests/*.test.js
```

Node.jsが入っていない環境では、`uvx --from nodejs-wheel node --test app/search-ui/tests/*.test.js` でも実行できる。

## 既知の制約

- 本Issueの時点で実際のCaddy起動・ブラウザでの表示確認は未実施（開発環境にDockerが無く、
  `search.lab.local` の名前解決・証明書配布も実サーバ前提のため）。HTML/CSS/JSの構文確認
  （Node.jsによる `app.js` の構文チェック）のみ実施済み。実サーバでの動作確認が別途必要。
- キーワード補完・検索履歴・ページネーションは未実装（初期リリースの範囲外）。
