<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/chienami_logo_v2_dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/images/chienami_logo_v2_light.png">
    <img src="docs/images/chienami_logo_v2_light.png" alt="Chienami logo" width="480">
  </picture>
</p>

<!-- <p align="center">
  研究室ノウハウ蓄積・段階拡張型検索/RAG基盤システム
</p> -->

## 概要

Chienamiは、研究室内の1台のデスクトップPCをサーバとして利用し、Notionのような操作感で研究室ノウハウを蓄積・整理・共有する知識基盤です。

第一段階では知識蓄積機能（Outline Wiki）だけを完成させ、文書取り込み・Semantic Search・RAG/ローカルLLM機能は後から独立して追加できる段階構成とします。研究データを外部クラウドへ送らないことを基本方針とします。

## 最も重要な考え方

Chienamiの中心はOutlineに保存された知識です。Phase 1ではOutlineだけで価値を成立させます。将来追加する文書取り込み処理、Qdrantの索引、Embedding、RAG、LLMはすべて再構築・交換可能な派生機能とし、知識資産を特定のAI技術へ依存させません。

最終形でも回答の正本はAIではなくOutline原文とし、検索結果・回答には原文タイトル・章・Outlineへのリンクを付けます。

## フェーズ構成

| Phase | 名称 | 内容 | 主な技術 |
|---|---|---|---|
| Phase 1 | Chienami Knowledge | Outline Wikiによる知識蓄積・検索・権限管理 | Outline + PostgreSQL + Redis + Reverse Proxy |
| Phase 2 | Document Import / Knowledge Circulation | 既存文書の取り込み・下書き生成 | Document Importer |
| Phase 3 | Chienami Search | Outline文書のSemantic Search | Qdrant + Qwen3-Embedding-0.6B |
| Phase 4 | Chienami AI | 出典付きRAG回答（ローカルLLM） | llama.cpp + Qwen3-Reranker-0.6B |

各Phaseは単独で利用価値を持ち、後段のAI機能が停止してもPhase 1の知識蓄積・閲覧は継続できます。

- **Phase 1**: 研究者が `knowledge.lab.local` を開き、Outlineへ実験手順・トラブル事例・会議メモなどを蓄積する。
- **Phase 2**: PDF・Word・PowerPoint・Markdown等を取り込み、Outline下書きとして生成する。研究者が確認・公開した後に検索/RAG対象へ反映する。
- **Phase 3**: 公開済み知識をIndexerで索引化し、Embedding + QdrantによるSemantic Searchを追加する。検索結果は必ず元のOutlineページへ戻れるようにする。
- **Phase 4**: Keyword Search、Reranker、ローカルLLMを追加し、RAGによる出典付き回答を提供する。根拠がない場合は回答を控える。

詳細は設計書（[docs/system_design_v1.4.md](docs/system_design_v1.4.md)）を参照してください。

## 設計方針

- **知識の正本はOutline**: 検索索引・Embedding・LLMはいつでも再構築できる派生物として扱う。
- **クローズド運用**: 外部公開はせず、研究室LANからのみReverse Proxy経由で接続する。
- **権限漏洩の防止**: Phase 3以降で検索索引を追加する際、Outline側の閲覧権限より広く検索/AI回答に文書が漏れないようにする（権限フィルタが完成するまでは全員閲覧可Collectionのみ索引対象とする）。
- **交換可能なコンポーネント**: モデルやミドルウェアは要件（日本語性能・ライセンス・GGUF提供状況など）に応じて差し替え可能とする。

## ディレクトリ構成

```
chienami/
├─ app/                  # 実行設定（Git管理）
│  ├─ reverse-proxy/     # Reverse Proxy設定
│  ├─ config/            # 各種設定ファイル
│  └─ scripts/           # 運用スクリプト（setup.sh / start.sh / stop.sh）
├─ docs/                 # 運用・設計資料
│  ├─ system_design_v1.4.md
│  ├─ design/            # 設計関連資料
│  └─ images/            # ロゴ・図版
└─ .github/              # Issue/PRテンプレート
```

## リリースブランチ

