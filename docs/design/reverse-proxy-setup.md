# Reverse Proxyセットアップ手順（研究室LAN内アクセス）

Issue #14で追加したCaddyコンテナは、`knowledge.lab.local`（Outline）・`auth.lab.local`
（Authentik）・`search.lab.local`（Chienami Search UI, Issue #36）・`portal.lab.local`
（Outline/Search選択画面, Issue #40）宛のリクエストをそれぞれ内部のコンテナ・静的ファイルへ
転送する。ただし、これらのホスト名は実在するドメインではないため、
**名前解決の設定を別途行わないとどの端末からも `knowledge.lab.local` へアクセスできない**。

前提: `app/compose.yaml` の `caddy` サービスが起動していること（`docker compose up -d`）。

## 1. 名前解決の設定

研究室に共通DNSサーバーがまだない開発・検証段階では、アクセスする各端末の hosts ファイルに
Reverse Proxyを動かしているホストPCのIPアドレスを追記する。

```
<ホストPCのLAN内IPアドレス>  knowledge.lab.local
<ホストPCのLAN内IPアドレス>  auth.lab.local
<ホストPCのLAN内IPアドレス>  search.lab.local
<ホストPCのLAN内IPアドレス>  portal.lab.local
```

- Windows: `C:\Windows\System32\drivers\etc\hosts`
- macOS/Linux: `/etc/hosts`
- ホストPC自身から動作確認する場合も、同様にホストPC自身のhostsファイルへ追記が必要
  （`127.0.0.1` ではなく、他端末からの見え方と揃えるためLAN内IPを指定することを推奨）。

将来、研究室に共通DNSサーバーを構築した場合は、hosts追記の代わりにDNSレコードとして
登録する（`docs/system_design_v1.4.md` Phase 0参照）。

## 2. ファイアウォール設定（LAN外からのアクセス遮断）

Reverse Proxyのポート80/443は `compose.yaml` で全インターフェースへ公開しているため、
ホストPCのファイアウォールでLAN外からのアクセスを遮断する。80番はCaddyの自動HTTPS機能に
よるHTTP→HTTPSリダイレクト専用として残す（`docs/system_design_v1.4.md` 7.1節）。

```bash
# 例: ufwの場合。<LAN内サブネット>は実際の研究室LANのCIDRに置き換える。
sudo ufw allow from <LAN内サブネット> to any port 80
sudo ufw allow from <LAN内サブネット> to any port 443
sudo ufw deny 80
sudo ufw deny 443
```

## 3. HTTPS証明書の配布（ルートCA信頼登録）

CaddyはHTTPS化（Issue #26）にあたり、組み込みの内部CA（`tls internal`）でサーバ証明書を
自動発行する。`*.lab.local` は研究室内限定の名前のためLet's Encrypt等の公的CAは使えず、
代わりにこのCaddy内部CAのルート証明書を研究室メンバーの各端末へ一度だけ信頼登録して
もらう必要がある（登録しないとブラウザで証明書エラーが表示される）。

### 3.1 管理者側: ルートCA証明書の取り出し

Caddyコンテナ起動後（初回HTTPS応答時にCAが生成される）、以下でルート証明書を取り出す。

```bash
cd app
docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > chienami-root-ca.crt
```

### 3.2 配布物の作成

`chienami-root-ca.crt` と `app/scripts/setup-client.bat`（Windows向け一括セットアップ
スクリプト）をまとめて研究室内共有フォルダ等で配布する。

### 3.3 利用者側: セットアップ

Windows端末の利用者は、配布された2ファイルを同じフォルダに置き、`setup-client.bat` を
**管理者として実行**する（UACプロンプトが表示される）。これにより以下が1回の実行で
完了する。

- hostsファイルへの `knowledge.lab.local` / `auth.lab.local` / `search.lab.local` /
  `portal.lab.local` 追記（名前解決）
- ルートCA証明書の信頼登録（証明書エラーの解消）

macOS/Linuxを使う場合は、現時点では対応スクリプトを用意していないため、
[1. 名前解決](#1-名前解決)のhosts追記と、OS標準の証明書信頼登録手順
（macOS: キーチェーンアクセス、Linux: `update-ca-certificates`）を手動で行う。

## 4. 動作確認（Issue #14 / #26 完了条件）

- LAN内の別端末から `https://knowledge.lab.local/` にアクセスし、証明書エラーなく
  Outlineのログイン画面が表示されること。
- 同じ端末から `https://auth.lab.local/` にアクセスし、証明書エラーなくAuthentikの
  ログイン画面が表示されること（Outlineからのログインボタン経由のリダイレクトも
  成功すること）。
- `http://knowledge.lab.local/` へアクセスした場合、自動的に `https://` へリダイレクト
  されること。
- LAN外（例: 研究室LANに接続していない回線）から
  `http(s)://<ホストPCのグローバル/WAN側IP>/` へアクセスできないこと。
- `docker compose down` → `docker compose up -d` 後も上記が再現すること
  （`caddy-data` named volumeを削除しない限り、同じルートCA・証明書が使われ続ける）。
- 配布した `setup-client.bat` をWindows端末で実行し、hosts設定と証明書信頼の両方が
  1回の実行で完了することを確認済み。

## 5. 既知の制約

- `knowledge.lab.local` / `auth.lab.local` / `search.lab.local` / `portal.lab.local` の名前解決を手動（hosts）に依存しているため、
  IPアドレスが変わった場合は各端末のhostsファイルを再度更新する必要がある。
- `docker compose down -v` 等で `caddy-data` named volumeを削除すると、Caddyの
  ルートCA自体が再生成される。この場合は3節の手順で証明書を配り直し、全端末で
  再度信頼登録が必要になる（README/設計書の「`-v`付き停止禁止」ルールが該当）。
- クライアント向け一括セットアップスクリプトは現状Windows（`setup-client.bat`）のみ。
  macOS/Linuxは手動対応。
