# 起動・停止スクリプトの使い方（app/scripts/）

Issue #24で追加した `app/scripts/` 配下のスクリプトにより、`app/compose.yaml` の初回セットアップから
日常的な起動・停止までをコマンド1つで行える。

前提: `docker` / `docker compose`（v2）/ `openssl` / `bash` が使えること。

## 0. ファイル構成

- `setup.sh` — `config/docker.env` / `config/authentik.env` の初回生成（シークレット・DBパスワード自動生成）
- `start.sh` — `setup.sh` を確認した上で `docker compose up -d` する（日常の起動用）
- `stop.sh` — `docker compose down` する（日常の停止用。データは保持）
- `lib.sh` — 上記3スクリプトが共有する内部ヘルパー（直接実行しない）

## 1. 初回セットアップ: `setup.sh`

```bash
./app/scripts/setup.sh
```

- `config/docker.env` / `config/authentik.env` が無ければ、対応する `*.example` からコピーし、
  `openssl rand` でシークレット・DBパスワードを生成して埋め込む。
  - OutlineのDBパスワードとAuthentikのDBパスワードは別々の値を生成する。
  - `docker.env` の `POSTGRES_PASSWORD` と `DATABASE_URL` 内のパスワードは同じ値になる。
  - `authentik.env` の `POSTGRES_PASSWORD` と `AUTHENTIK_POSTGRESQL__PASSWORD` は同じ値になる。
- **既にファイルが存在する場合は一切変更しない。** 何度実行しても安全（再実行してよい）。
- `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` は空のまま残る。Authentik管理画面でOutline用の
  Provider/Applicationを作成した後、手動で設定する（[authentik-setup.md](authentik-setup.md) 参照）。
- `/etc/hosts` に `knowledge.lab.local` / `auth.lab.local` が無い場合は警告を表示するのみで、
  自動編集は行わない（sudo権限が必要なため）。手動での追記手順は
  [reverse-proxy-setup.md](reverse-proxy-setup.md) を参照。
- 末尾で `docker compose up -d` を実行するかどうか確認される（対話端末の場合）。
  - `--up`: 確認なしで起動する
  - `--no-up`: セットアップのみ行い起動しない

## 2. 日常の起動: `start.sh`

```bash
./app/scripts/start.sh
```

内部で `setup.sh --no-up` を呼び出した後（envが既にあれば即座にスキップされる）、
`docker compose up -d` を実行し、`docker compose ps` を表示する。新規クローンでもこのコマンド
1つで起動できる。

## 3. 日常の停止: `stop.sh`

```bash
./app/scripts/stop.sh
```

`docker compose down` を実行する（`-v` は付けない。named volume＝蓄積したOutline/Authentikの
データは保持される）。

### データを完全に削除する場合（要注意・元に戻せません）

```bash
./app/scripts/stop.sh --reset-data
```

`storage-data` / `database-data` / `authentik-database-data` / `authentik-data` / `caddy-data` /
`qdrant-data` / `embedding-model-cache` の全named volumeを削除して停止する。対話端末では
`delete` という文字列の入力一致を要求する。
CI等の非対話環境から実行する場合は `--yes` を明示的に付けない限り拒否される
(`./app/scripts/stop.sh --reset-data --yes`)。

## 既知の制約

- OIDC値の設定と `/etc/hosts` の編集は引き続き手動（前者はAuthentik管理UI操作、後者はsudo権限が
  必要なため）。
- ここでのログはスクリプト実行時のタイムスタンプ付き標準出力のみ。コンテナが実行中に突然クラッシュ
  した場合の常時監視・ログ収集は対象外（`compose.yaml` 側の `restart: unless-stopped` に委ねる）。
