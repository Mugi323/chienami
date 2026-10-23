#!/usr/bin/env bash
# 正本データのバックアップ: Outline・AuthentikのDBダンプと添付ファイル、config/*.env を
# CHIKEN_BACKUP_DIR 配下に日付ごとのスナップショットとして保存する。
# 前回のスナップショットから変わっていないファイルはハードリンクで共有する（rsync --link-dest）ため、
# 毎回フルコピーの見た目でも実際に増える容量は差分だけ。cronで1日1回実行する想定。
set -euo pipefail
# shellcheck source=./lib.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

usage() {
  cat <<'EOF'
使い方: backup.sh [-h|--help]

CHIKEN_BACKUP_DIR（config/docker.env または環境変数、絶対パス）配下に
YYYY-MM-DD_HHMMSS/ のスナップショットを作り、latest を最新のものへ向ける。
CHIKEN_BACKUP_KEEP（既定7）より古いスナップショットは削除する。

保存するもの:
  outline-postgres.dump / authentik-postgres.dump  pg_dump -Fc（pg_restore で復元）
  outline-storage/   Outlineの添付ファイル
  authentik-data/    Authentikのデータ
  config/            config/*.env（シークレットを含む）
検索索引（Qdrant）・モデルキャッシュ・Caddyの証明書は再生成できるため対象外。
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

require_compose
require_cmd rsync
require_cmd flock

# CHIKEN_BACKUP_DIR を決める（load_data_dir と同じく環境変数 > config/docker.env）。
if [[ -z "${CHIKEN_BACKUP_DIR:-}" && -f "$CONFIG_DIR/docker.env" ]]; then
  CHIKEN_BACKUP_DIR="$(sed -n 's/^CHIKEN_BACKUP_DIR=//p' "$CONFIG_DIR/docker.env" | tail -n 1)"
fi
[[ -n "${CHIKEN_BACKUP_DIR:-}" ]] || { log_error "CHIKEN_BACKUP_DIR が未設定です（config/docker.env に絶対パスで書いてください）"; exit 1; }
[[ "$CHIKEN_BACKUP_DIR" == /* ]] || { log_error "CHIKEN_BACKUP_DIR は絶対パスで指定してください: $CHIKEN_BACKUP_DIR"; exit 1; }
[[ -d "$CHIKEN_BACKUP_DIR" && -w "$CHIKEN_BACKUP_DIR" ]] || { log_error "バックアップ先に書き込めません: $CHIKEN_BACKUP_DIR"; exit 1; }
KEEP="${CHIKEN_BACKUP_KEEP:-7}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { log_error "CHIKEN_BACKUP_KEEP は1以上の整数で指定してください: $KEEP"; exit 1; }

# 同時実行（cronと手動の重なり等）を防ぐ。
exec 9>"$CHIKEN_BACKUP_DIR/.backup.lock"
flock -n 9 || { log_error "別のバックアップが実行中です"; exit 1; }

STAMP="$(date '+%Y-%m-%d_%H%M%S')"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

log_info "DBをダンプしています"
# 認証情報はコンテナ内の環境変数を使い、ホスト側には取り出さない。
compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$WORK/outline-postgres.dump"
compose exec -T authentik-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$WORK/authentik-postgres.dump"

log_info "添付ファイル等をコピーしています"
# copy_from_container SERVICE CONTAINER_PATH NAME: named volume / CHIKEN_DATA_DIR のどちらでも同じ手順で取り出せるよう、
# コンテナ内でtarしてホスト側で展開する（ホスト側の所有者は実行ユーザーになる）。
copy_from_container() {
  mkdir -p "$WORK/$3"
  compose exec -T "$1" tar -C "$2" -cf - . | tar -C "$WORK/$3" -xf - --no-same-owner
}
copy_from_container outline /var/lib/outline/data outline-storage
copy_from_container authentik-server /data authentik-data
mkdir -p "$WORK/config"
cp -p "$CONFIG_DIR"/*.env "$WORK/config/"
# 運用方針として、シークレット（config/*.env, DBダンプ）を含めて誰でも読めるようにする。
# rsync --link-dest は権限まで一致したファイルしか共有しないため、毎回同じ権限に揃えてから保存する。
chmod -R u+rwX,go+rX,go-w "$WORK"

log_info "保存しています: $CHIKEN_BACKUP_DIR/$STAMP"
link_dest=()
[[ -d "$CHIKEN_BACKUP_DIR/latest/" ]] && link_dest=(--link-dest="$CHIKEN_BACKUP_DIR/latest/")
# 途中で失敗したものを latest にしないよう、一時名で書いてから改名する。
rsync -a --checksum "${link_dest[@]}" "$WORK/" "$CHIKEN_BACKUP_DIR/.incomplete-$STAMP/"
mv "$CHIKEN_BACKUP_DIR/.incomplete-$STAMP" "$CHIKEN_BACKUP_DIR/$STAMP"
ln -sfn "$STAMP" "$CHIKEN_BACKUP_DIR/latest"

# 古いスナップショットを削除する（名前が日時なので名前順＝古い順）。
mapfile -t snapshots < <(find "$CHIKEN_BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9]-*' -printf '%f\n' | sort)
if ((${#snapshots[@]} > KEEP)); then
  for old in "${snapshots[@]:0:${#snapshots[@]}-KEEP}"; do
    log_info "古いスナップショットを削除します: $old"
    rm -rf -- "${CHIKEN_BACKUP_DIR:?}/$old"
  done
fi

log_info "バックアップ完了: $CHIKEN_BACKUP_DIR/$STAMP"
