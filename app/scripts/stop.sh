#!/usr/bin/env bash
# アプリの停止: 通常は named volume を保持したまま `docker compose down` する。
# データを完全に削除したい場合のみ、明示的な確認を経て --reset-data を使う。
set -euo pipefail
# shellcheck source=./lib.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

usage() {
  cat <<'EOF'
使い方: stop.sh [--reset-data [--yes]] [-h|--help]

デフォルト: `docker compose down`（named volumeは保持される。データは消えない）。

  --reset-data  全named volume（storage-data, database-data, authentik-database-data,
                authentik-data, caddy-data）を完全に削除して停止する。元に戻せません。
                対話端末では確認のため "delete" の入力を要求します。
  --yes         --reset-data と併用し、非対話環境でも確認をスキップして実行する。
  -h, --help    このヘルプを表示する
EOF
}

reset_data=false
assume_yes=false
for arg in "$@"; do
  case "$arg" in
    --reset-data) reset_data=true ;;
    -y|--yes) assume_yes=true ;;
    -h|--help) usage; exit 0 ;;
    *) log_error "不明な引数: $arg"; usage; exit 1 ;;
  esac
done

require_compose

if $reset_data; then
  log_warn "危険: --reset-data により以下のnamed volumeが完全に削除されます（元に戻せません）:"
  log_warn "  storage-data database-data authentik-database-data authentik-data caddy-data"
  if ! $assume_yes; then
    if [[ -t 0 ]]; then
      read -r -p "本当に削除しますか？ 'delete' と入力してください: " ans
      [[ "$ans" == "delete" ]] || { log_error "確認と一致しなかったため中止しました"; exit 1; }
    else
      log_error "非対話環境で --reset-data を使う場合は --yes を明示指定してください"
      exit 1
    fi
  fi
  log_info "docker compose down -v を実行します"
  compose down -v
  log_info "停止・データ削除が完了しました"
else
  log_info "docker compose down を実行します（named volumeは保持されます）"
  compose down
  log_info "停止しました"
fi
