<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/chienami_logo_2_dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/images/chienami_logo_2_light.png">
    <img src="docs/images/chienami_logo_2_light.png" alt="Chienami logo" width="480">
  </picture>
</p>

<p align="center">
  研究室ノウハウ蓄積・段階拡張型検索/RAG基盤システム
</p>

## 概要

Chienamiは、研究室内の1台のデスクトップPCをサーバとして利用し、Notionのような操作感で研究室ノウハウを蓄積・整理・共有する知識基盤です。

第一段階では知識蓄積機能（Outline Wiki）だけを完成させ、Semantic Search・RAG/ローカルLLM・文書取り込み機能は後から独立して追加できる段階構成とします。研究データを外部クラウドへ送らないことを基本方針とします。

## 最も重要な考え方

Chienamiの中心はOutlineに保存された知識です。Phase 1ではOutlineだけで価値を成立させます。将来追加するQdrantの索引、Embedding、RAG、LLM、文書取り込み処理はすべて再構築・交換可能な派生機能とし、知識資産を特定のAI技術へ依存させません。

最終形でも回答の正本はAIではなくOutline原文とし、検索結果・回答には原文タイトル・章・Outlineへのリンクを付けます。

## フェーズ構成

| Phase | 名称 | 内容 | 主な技術 |
|---|---|---|---|
| Phase 1 | Chienami Knowledge | Outline Wikiによる知識蓄積・検索・権限管理 | Outline + PostgreSQL + Redis + Reverse Proxy |
| Phase 2 | Chienami Search | Outline文書のSemantic Search | Qdrant + Qwen3-Embedding-0.6B |
| Phase 3 | Chienami AI | 出典付きRAG回答（ローカルLLM） | llama.cpp + Qwen3-Reranker-0.6B |
| Phase 4 | Document Import / Knowledge Circulation | 既存文書の取り込み・下書き生成 | Document Importer |

各Phaseは単独で利用価値を持ち、後段のAI機能が停止してもPhase 1の知識蓄積・閲覧は継続できます。

- **Phase 1**: 研究者が `knowledge.lab.local` を開き、Outlineへ実験手順・トラブル事例・会議メモなどを蓄積する。
- **Phase 2**: 公開済み知識をIndexerで索引化し、Embedding + QdrantによるSemantic Searchを追加する。検索結果は必ず元のOutlineページへ戻れるようにする。
- **Phase 3**: Keyword Search、Reranker、ローカルLLMを追加し、RAGによる出典付き回答を提供する。根拠がない場合は回答を控える。
- **Phase 4**: PDF・Word・PowerPoint・Markdown等を取り込み、Outline下書きとして生成する。研究者が確認・公開した後に検索/RAG対象へ反映する。

詳細は設計書（[docs/system_design_v1.4.md](docs/system_design_v1.4.md)）を参照してください。

## 設計方針

- **知識の正本はOutline**: 検索索引・Embedding・LLMはいつでも再構築できる派生物として扱う。
- **クローズド運用**: 外部公開はせず、研究室LANからのみReverse Proxy経由で接続する。
- **権限漏洩の防止**: Phase 2以降で検索索引を追加する際、Outline側の閲覧権限より広く検索/AI回答に文書が漏れないようにする（権限フィルタが完成するまでは全員閲覧可Collectionのみ索引対象とする）。
- **交換可能なコンポーネント**: モデルやミドルウェアは要件（日本語性能・ライセンス・GGUF提供状況など）に応じて差し替え可能とする。

## ディレクトリ構成

```
chienami/
├─ app/                  # 実行設定（Git管理）
│  ├─ reverse-proxy/     # Reverse Proxy設定
│  ├─ config/            # 各種設定ファイル
│  └─ scripts/           # 運用スクリプト
├─ docs/                 # 運用・設計資料
│  ├─ system_design_v1.4.md
│  ├─ design/            # 設計関連資料
│  └─ images/            # ロゴ・図版
└─ .github/              # Issue/PRテンプレート
```

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
