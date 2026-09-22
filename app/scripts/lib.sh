#!/usr/bin/env bash
# 共有ヘルパー。source して使う（直接実行しない）。
set -euo pipefail
(return 0 2>/dev/null) || { echo "lib.sh は source してください（直接実行できません）" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC2034  # setup.sh/start.sh/stop.sh から参照される
CONFIG_DIR="${CHIENAMI_CONFIG_DIR:-$APP_DIR/config}"
COMPOSE_FILE="$APP_DIR/compose.yaml"

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

compose() {
  docker compose -f "$COMPOSE_FILE" --project-directory "$APP_DIR" "$@"
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
  for host in knowledge.lab.local auth.lab.local search.lab.local; do
    grep -qE "^[^#]*[[:space:]]${host}([[:space:]]|\$)" /etc/hosts 2>/dev/null || missing+=("$host")
  done
  if ((${#missing[@]} > 0)); then
    log_warn "/etc/hosts に未設定のホスト名があります: ${missing[*]}"
    log_warn "sudo権限が必要なため自動追記はしません。手動で追記してください（手順: docs/design/reverse-proxy-setup.md）"
  fi
}
