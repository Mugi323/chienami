# 招待リンク発行ページのセットアップと動作確認（Issue #81）

新メンバー用の招待リンク（[authentik-setup.md](authentik-setup.md) 4節の招待制セルフ登録フロー）を、
Authentik管理画面を開かずに `https://portal.lab.local/invite/` から発行・一覧・削除できるようにする。
ページはAuthentikに**ログインできるメンバーなら誰でも**開ける（以前は `authentik Admins` グループに限定していた）。

## 仕組み

```
ブラウザ ──> Caddy /invite/*  ──forward_auth──> Authentik（組み込みOutpost）
                 │                                 └ 未ログイン → auth.lab.local のログイン画面
                 ├ /invite/       → app/invite-ui/（静的ページ）
                 └ /invite/api/*  → chienami-api /invitations（X-Authentik-Username 付き）
                                        └ サービスアカウント chienami-invite のトークンで
                                          Authentik の Invitation API を呼ぶ
```

- ページの保護・サービスアカウント・権限は `app/authentik/blueprints/invite-admin.yaml` で自動構築する
  （Proxy Provider `chienami-invite`、Application「招待リンク発行」、組み込みOutpostへの紐付け、
  Role `chienami-invite-manager`）。ポリシーバインディングは付けないため、ログイン済みの全員が通れる。
- `chienami-api` に持たせるトークンは **招待の作成・閲覧・削除とFlowの閲覧だけ** ができる権限で、
  管理者権限ではない。
- Caddyは全経路でクライアントが送った `X-Authentik-*` ヘッダを消し、forward_authを通過したときだけ
  Authentikが付ける。`chienami-api` はこのヘッダが無い `/invitations` へのリクエストを403にする
  （`/search/api/invitations` のような別経路からの呼び出しも拒否される）。
- Authentik上の招待の作成者はサービスアカウントになるため、実際に発行・削除したメンバーは
  `chienami-api` のログに残す（`docker compose logs api | grep 招待`）。

## 1. トークンの設定

新規に `setup.sh` で環境変数ファイルを作る場合は自動で設定されるため、この手順は不要。

既存のサーバでは、同じ値を2つのファイルへ手動で追記する。

```bash
token="$(openssl rand -hex 32)"
echo "CHIENAMI_INVITE_API_TOKEN=$token" >> app/config/docker.env
echo "CHIENAMI_INVITE_API_TOKEN=$token" >> app/config/authentik.env
```

未設定の場合もページの保護は有効で、発行操作だけが「サーバに CHIENAMI_INVITE_API_TOKEN が
設定されていません」と表示されて失敗する（`/invitations` が503を返す）。

## 2. サーバ側の反映

```bash
cd app
# トークンを読み込ませ、Blueprintを適用させる
docker compose up -d --force-recreate authentik-server authentik-worker
docker compose up -d --build --force-recreate api
# 新しいフォルダ（invite-ui）のマウントとCaddyfileの変更を反映する
docker compose up -d --force-recreate caddy
```

AuthentikはBlueprintのファイルが変わったときしか再適用しないため、トークンを後から追記した場合や
Blueprintを更新した場合は、手動で適用する（何度実行してもよい）。

```bash
docker compose exec authentik-worker ak apply_blueprint custom/invite-admin.yaml
```

Blueprintが適用されたことを確認する（`successful` になっていればよい）。

```bash
docker compose exec authentik-worker ak shell -c "
from authentik.blueprints.models import BlueprintInstance
print(BlueprintInstance.objects.get(path='custom/invite-admin.yaml').status)"
```

## 3. 動作確認

1. `https://portal.lab.local/` 下部の「招待リンクの発行」を開く。
   未ログインならAuthentikのログイン画面が出るので、ログインすると発行ページに戻る。
2. 有効期間と登録できる人数を選んで「発行する」を押し、一覧に追加されたリンクを「コピー」する。
3. 別のブラウザ（シークレットウィンドウ）でリンクを開き、氏名・パスワードで登録できることを確認する。
4. 3で登録した一般ユーザのまま `https://portal.lab.local/invite/` を開き、発行ページが使えることを確認する。
5. 発行ページで「削除」を押すと一覧から消え、そのリンクでは登録できなくなることを確認する。

## 使える人を絞り直す

Authentik管理画面 → **Applications > 招待リンク発行 > Policy / Group / User Bindings** で
グループやユーザを紐付けると、そのメンバーだけに限定できる。ただし Blueprint を再適用しても消えない
よう、限定し直す場合は `invite-admin.yaml` のポリシーバインディングの `state: absent` も外すこと。

## 単体テスト

```bash
cd app/api && python -m pytest tests/test_invitations.py tests/test_main.py
node --test app/invite-ui/tests/*.test.js
```

## 既知の制約

- 組み込みOutpostに紐付くProviderは本Blueprintの内容で上書きされる。管理画面から組み込みOutpostへ
  別のProviderを追加した場合は、`invite-admin.yaml` の `providers` にも追記すること。
- 招待の「登録できる人数」はAuthentikの仕様上「1人だけ」か「期限内なら何人でも」の2択。
- 有効期間なしの招待は発行できない（ページの選択肢は1・7・30・90日、APIは1〜365日）。
- 招待リンクを受け取った人の端末にも、証明書の信頼登録と hosts 設定が必要
  （[reverse-proxy-setup.md](reverse-proxy-setup.md)）。
