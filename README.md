# Chienami

研究室ノウハウ蓄積・段階拡張型検索/RAG基盤システム

## 概要

Chienamiは、研究室内の1台のデスクトップPCをサーバとして利用し、Notionのような操作感で研究室ノウハウを蓄積・整理・共有する知識基盤です。

## フェーズ構成

| Phase | 内容 | 主な技術 |
|---|---|---|
| Phase 1 | Outline Wiki | Outline + PostgreSQL + Redis + Reverse Proxy |
| Phase 2 | 意味検索 | Qdrant + Qwen3-Embedding-0.6B |
| Phase 3 | RAG/AI回答 | llama.cpp + Qwen3-Reranker-0.6B |
| Phase 4 | 文書取り込み | Document Importer |

## ディレクトリ構成

```
chienami/
├─ app/                  # 実行設定（Git管理）
│  ├─ reverse-proxy/     # Reverse Proxy設定
│  ├─ config/            # 各種設定ファイル
│  └─ scripts/           # 運用スクリプト
├─ docs/                 # 運用・設計資料
└─ .github/              # Issue/PRテンプレート
```

## 開発フロー

GitHub Flowを採用。

```
Issue作成 → ブランチ作成 → 実装 → PR → CI → Squash merge
```

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