研究室サーバへの導入は、安定版ブランチ `release/v2-rag`
（Phase 1〜4: Outline知識蓄積 + Semantic Search + 出典付きRAG回答）から行います。
`main`は開発の最新状態を追跡するため、サーバ導入時は必ずリリースブランチを指定してください。

```bash
git clone -b release/v2-rag https://github.com/Mugi323/chienami.git
```

既存のサーバを `release/v1-no-rag` から切り替える場合:

```bash
git fetch origin
git switch -c release/v2-rag --track origin/release/v2-rag
```

Phase 4ではLLM・Rerankerのモデル配置などが追加で必要です。
[LLM](docs/design/llm-setup.md)・[Reranker](docs/design/reranker-setup.md)・
[RAG](docs/design/rag-setup.md) の各手順を参照してください。

Phase 1〜3のみの旧安定版（`release/v1-no-rag`）は廃止しました。その時点の状態は
タグ `v1.0.0` で参照できます。

導入手順は [docs/design/linux-server-deployment.md](docs/design/linux-server-deployment.md) を参照してください。

### リリースブランチの運用ルール

リリースブランチは「導入済みの安定版」を固定するためのブランチであり、新機能は入れません。

| 変更の種類 | 流れ |
|---|---|
| 新機能 | `feat/*` → PR → `main`（リリースブランチには入れない） |
| サーバ運用中のバグ修正 | `fix/*` → PR → `release/*` → リリースブランチを `main` にマージして戻す |
| 次の安定版 | `main` から `release/v2-<概要>` を新規作成し、本節の案内とサーバのcheckout先を切り替える |

- リリースブランチ向けの修正ブランチは、リリースブランチから作成し、PRのbaseもリリースブランチにする。
- リリースブランチで行った修正は、次のリリースで再発しないよう必ず `main` へ戻す。
- 新機能を現行の安定版へ個別に取り込む（`git cherry-pick`）のは例外扱いとし、PRで理由を明記する。
- リリース時点および修正の反映時に `v<メジャー>.<マイナー>.<パッチ>` 形式のタグを打つ（例: `v1.0.0`, `v1.0.1`）。

## 開発フロー

GitHub Flowを採用し、「1 Issue = 1変更目的 = 1 Pull Request」を原則とします。

```
Issue作成 → ブランチ作成 → 実装 → Push → Pull Request → CI → 自己レビュー → Squash merge → Issue close
```

- ブランチ名: `feat/<issue番号>-<概要>` / `fix/<issue番号>-<概要>` / `docs/<issue番号>-<概要>` / `chore/<issue番号>-<概要>`
- PR本文には `Closes #<Issue番号>`・変更内容・確認方法・確認結果を記載する。
- mainへ直接pushせず、CIが成功していることをマージ条件とする（初期はApprove必須化を見送り、自己レビューを必須とする）。

## コミット規約

| 絵文字 | プレフィックス | 用途 |
|---|---|---|
| ✨ | feat: | 新機能 |
| 🐛 | fix: | バグ修正 |
| 🔧 | chore: | 設定・環境整備 |
| 📝 | docs: | ドキュメント |
| ♻️ | refactor: | リファクタリング |
| 🔒 | security: | セキュリティ対応 |
| 🧪 | test: | テスト |

## 関連ドキュメント

- [システム設計書 v1.4](docs/system_design_v1.4.md) — アーキテクチャ、コンポーネント設計、セキュリティ、バックアップ・復旧、導入ロードマップなどの詳細
- [起動・停止スクリプトの使い方](docs/design/scripts-usage.md) — `app/scripts/` の `setup.sh` / `start.sh` / `stop.sh` の使い方
- [GPU非搭載の開発機での起動](docs/design/cpu-dev-setup.md) — `CHIENAMI_CPU=1` でCPU用overrideを重ねて起動する方法
- [Reranker基盤の動作確認](docs/design/reranker-setup.md) — llama.cpp + Qwen3-Reranker-0.6B（Phase 4）
- [RAG（/chat）の動作確認](docs/design/rag-setup.md) — 出典付き回答の仕組み・設定・GPU機での確認項目（Phase 4）
