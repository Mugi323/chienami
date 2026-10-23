# 文書データの保存先の指定（Issue #76）

既定では、Chikenのデータはすべて Docker named volume に保存される（実体はDockerの管理領域にあり、
場所を意識せずに使える）。本番サーバでは、失うと復元できない正本データの保存先を明示し、バックアップ
対象を分かりやすくするため、`app/config/docker.env` の `CHIKEN_DATA_DIR` で保存先ディレクトリを指定できる
（`docs/system_design_v1.4.md` 4.2.1節、本番は `/srv/chiken/data` を想定）。

## 1. 対象となるデータ

`CHIKEN_DATA_DIR` を設定すると、以下の正本データだけが指定ディレクトリ配下に保存される。

| 配置先（`CHIKEN_DATA_DIR` 配下） | 内容 | 既定のnamed volume |
|---|---|---|
| `outline/postgres/` | Outlineの文書・メタデータ（PostgreSQL） | `database-data` |
| `outline/storage/` | Outlineの添付ファイル | `storage-data` |
| `authentik/postgres/` | Authentikの利用者・設定（PostgreSQL） | `authentik-database-data` |
| `authentik/data/` | Authentikのアップロードファイル等 | `authentik-data` |

検索索引（`qdrant-data`、Outlineから再構築できる）、モデルキャッシュ（`*-model-cache`、再ダウンロード
できる）、Caddyの証明書・ルートCA（`caddy-data`）は対象外で、引き続きnamed volumeに保存される。

## 2. 使い方

保存先は `app/config/docker.env` に書く。`app/scripts/` のスクリプトはこの値が設定されていれば
override `app/compose.data.yaml` を自動的に重ねる。`CHIKEN_CPU=1` と併用してよい。

```bash
# 保存先を用意する（初回のみ。/srv 配下は sudo が必要）
sudo mkdir -p /srv/chiken/data
sudo chown "$USER" /srv/chiken/data

# config/docker.env が無ければ生成する（既にあれば何もしない）
./app/scripts/setup.sh --no-up
```

`app/config/docker.env` の次の行に保存先を書き、起動する。

```bash
CHIKEN_DATA_DIR=/srv/chiken/data
```

```bash
./app/scripts/start.sh
```

- パスは絶対パスで、引用符を付けずに書く（相対パスはエラーで停止する）。空のままならnamed volumeに保存する。
- Issue #76以前に生成した `docker.env` にはこの行が無い（`setup.sh` は既存のファイルを変更しない）。
  その場合は上の1行を追記する。
- 環境変数 `CHIKEN_DATA_DIR` が設定されていれば、`docker.env` の値より優先される
  （例: 一時的に別の場所で試す `CHIKEN_DATA_DIR=/tmp/chiken-test ./app/scripts/start.sh`）。
- `start.sh`（および `setup.sh --up`）は起動前に1節のサブディレクトリを作成し、OutlineとAuthentikの
  ディレクトリの所有者をコンテナの実行ユーザー（Outline: UID 1001、Authentik: UID 1000）に設定する。
  所有者の変更は対象イメージを一時的にrootで起動して行うため、sudoは不要。PostgreSQLのディレクトリは
  PostgreSQL自身が起動時に所有者を設定する。
- スクリプトを使わずに `docker compose` を直接実行する場合は、overrideを明示的に重ね、保存先を
  環境変数で渡す（`docker compose` 自身は `docker.env` のこの値を読まない）。

  ```bash
  cd app
  CHIKEN_DATA_DIR=/srv/chiken/data docker compose -f compose.yaml -f compose.data.yaml up -d
  ```

  この場合はディレクトリ作成・所有者設定が行われないため、先に一度 `start.sh` で起動しておくこと。

## 3. 注意点

- 運用開始後に `CHIKEN_DATA_DIR` を変更・削除すると、次の `start.sh` から別の保存先
  （削除した場合はnamed volume）で起動し、Outlineが空に見える。元の保存先のデータは消えないので、
  値を戻して `start.sh` で起動し直せばよい。
- `CHIKEN_DATA_DIR` はスクリプトが読む値で、コンテナでは使わない（`docker.env` は各コンテナにも
  渡されるが、影響はない）。
- `stop.sh --reset-data` はnamed volumeのみを削除し、`CHIKEN_DATA_DIR` 配下は削除しない
  （停止後に警告を表示する）。初期化したい場合は、停止後に手動で削除する。PostgreSQLのファイルは
  コンテナ内のユーザー所有になるため、削除には `sudo` が必要になる。
- 既存のnamed volumeから指定ディレクトリへデータは自動で移行されない。運用中の環境で切り替える場合は、
  停止してから各volumeの中身をコピーする（例: `docker run --rm -v app_database-data:/from -v /srv/chiken/data/outline/postgres:/to alpine cp -a /from/. /to/`）。
  開発環境から本番環境へのデータ移行は、volumeのコピーではなく論理バックアップで行う
  （`docs/system_design_v1.4.md` 8節）。
- バックアップの取得自体はIssue #16で扱う。保存先を指定しても、同じディスク上にあるだけでは
  バックアップにはならない。
