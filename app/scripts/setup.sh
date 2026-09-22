#!/usr/bin/env bash
# 初回セットアップ: config/*.env の生成とシークレット埋め込み（Issue #24）。
# 既存の config/docker.env / config/authentik.env には一切触れないため、何度実行しても安全。
set -euo pipefail
# shellcheck source=./lib.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

usage() {
  cat <<'EOF'
使い方: setup.sh [--up|--no-up] [-h|--help]

config/docker.env・config/authentik.env が無ければ *.example からコピーし、
シークレット・DBパスワードを自動生成して埋め込みます。既に存在するファイルは変更しません。

  --up      セットアップ後、確認なしで `docker compose up -d` を実行する
  --no-up   セットアップのみ行い、起動はしない（確認プロンプトも出さない）
  -h, --help  このヘルプを表示する

引数を省略した場合、対話端末であれば起動するか確認します。
EOF
}

docker_env_partial=""
authentik_env_partial=""
cleanup_on_failure() {
  local ec=$?
  if [[ $ec -ne 0 ]]; then
    [[ -n "$docker_env_partial" && -f "$docker_env_partial" ]] && {
      rm -f "$docker_env_partial"
      log_warn "生成途中のファイルを削除しました: $docker_env_partial"
    }
    [[ -n "$authentik_env_partial" && -f "$authentik_env_partial" ]] && {
      rm -f "$authentik_env_partial"
      log_warn "生成途中のファイルを削除しました: $authentik_env_partial"
    }
  fi
  exit "$ec"
}
trap cleanup_on_failure EXIT

bootstrap_docker_env() {
  local target="$CONFIG_DIR/docker.env" example="$CONFIG_DIR/docker.env.example"
  if [[ -f "$target" ]]; then
    log_info "既存のためスキップ: $target"
    return
  fi
  [[ -f "$example" ]] || { log_error "テンプレートが見つかりません: $example"; exit 1; }

  cp "$example" "$target"
  docker_env_partial="$target"

  local outline_db_pw secret_key utils_secret qdrant_api_key llama_api_key
  outline_db_pw="$(openssl rand -hex 32)"
  secret_key="$(openssl rand -hex 32)"
  utils_secret="$(openssl rand -hex 32)"
  qdrant_api_key="$(openssl rand -hex 32)"
  llama_api_key="$(openssl rand -hex 32)"

  inject_kv "$target" SECRET_KEY "$secret_key"
  inject_kv "$target" UTILS_SECRET "$utils_secret"
  inject_kv "$target" POSTGRES_PASSWORD "$outline_db_pw"
  # DATABASE_URLは同じ$outline_db_pwから再構築するため、POSTGRES_PASSWORDとズレる余地がない。
  inject_kv "$target" DATABASE_URL "postgres://outline:${outline_db_pw}@postgres:5432/outline"
  # QdrantサーバとクライアントQDRANT__SERVICE__API_KEY / QDRANT_API_KEYを同一値にするため、
  # ズレないよう1回の生成から両方へ注入する（Issue #30）。
  inject_kv "$target" QDRANT__SERVICE__API_KEY "$qdrant_api_key"
  inject_kv "$target" QDRANT_API_KEY "$qdrant_api_key"
  inject_kv "$target" LLAMA_API_KEY "$llama_api_key"

  docker_env_partial=""
  log_info "作成しました: $target"
  log_info "OIDC_CLIENT_ID / OIDC_CLIENT_SECRET は未設定です。Authentik側でProvider作成後、docs/design/authentik-setup.md の手順に従って手動設定してください。"
}

bootstrap_authentik_env() {
  local target="$CONFIG_DIR/authentik.env" example="$CONFIG_DIR/authentik.env.example"
  if [[ -f "$target" ]]; then
    log_info "既存のためスキップ: $target"
    return
  fi
  [[ -f "$example" ]] || { log_error "テンプレートが見つかりません: $example"; exit 1; }

  cp "$example" "$target"
  authentik_env_partial="$target"

  local authentik_db_pw authentik_secret_key
  authentik_db_pw="$(openssl rand -hex 32)"
  authentik_secret_key="$(openssl rand -base64 60 | tr -d '\n')"

  inject_kv "$target" POSTGRES_PASSWORD "$authentik_db_pw"
  inject_kv "$target" AUTHENTIK_POSTGRESQL__PASSWORD "$authentik_db_pw"
  inject_kv "$target" AUTHENTIK_SECRET_KEY "$authentik_secret_key"

  authentik_env_partial=""
  log_info "作成しました: $target"
}

main() {
  local mode="prompt"
  case "${1:-}" in
    -h|--help) usage; trap - EXIT; exit 0 ;;
    --up) mode="up" ;;
    --no-up) mode="no-up" ;;
    "") mode="prompt" ;;
    *) log_error "不明な引数: $1"; usage; exit 1 ;;
  esac

  require_cmd openssl

  bootstrap_docker_env
  bootstrap_authentik_env
  check_hosts_entries

  local run_up=false
  case "$mode" in
    up) run_up=true ;;
    no-up) run_up=false ;;
    prompt)
      if [[ -t 0 ]]; then
        read -r -p "docker compose up -d を今すぐ実行しますか？ [y/N]: " ans
        [[ "$ans" =~ ^[Yy]$ ]] && run_up=true
      fi
      ;;
  esac

  if $run_up; then
    require_compose
    log_info "docker compose up -d を実行します"
    compose up -d
    log_info "起動完了。docker compose ps で状態を確認してください"
  fi
}

main "$@"
