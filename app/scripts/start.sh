#!/usr/bin/env bash
# アプリの起動: 初回セットアップ(setup.sh)を確認した上で `docker compose up -d` する。
set -euo pipefail
# shellcheck source=./lib.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

usage() {
  cat <<'EOF'
使い方: start.sh [-h|--help]

config/*.env が無ければ自動生成した上で、Chienamiの全コンテナを起動します
（内部で setup.sh --no-up を呼び出します。envが既に存在する場合は即座にスキップされます）。
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

bash "$SCRIPT_DIR/setup.sh" --no-up

require_compose

log_info "起動しています: outline / postgres / redis / authentik-postgres / authentik-server / authentik-worker / caddy"
compose up -d
compose ps
check_hosts_entries
log_info "起動完了: http://knowledge.lab.local/ （認証: http://auth.lab.local/）"
