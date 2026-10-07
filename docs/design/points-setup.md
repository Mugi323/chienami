# 貢献ポイントのセットアップと動作確認（Issue #77）

Outlineの文書充実に貢献したユーザへポイントを付与し、ランキングとして可視化する。
`chienami-api` の `GET /points` がOutlineから集計し、静的ページ `app/points-ui/` を
Caddyが `points.lab.local` として配信する（`/api/*` は `chienami-api` へプロキシ）。

景品交換ページは本Issueの対象外（ユーザ認証の方式を含めてIssue #88で扱う）。

## ポイントの付け方

| 項目 | 既定値 | 環境変数 |
|---|---|---|
| 公開文書1件あたりの基本点 | 10 pt | `POINTS_PER_DOCUMENT` |
| 文字量点（この文字数ごとに +1 pt） | 100 文字 | `POINTS_CHARACTERS_PER_POINT` |
| ランキングのキャッシュ時間 | 300 秒 | `POINTS_CACHE_SECONDS` |

- 対象は indexer と同じ **全員閲覧可Collectionの公開済み文書**（下書き・アーカイブ・削除済みは除く）。
  招待制Collectionの文書タイトル・作成者がランキング経由で漏れないようにするため
  （design書7.3節）。
- ポイントは文書の **作成者**（Outlineの `createdBy`）に付く。他人の文書を編集してもポイントは付かない。
- 文字量点は文書ごとに切り捨てる（短い文書に分割しても文字量点が増えないようにするため）。
- ポイントはOutlineから毎回再計算する派生値で、専用DBは持たない。文書を削除・非公開にすると
  その分のポイントも減る。

## 前提

- `config/docker.env` に `OUTLINE_API_TOKEN` が設定済みであること（indexerと共用,
  [indexer-setup.md](indexer-setup.md)）。未設定の場合、`/points` のみ503を返し、検索・RAGは動作し続ける。
- クライアント側の証明書信頼・hosts設定（`points.lab.local` 含む）は
  [reverse-proxy-setup.md](reverse-proxy-setup.md) の手順に従うこと。
  `app/scripts/setup-client.bat` は本Issueで `points.lab.local` のhosts追記にも対応済み。

## 1. サーバ側の起動

```bash
docker compose up -d --build api
docker compose up -d --force-recreate caddy
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/points').read().decode())"
```

## 2. ブラウザでの確認

1. `https://portal.lab.local/` を開き、「Chienami Points」カードから `https://points.lab.local/` へ遷移する。
2. ポイントの付け方・ランキング（順位・名前・文書数・文字数・ポイント）が表示されることを確認する。
3. Outlineで全員閲覧可Collectionに文書を公開し、キャッシュ時間経過後に再読み込みすると
   ポイントが増えることを確認する。

## 単体テスト

```bash
cd app/api && python -m pytest tests/test_points.py tests/test_main.py
node --test app/points-ui/tests/*.test.js
```

## 既知の制約

- ランキングは全員閲覧可能（ログイン不要）。ユーザの表示名はOutlineの名前をそのまま使う。
- 編集による貢献（他人の文書の加筆）は評価しない。
- 景品交換ページ（交換時の本人確認・交換履歴の保存）は未実装（Issue #88）。
