# Reverse Proxyセットアップ手順（研究室LAN内アクセス）

Issue #14で追加したCaddyコンテナは、`knowledge.lab.local`（Outline）と `auth.lab.local`
（Authentik）宛のリクエストをそれぞれ内部のOutline/Authentikコンテナへ転送する。
ただし、これらのホスト名は実在するドメインではないため、**名前解決の設定を別途行わないと
どの端末からも `knowledge.lab.local` へアクセスできない**。

前提: `app/compose.yaml` の `caddy` サービスが起動していること（`docker compose up -d`）。

## 1. 名前解決の設定

研究室に共通DNSサーバーがまだない開発・検証段階では、アクセスする各端末の hosts ファイルに
Reverse Proxyを動かしているホストPCのIPアドレスを追記する。

```
<ホストPCのLAN内IPアドレス>  knowledge.lab.local
<ホストPCのLAN内IPアドレス>  auth.lab.local
```

- Windows: `C:\Windows\System32\drivers\etc\hosts`
- macOS/Linux: `/etc/hosts`
- ホストPC自身から動作確認する場合も、同様にホストPC自身のhostsファイルへ追記が必要
  （`127.0.0.1` ではなく、他端末からの見え方と揃えるためLAN内IPを指定することを推奨）。

将来、研究室に共通DNSサーバーを構築した場合は、hosts追記の代わりにDNSレコードとして
登録する（`docs/system_design_v1.4.md` Phase 0参照）。

## 2. ファイアウォール設定（LAN外からのアクセス遮断）

Reverse Proxyのポート80は `compose.yaml` で全インターフェースへ公開しているため、
ホストPCのファイアウォールでLAN外からのアクセスを遮断する。

```bash
# 例: ufwの場合。<LAN内サブネット>は実際の研究室LANのCIDRに置き換える。
sudo ufw allow from <LAN内サブネット> to any port 80
sudo ufw deny 80
```

（`docs/system_design_v1.4.md` 7.1節: 「ホストOSのファイアウォールでLAN内からの443のみ許可する」
の方針に準拠。Phase 1暫定ではTLS未対応のため80番で読み替える。）

## 3. 動作確認（Issue #14 完了条件）

- LAN内の別端末から `http://knowledge.lab.local/` にアクセスし、Outlineのログイン画面が
  表示されること。
- 同じ端末から `http://auth.lab.local/` にアクセスし、Authentikのログイン画面が表示される
  こと（Outlineからのログインボタン経由のリダイレクトも成功すること）。
- LAN外（例: 研究室LANに接続していない回線）から `http://<ホストPCのグローバル/WAN側IP>/`
  へアクセスできないこと。
- `docker compose down` → `docker compose up -d` 後も上記が再現すること。

## 4. 既知の制約

- TLS（HTTPS）は本Issueの対象外。研究室内CA導入後に別Issueで対応する
  （`app/config/docker.env.example` の `FORCE_HTTPS=false` を参照）。
- `knowledge.lab.local` / `auth.lab.local` の名前解決を手動（hosts）に依存しているため、
  IPアドレスが変わった場合は各端末のhostsファイルを再度更新する必要がある。
