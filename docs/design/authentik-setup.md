# Authentikセットアップ手順（Outline OIDC連携）

Issue #21で追加したAuthentikコンテナは、起動しただけではOutlineと連携しません。
以下の手順を初回のみ手動で行う必要があります（Authentik管理UI上の操作のため、compose.yamlだけでは自動化できません）。

前提: 以下の環境変数ファイルを用意した上で `docker compose up -d` を実行し、全コンテナが起動していること。

```bash
cd app
cp config/docker.env.example config/docker.env
cp config/authentik.env.example config/authentik.env
```

`docker.env`（Outline/Outline用PostgreSQL/Redis）と `authentik.env`（Authentik/Authentik専用PostgreSQL）は別ファイルになっている。
両方とも `POSTGRES_DB` 等、公式postgresイメージが要求する同じ変数名を別の値で使う必要があるため、
1ファイルに統合すると値が衝突してしまう（Compose自体は `docker.env` を変数展開の対象として読み込まないため、
`${AUTHENTIK_PG_PASS}` のような書き方はcompose.yaml内では機能しない）。それぞれのファイルに直接、対応する値を記入すること。

## 1. Authentik初回セットアップ

1. `http://localhost:9000/` にアクセスする（初回は自動的にセットアップ画面へリダイレクトされる。`/if/flow/initial-setup/` への直接アクセスは、セッション未初期化のため拒否されることがある）。
2. 管理者（`akadmin`）のメールアドレス・パスワードを設定する。
   - メールアドレスは実在しなくてもよい（外部への送信は発生しない）。
3. 管理画面（`http://localhost:9000/if/admin/`）にログインできることを確認する。

## 2. Outline用 OIDC Provider / Application の作成

1. 管理画面 → **Applications > Providers > Create** を開く。
2. Provider種別に **OAuth2/OpenID Provider** を選択する。
3. 主要項目を以下の通り設定する。
   - **Name**: `outline`
   - **Authorization flow**: `default-provider-authorization-implicit-consent` を選択する。
     （OutlineはAuthentikと同じ研究室が運営する内部アプリのため、同意画面を挟まない
     implicit-consentが適切。外部の信頼できないアプリを連携する場合は
     explicit-consent（同意画面あり）を使う。）
   - **Client type**: `Confidential`
   - **Redirect URIs**: `http://localhost:3000/auth/oidc.callback`
     （Reverse Proxy導入(#14)後は `https://knowledge.lab.local/auth/oidc.callback` へ変更する）
   - **Scopes**: `openid`, `email`, `profile` を含める。
4. 保存後に発行される **Client ID** / **Client Secret** を控える。
5. **Applications > Applications > Create** で以下を設定する。
   - **Name**: `Outline`
   - **Slug**: `outline`
   - **Provider**: 手順3で作成したProviderを紐付ける。

## 3. Outline側の設定反映

`app/config/docker.env`（Git管理対象外）に、手順2で控えた値を設定する。

```
OIDC_CLIENT_ID=<発行されたClient ID>
OIDC_CLIENT_SECRET=<発行されたClient Secret>
```

その他の `OIDC_*` 項目は `docker.env.example` の値をそのまま使用してよい。設定後、Outlineコンテナを再起動する。

```
docker compose up -d --force-recreate outline
```

`http://localhost:3000` を開き、ログイン画面に「Authentikでログイン」ボタンが表示されることを確認する。

## 4. 招待リンクによるセルフ登録

招待制セルフ登録フロー「研究室メンバー登録」（slug: `chienami-invite-enrollment`）は、
`app/authentik/blueprints/enrollment-invite-name-password.yaml` により**自動構築済み**（Invitation → Prompt(氏名/パスワード/パスワード確認) → User write → User login）。
入力項目は氏名とパスワード（2回）のみで、メールアドレスは収集しない。ログインIDは入力された氏名をそのまま使う（重複時のみ連番を付与、`app/authentik/blueprints/enrollment-invite-name-password.yaml` 内のExpression Policyで自動生成）。

管理画面での作業は「実際に配布する招待リンクの発行」のみでよい。

1. **Directory > Invitations > Create** を開く。
2. **Flow** に「研究室メンバー登録」を選択する。
3. 有効期限（例: 学期末まで）や単一/複数回使用可否を設定して発行する。
4. 発行された招待URL（例: `http://localhost:9000/if/flow/chienami-invite-enrollment/?itoken=<token>`）を研究室内で共有する（対面・学内チャット等。メール送信は行わない）。

### 動作確認

- 招待URLを開き、氏名・パスワード（2回）のみでアカウントが作成できること。
- 作成直後にOutlineへリダイレクトされ、初回アクセス時にOutline側アカウントが自動作成されること（JITプロビジョニング）。
- 同じ氏名で2人目が登録した場合、ログインIDに連番が付与され、1人目のアカウントと衝突しないこと。
- 招待URLを使い切った後（または期限切れ後）は登録できないこと。

### Blueprintの再適用

`app/authentik/blueprints/` 配下のYAMLは、コンテナ起動時およびファイル変更検知時に自動適用される。
即座に反映させたい場合は以下でも実行できる。

```
docker exec app-authentik-server-1 ak apply_blueprint /blueprints/custom/<ファイル名>.yaml
```

## 5. Secret管理の確認

- `app/config/docker.env` と `app/config/authentik.env` がいずれもGit管理対象外（`.gitignore`）であることを確認する。
- `AUTHENTIK_SECRET_KEY` / `POSTGRES_PASSWORD`（authentik.env側） / `OIDC_CLIENT_SECRET` がリポジトリやコミット履歴に含まれていないことを確認する。
