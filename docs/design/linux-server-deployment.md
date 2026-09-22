# Linuxサーバ導入・動作確認手順書（Issue #28）

これまでの開発・検証はWindows/WSL2環境で行ってきた。本手順書は、実際のLinuxサーバへ
Chienamiを導入し、同一LAN内のWindows PCから `https://knowledge.lab.local` へ問題なく
アクセスできることを確認するための手順をまとめたものである。

**対象読者**: サーバへの初回導入作業を行う研究室メンバー。

**本手順書のスコープ**: 動作確認できる状態までの導入に限定する。以下は対象外。

- バックアップ・復元（Issue #16、保留中）
- `/srv/chienami` への本番向けディレクトリ構成の正式運用（`docs/system_design_v1.4.md` 4.2節）
- 開発環境（WSL2）から本番環境へのデータ移行

## 0. 前提

- 対象サーバ: Ubuntu LTS系（`docs/system_design_v1.4.md` Phase 0）
- サーバは研究室LANに接続済みで、LAN内の他端末（Windows PC）から到達できること
- サーバへSSH等で管理者権限（sudo）でログインできること

## 1. サーバの固定IP確認

サーバのIPアドレスが変わるとWindows PC側のhosts設定が壊れるため、ルーターでのDHCP予約、
または静的IP設定によりサーバのLAN内IPアドレスを固定しておく。

```bash
ip -4 addr show scope global | grep inet
```

以降の手順で使う `<サーバのLAN内IP>` はここで確認した値を使う。

## 2. Docker / Docker Composeのインストール

Docker公式ドキュメントに従いインストールする（既にインストール済みの場合はスキップ）。

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

`usermod` 実行後は一度ログアウト・再ログインする（`docker`コマンドを`sudo`無しで使うため）。

```bash
docker --version
docker compose version
```

両方ともバージョンが表示されることを確認する。

## 3. リポジトリの取得

```bash
git clone git@github.com:Mugi323/chienami.git
cd chienami/app
```

## 4. 初回セットアップと起動

`app/scripts/start.sh` を実行すると、`config/docker.env` / `config/authentik.env` が
無ければ自動生成した上で全コンテナが起動する（詳細: [scripts-usage.md](scripts-usage.md)）。

```bash
./scripts/start.sh
```

- **開発環境（WSL2）の `docker.env` / `authentik.env` をコピーしてはいけない。** 本番サーバでは
  `start.sh` に新規生成させ、開発環境とは別のシークレットを使う。
- `docker compose ps` で全サービスが `healthy` または `running` になっていることを確認する。

## 5. Authentikの初期設定

[authentik-setup.md](authentik-setup.md) の手順に従い、以下を行う。

1. Authentik管理者アカウントの作成
2. Outline用OIDC Provider / Applicationの作成（Redirect URIは `https://knowledge.lab.local/auth/oidc.callback`）
3. 控えたClient ID / Client Secretを `config/docker.env` の `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` に設定
4. `docker compose up -d --force-recreate outline` でOutlineに反映

この時点ではまだ名前解決・証明書信頼ができていないため、サーバ自身のhostsファイルへ
一時的に `127.0.0.1 knowledge.lab.local` `127.0.0.1 auth.lab.local` を追記し、サーバ上の
ブラウザ（またはSSHポートフォワード経由）で確認するか、7節以降を先に行ってから戻ってくる。

## 6. ホストファイアウォール設定

LAN外からのアクセスを遮断する（詳細: [reverse-proxy-setup.md](reverse-proxy-setup.md) 2節）。

```bash
sudo ufw allow from <LAN内サブネット> to any port 80
sudo ufw allow from <LAN内サブネット> to any port 443
sudo ufw deny 80
sudo ufw deny 443
sudo ufw enable
sudo ufw status
```

`<LAN内サブネット>` は研究室LANの実際のCIDR（例: `192.168.1.0/24`）に置き換える。

## 7. サーバ再起動時の自動起動確認

`compose.yaml` の各サービスは `restart: unless-stopped` のため、Dockerデーモンが起動すれば
コンテナも自動的に復帰する。Dockerサービス自体がOS起動時に有効化されているか確認する。

```bash
sudo systemctl is-enabled docker
```

`enabled` と表示されない場合は以下で有効化する。

```bash
sudo systemctl enable docker
```

可能であればサーバを実際に再起動し、`docker compose ps` で全コンテナが自動復帰することを
確認する。

## 8. ルートCA証明書の取り出しとクライアント配布物の準備

[reverse-proxy-setup.md](reverse-proxy-setup.md) 3節の手順で証明書を取り出す。

```bash
cd ~/chienami/app
docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > chienami-root-ca.crt
```

`app/scripts/setup-client.bat` をコピーし、冒頭の `HOST_IP` を1節で確認した
`<サーバのLAN内IP>` に書き換える。

```bat
set HOST_IP=192.0.2.1
```
↓
```bat
set HOST_IP=<サーバのLAN内IP>
```

`chienami-root-ca.crt` と書き換え済みの `setup-client.bat` を同じフォルダにまとめ、
研究室内共有フォルダ等でWindows PCへ配布する。

## 9. Windows PC側のセットアップと接続確認

各Windows PCで、配布された2ファイルを同じフォルダに置き、`setup-client.bat` を
**管理者として実行**する。完了後、ブラウザを再起動して `https://knowledge.lab.local` に
アクセスし、証明書エラーなくOutlineのログイン画面が表示されることを確認する。

macOS/Linuxクライアントの場合は、[reverse-proxy-setup.md](reverse-proxy-setup.md) 3.3節の
手動手順に従う。

## 10. 動作確認チェックリスト

- [ ] `docker compose ps` で全サービスが起動していること
- [ ] サーバ再起動後もコンテナが自動復帰すること（7節）
- [ ] LAN内のWindows PCから `https://knowledge.lab.local/` に証明書エラーなくアクセスでき、
      Outlineのログイン画面が表示されること
- [ ] 「Authentikでログイン」からOIDCログインが成功し、Outlineへ入れること
- [ ] `http://knowledge.lab.local/` へアクセスした場合、自動的に `https://` へリダイレクト
      されること
- [ ] LAN外（研究室LANに接続していない回線）からサーバへアクセスできないこと
- [ ] 複数台のWindows PCで`setup-client.bat`実行→接続確認ができること

## 11. 既知の制約・今後の課題

- バックアップ・復元は未整備（Issue #16、保留中）。本手順のみでは障害時にデータを失う。
- `/srv/chienami` 配置等の本番向けディレクトリ構成は未適用。現状はリポジトリ直下・Docker
  named volumeで運用している。
- サーバのLAN内IPが変わった場合、Windows PC側のhosts設定・ルートCA信頼は影響を受けない
  （hosts側のIP更新のみで足りる）が、`caddy-data` named volumeを削除した場合はルートCAが
  再生成されるため、8〜9節の手順をやり直す必要がある。
