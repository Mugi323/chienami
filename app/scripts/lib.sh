#!/usr/bin/env bash
# 共有ヘルパー。source して使う（直接実行しない）。
set -euo pipefail
(return 0 2>/dev/null) || { echo "lib.sh は source してください（直接実行できません）" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC2034  # setup.sh/start.sh/stop.sh から参照される
CONFIG_DIR="${CHIENAMI_CONFIG_DIR:-$APP_DIR/config}"
COMPOSE_FILE="$APP_DIR/compose.yaml"
# GPU非搭載の開発機では CHIENAMI_CPU=1 でCPU用overrideを重ねる（Issue #55, docs/design/cpu-dev-setup.md）。
COMPOSE_CPU_FILE="$APP_DIR/compose.cpu.yaml"
# CHIENAMI_DATA_DIR（config/docker.env または環境変数）を設定すると、正本データの保存先を
# そのディレクトリへ切り替えるoverrideを重ねる（Issue #76, docs/design/data-dir-setup.md）。
COMPOSE_DATA_FILE="$APP_DIR/compose.data.yaml"

log()       { printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "$2"; }
log_info()  { log "INFO"  "$1"; }
log_warn()  { log "WARN"  "$1" >&2; }
log_error() { log "ERROR" "$1" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log_error "コマンドが見つかりません: $1"; exit 1; }
}

require_compose() {
  require_cmd docker
  docker compose version >/dev/null 2>&1 || { log_error "docker compose (v2) が見つかりません"; exit 1; }
}

# CHIENAMI_DATA_DIR を決める。環境変数が設定されていればそれを優先し、無ければ config/docker.env の値を使う。
# compose.data.yaml の ${CHIENAMI_DATA_DIR} 展開に使うため export する。
load_data_dir() {
  if [[ -z "${CHIENAMI_DATA_DIR:-}" && -f "$CONFIG_DIR/docker.env" ]]; then
    CHIENAMI_DATA_DIR="$(sed -n 's/^CHIENAMI_DATA_DIR=//p' "$CONFIG_DIR/docker.env" | tail -n 1)"
  fi
  export CHIENAMI_DATA_DIR="${CHIENAMI_DATA_DIR:-}"
}

compose() {
  load_data_dir
  local files=(-f "$COMPOSE_FILE")
  if [[ "${CHIENAMI_CPU:-}" == "1" ]]; then
    files+=(-f "$COMPOSE_CPU_FILE")
  fi
  if [[ -n "${CHIENAMI_DATA_DIR:-}" ]]; then
    [[ "$CHIENAMI_DATA_DIR" == /* ]] || { log_error "CHIENAMI_DATA_DIR は絶対パスで指定してください: $CHIENAMI_DATA_DIR"; exit 1; }
    files+=(-f "$COMPOSE_DATA_FILE")
  fi
  docker compose "${files[@]}" --project-directory "$APP_DIR" "$@"
}

# CHIENAMI_DATA_DIR 配下に正本データ用のディレクトリを作り、コンテナの実行ユーザーが書き込めるよう
# 所有者を設定する（起動前に呼ぶ）。PostgreSQLは起動時に自分で所有者を直すため作成のみ行う。
prepare_data_dir() {
  load_data_dir
  [[ -n "${CHIENAMI_DATA_DIR:-}" ]] || return 0
  local dir
  for dir in outline/storage outline/postgres authentik/postgres authentik/data; do
    if ! mkdir -p "$CHIENAMI_DATA_DIR/$dir" 2>/dev/null; then
      log_error "データディレクトリを作成できません: $CHIENAMI_DATA_DIR/$dir"
      log_error "書き込み権限を付与してから再実行してください: sudo mkdir -p \"$CHIENAMI_DATA_DIR\" && sudo chown \"\$USER\" \"$CHIENAMI_DATA_DIR\""
      exit 1
    fi
  done
  # UIDは各イメージの実行ユーザー（outline:1.10.0はnodejs=1001、authentik 2026.8.1はauthentik=1000）。
  chown_data_dir outline /var/lib/outline/data "$CHIENAMI_DATA_DIR/outline/storage" 1001
  chown_data_dir authentik-server /data "$CHIENAMI_DATA_DIR/authentik/data" 1000
  log_info "正本データの保存先: $CHIENAMI_DATA_DIR"
}

# chown_data_dir SERVICE CONTAINER_PATH HOST_DIR UID: HOST_DIRの所有者がUIDでなければ、
# sudoを使わずに済むよう対象サービスのイメージをrootで一時起動してchownする。
chown_data_dir() {
  local service="$1" path="$2" host_dir="$3" uid="$4"
  [[ "$(stat -c %u "$host_dir")" == "$uid" ]] && return 0
  log_info "所有者を設定します: $host_dir -> $uid:$uid"
  compose run --rm --no-deps --user root --entrypoint chown "$service" -R "$uid:$uid" "$path"
}

# sedの置換文字列に含まれる \ & | を無害化する（区切り文字|との衝突・&の特殊展開を防ぐ）。
sed_escape_repl() {
  printf '%s' "$1" | sed -e 's/[\&|]/\\&/g'
}

# inject_kv FILE KEY VALUE: "KEY=..." で始まる行をまるごと "KEY=VALUE" に置換する。
inject_kv() {
  local file="$1" key="$2" value="$3" escaped
  escaped="$(sed_escape_repl "$value")"
  sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
}

check_hosts_entries() {
  local host missing=()
  for host in knowledge.lab.local auth.lab.local portal.lab.local; do
    grep -qE "^[^#]*[[:space:]]${host}([[:space:]]|\$)" /etc/hosts 2>/dev/null || missing+=("$host")
  done
  if ((${#missing[@]} > 0)); then
    log_warn "/etc/hosts に未設定のホスト名があります: ${missing[*]}"
    log_warn "sudo権限が必要なため自動追記はしません。手動で追記してください（手順: docs/design/reverse-proxy-setup.md）"
  fi
}
