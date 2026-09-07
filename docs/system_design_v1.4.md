**Chienami****研究室ノウハウ蓄積・段階拡張型検索/RAG基盤****システム設計書**
Outlineを知識の正本とする、研究室内オンプレミス知識基盤
版: 1.4更新日: 2026年9月5日想定読者: 研究室メンバー / システム管理担当 / 開発担当 / 将来の検索・RAG実装担当
v1.4変更点: Chienami開発をGitHub Flowで進める方針を追加。Issue作成 → 作業ブランチ → commit/push → Pull Request → GitHub Actionsによるテスト → 差分確認 → Squash merge → Issue close を標準フローとする。初期の一人開発では承認（Approve）必須化を見送り、CI成功をマージ条件とする。将来の複数人開発時にレビュー承認を追加する。


# 1. この設計書で作るもの

Chienamiは、研究室内の1台のデスクトップPCをサーバとして利用し、Notionのような操作感で研究室ノウハウを蓄積・整理・共有する知識基盤です。第一段階では知識蓄積機能だけを完成させ、文書取り込み、Semantic Search、RAG/ローカルLLM機能は後から独立して追加できる段階構成とします。研究データを外部クラウドへ送らないことを基本方針とします。

## 最も重要な考え方

Chienamiの中心はOutlineに保存された知識です。Phase 1ではOutlineだけで価値を成立させます。将来追加する文書取り込み処理、Qdrantの索引、Embedding、RAG、LLMはすべて再構築・交換可能な派生機能とし、知識資産を特定のAI技術へ依存させません。

## 段階導入の利用イメージ

Phase 1（Chienami Knowledge）: 研究者が knowledge.lab.local を開き、Outlineへ実験手順・トラブル事例・会議メモなどを蓄積する。通常検索・権限管理・履歴・添付・バックアップまでを完成させる。
Phase 2（Document Import / Knowledge Circulation）: PDF、Word、PowerPoint、Markdown等を取り込み、Outline下書きとして生成する。研究者が確認・公開した後に検索/RAG対象へ反映する。
Phase 3（Chienami Search）: Outlineの公開済み知識をIndexerで索引化し、Embedding + QdrantによるSemantic Searchを追加する。検索結果は必ず元のOutlineページへ戻れるようにする。
Phase 4（Chienami AI）: Keyword Search、Reranker、ローカルLLMを追加し、RAGによる出典付き回答を提供する。根拠がない場合は回答を控える。
各Phaseは単独で利用価値を持たせ、後段のAI機能が停止してもPhase 1の知識蓄積・閲覧は継続できる。
最終形でも回答の正本はAIではなくOutline原文とし、検索結果・回答には原文タイトル・章・Outlineへのリンクを付ける。

## 本設計の想定規模




# 2. 将来構成を理解する4つの役割



## RAGとは何か

RAG（Retrieval-Augmented Generation）は、LLMに研究室の全知識を再学習させる方法ではありません。質問のたびに関連資料を検索し、その資料をLLMへ渡して回答させる方式です。したがって、ノウハウを更新してもLLM自体の再学習は不要です。

## この方式が研究室に向く理由

新しい実験知見を追加した直後から検索対象にできる。
LLMを別モデルへ変更しても、Outlineの知識をそのまま利用できる。
回答と原文を照合できるため、研究用途で重要な検証可能性を確保しやすい。
未公開データを研究室LAN内に保持したまま運用できる。

# 3. 全体システム構成


## 論理構成

**↓**
**↓**

下図は将来の最終構成です。Phase 1では Reverse Proxy + Outline + PostgreSQL + Redis + 添付ファイル保存領域だけを同じデスクトップPC上で動作させます。Phase 2以降で文書取り込み・検索・AI系コンテナを追加します。外部公開はせず、研究室LANからのみReverse Proxyへ接続できるようにします。

## 推奨コンテナ構成


# 4. 各コンポーネントの設計


## 4.1 Outline: ノウハウの正本

研究者が直接触る中心アプリケーションです。文書の本文、階層構造、更新履歴、Collection単位の権限をOutline側で管理します。Outline公式ドキュメントではDockerが推奨され、PostgreSQLとRedisが必要です。また、セルフホスト時は認証プロバイダが必要です。


### 推奨Collection例


## 4.2 PostgreSQL / Redis / 添付ファイル

PostgreSQLはOutlineの文書・メタデータの最重要保存先。毎日バックアップする。
RedisはOutlineの動作に必要だが、原則として永続知識の正本ではない。
添付ファイルはOutlineのローカルファイルストレージを利用し、ホスト側ボリュームへ永続化する。
OutlineのSECRET_KEYは紛失すると暗号化データ・セッション等に影響するため、パスワード管理基盤またはオフライン保管を行う。

### 4.2.1 データ保存先の基本方針

コンテナ本体は交換可能な実行環境とし、知識データは必ずコンテナ外の永続領域へ保存します。開発環境ではDocker named volumeを使って簡単に管理し、本番Linuxでは保存場所とバックアップ対象を明示できる構成にします。PostgreSQLと添付ファイルがChienami Phase 1の中心的な永続データです。

### 開発環境（Windows + WSL2 + Docker Desktop）

開発中のPostgreSQL・Redis等はDocker named volumeへ保存します。実体はDocker Desktopが管理するWSL2内部領域にあり、通常はそのファイルを直接編集・コピーしません。ソースコードは ~/projects/chienami のようなWSL側Linuxファイルシステムに置きます。
**重要: docker compose down ではnamed volumeは通常保持されますが、docker compose down -v はvolumeを削除します。Chienamiの通常運用では -v を付けた停止を禁止し、データ初期化時だけ明示的に使用します。**

### 本番環境（Linuxデスクトップ）

本番では /srv/chienami をChienami専用のルートとし、実行設定・稼働データ・モデル・バックアップを分離します。PostgreSQLの実ファイルは稼働用であり、バックアップは原則として pg_dump / pg_restore を用います。
保存の優先順位は「PostgreSQL + 添付/原本 > 検索索引 > AIモデル」です。検索索引とAIモデルは再生成・再取得可能ですが、Outlineの正本と原本ファイルは失うと復元できません。

## 4.3 Qdrant: 検索用インデックス（Phase 3以降）

Qdrantには「原文そのものの正本」を置くのではなく、検索用チャンクとEmbedding、検索に必要なmetadataを保存します。索引は全削除してもOutlineから再構築できる設計にします。
Qdrantのセルフホスト版は既定では認証・暗号化が有効ではないため、外部へ直接公開しません。本設計ではDocker内部ネットワークに閉じ、APIキーを設定します。

## 4.4 Embedding / Reranker（Phase 3 / Phase 4）

Embeddingは文章を「意味の近さ」で検索するための数値表現へ変換します。日本語・英語が混在する研究室を想定し、Phase 3の初期標準候補を Qwen/Qwen3-Embedding-0.6B とします。0.6B規模で、1024次元のEmbedding、32K context、多言語（100+言語）に対応しており、1台構成で扱いやすい候補です。Phase 4のReranker候補は Qwen/Qwen3-Reranker-0.6B とします。

最終モデルは研究室の実文書で評価して決定します。特に日本語、英語、数式、コード、装置名・モデル名の混在条件でRecallを比較します。

## 4.5 llama.cpp / Local LLM

Phase 4でLLMをllama.cppのHTTPサーバとして追加し、Chienami APIからのみアクセスします。llama.cppはOpenAI互換HTTP APIを提供し、GGUFモデルをローカル推論できます。GPU VRAMに応じて量子化モデルを選定します。Phase 1/2/3ではLLMは必須ではありません。

モデル名は更新が速いため、設計書では固定せず「日本語性能・指示追従・長文コンテキスト・商用/研究利用条件・GGUF提供状況」で選定します。

## 4.6 Document Importer（Phase 2 / 将来）

将来、既存のPDF・Word・PowerPoint・Markdown/TXT等をChienamiへ取り込むための独立サービスを追加します。Importerはファイルから本文とmetadataを抽出し、元ファイルを添付したOutline下書きを作成します。自動で検索DBへ直接登録せず、研究者の確認・公開後に通常のIndexer経由で検索/RAG対象へ反映します。これによりOutlineを知識の正本として維持します。

# 5. 検索・RAG処理フロー（Phase 3 / 4）


## 5.1 Semantic Search用索引作成フロー（Phase 3）

**↓**
**↓**
**↓**
**↓**
**↓**
差分更新の判定には document_id + updated_at + content_hash を使用します。変更がない文書は再Embeddingしません。これにより処理時間を抑えます。

## 5.2 検索・回答フロー（Phase 3 / 4）

**↓**
**↓**
**↓**
**↓**
**↓**
**↓**
Phase 3は検索結果を返した時点で終了し、LLMを使用しません。Phase 4ではLLMに「根拠にない内容を断定しない」「不明な場合は不明と答える」「各主張の根拠をSource IDで示す」というsystem promptを設定します。

## 5.3 Chunking方針



# 6. ノウハウを「貯める」運用設計

技術よりも重要なのが、研究者が無理なく書ける運用です。文書を細かく分類しすぎず、最低限のテンプレートを用意します。

## 推奨テンプレート: Troubleshooting


## 推奨テンプレート: 実験プロトコル


## 将来の文書取り込み機能（Phase 2）

既存資料を再入力する負担を減らすため、将来はファイル取り込み画面を追加します。取り込み後の本文は必ずOutlineの下書きとして確認できるようにし、原本ファイル・出典・取り込み日時・content hashを保持します。スキャンPDFや画像のOCRは誤認識リスクがあるため、通常のテキスト抽出とは分けて後から追加します。
取り込みフロー: ファイル選択 → 本文抽出 → metadata / 重複確認 → Outline下書き生成 → 人間レビュー → 公開 → Phase 3/4のIndexerが索引更新

## AIによるノウハウ追加支援（Phase 2 / 将来）

Phase 2では、短いメモをAIに渡して上記テンプレートのOutline下書きを生成する機能も追加できます。AIが自動公開するのではなく、研究者による確認・修正・公開を必須にします。

# 7. アクセス制御とセキュリティ


## 7.1 ネットワーク境界

ホストOSのファイアウォールでLAN内からの443のみ許可する。
Qdrant、PostgreSQL、Redis、llama.cppのポートをホストへpublishしない。
Reverse ProxyでHTTPSを必須にする。研究室内CAまたは組織CAを利用する。
管理用SSHは研究室管理端末または管理VLANからのみ許可する。

## 7.2 ユーザー認証

OutlineはOIDC対応の認証プロバイダを利用します。大学/研究機関のOIDCが利用可能なら第一候補とし、利用できない場合のみローカルKeycloak/Authentikを追加します。AI画面も同じ認証基盤を利用し、可能なら同じユーザーIDをRAG APIへ渡します。

## 7.3 検索・RAG追加時に最も注意する点: 権限漏洩

Phase 1ではOutline自身の権限管理だけを使用します。Phase 3以降、別の検索索引を持つと「Outlineでは見えない文書が検索結果やAI回答から見える」危険が生じます。そのため、権限連携が完成するまでは研究室全員が閲覧できるCollectionだけを索引対象にし、制限付きCollectionを扱う場合はユーザー単位のアクセスフィルタを必須とします。


## 7.4 Secret管理

Outline SECRET_KEY、OIDC client secret、Qdrant API keyをGitへcommitしない。
.envは権限600とし、バックアップ時も暗号化する。
可能ならDocker secretsまたは組織のsecret managerへ移行する。
Indexer用Outline APIキーはscopeと有効期限を絞る。

# 8. バックアップ・復旧設計


## 優先順位



## 保存場所とバックアップ先は別物

/srv/chienami/data は「現在サービスが使用している稼働データ」です。同じサーバ内の /srv/chienami/backup は復旧用ファイルの一時保管先として使えますが、同一SSDが故障すると同時に失われます。したがって、最終バックアップは必ず別NAS・別HDD等の物理的に別の媒体へコピーします。

## 推奨バックアップルール

PostgreSQL: 毎日pg_dump。7日分 + 週次4世代程度から開始。
添付ファイル: 毎日差分バックアップ。
Qdrant: 週次snapshot、または必要時に再index。
保存先: サーバ本体とは別のNAS/HDD。可能ならさらに別媒体へ月次コピー。
四半期ごとに「実際に復元できるか」をテストする。

## 復旧の考え方

1) Outline PostgreSQL・添付ファイル・secretを復元し、Wikiを先に復旧する。
2) Phase 1のOutlineが正常に復旧したことを確認する。Phase 3/4を導入済みの場合のみIndexer・Chienami APIを起動する。
3) Phase 3以降でQdrantが失われていれば、Outline全件から再indexする。
4) Phase 4を導入済みの場合のみLLMモデルを復元または再配置する。
5) Phase 3/4を導入済みの場合のみ代表質問セットで検索結果と出典リンクを確認する。

## 開発環境から本番Linuxへのデータ移行

Windows/WSL2上のDocker volumeの内部ファイルをそのまま本番Linuxへコピーする方式は採用しません。開発環境と本番環境は別データとして扱い、本番は原則クリーンに初期化します。開発中に作成した有効な知識を移す必要がある場合だけ、論理バックアップとファイルコピーで移行します。
1) 開発側Outlineへの書き込みを一時停止し、PostgreSQLを pg_dump で取得する。
2) Outline添付ファイルと、必要に応じてPhase 2の原本文書をアーカイブする。
3) 本番LinuxへPostgreSQLを pg_restore し、添付ファイルを所定の保存先へ配置する。
4) DB内の暗号化データに必要なSECRET_KEY等を移行する場合は、対象secretだけを安全な経路で移す。.envを丸ごとコピーしない。
5) URL、OIDC、TLS証明書等の本番固有設定を適用し、文書・添付・権限を確認する。
6) Phase 3以降はQdrantを原則として新しい本番環境で再indexし、開発索引をコピーしない。

# 9. ハードウェア設計

Phase 1のOutline中心構成は比較的軽量で、GPUは不要です。Phase 3のEmbeddingもCPUで運用可能です。Phase 4のローカルLLMはGPUがあると応答速度が大きく改善しますが、24GB級GPUを必須要件にはしません。小型の量子化LLMなら8〜12GB VRAMから開始でき、予算に応じて16GB以上へ拡張します。同じPCを将来拡張する場合は、GPU搭載余地・電源容量・RAMスロット・NVMe増設余地を確保します。


## Phase 1 初期推奨

Phase 1だけなら高性能GPUや大規模CPUは不要です。Phase 4も最初は8〜12GB級GPUまたはCPU推論で小さく始め、実際の利用状況を見て増強できます。将来より大きなLLMや複数同時利用が必要になった場合に備え、GPU交換が可能なケース、電源、冷却、RAM増設余地を確保しておく方針とします。

# 10. 将来API仕様（Phase 3 / 4）

Phase 1では独自Chienami APIは必須ではなく、Outlineだけで運用します。以下はPhase 3の検索UIとPhase 4のAI画面から利用する将来のAPI境界です。UIを変更しても検索/RAG本体とのインターフェースを維持できるようにします。


## Phase 4 chatリクエスト例


## Phase 4 chatレスポンス例


# 11. ログ・監視・品質評価


## Phaseごとに最低限保存するログ

Phase 1: Reverse Proxy / Outline / PostgreSQL / Redisの起動・停止・異常終了、バックアップ結果
Phase 3: Indexerの成功/失敗、対象document_id、処理時間、最終index時刻
Phase 3/4: 検索時間・取得件数、Phase 4ではrerank時間・LLM生成時間
エラー内容。ただし質問本文や機密文書本文を無条件にログへ残さない。
資源監視: ディスク、RAM、PostgreSQL容量。Phase 3以降はQdrant、Phase 4ではGPU VRAMも追加

## Phase 3 / 4 検索・RAG評価セット

導入前に研究室の実データから20〜50問程度の「正解が分かっている質問」を作ります。LLMの文章の上手さではなく、必要な根拠文書を取得できたかを優先評価します。


# 12. 導入ロードマップ


## Phase 0: 開発基盤・サーバ準備

Ubuntu LTS系・Dockerを準備する。Phase 1ではNVIDIA GPU/driverは必須ではない。
固定IPまたはDHCP予約
研究室DNSまたはhostsで *.lab.local 相当の名前解決
バックアップ先を準備
GitHub repositoryを作成し、Issue template、Pull Request template、GitHub Actionsの最小CIを用意する。
default branchをmainとし、mainへ直接pushしない運用を開始する。利用プランで可能ならbranch protection / rulesetでPull RequestとCI成功を必須化する。初期はApprove必須を設定しない。

## Phase 1: Chienami Knowledge（最初にここまで）

Reverse Proxy + Outline + PostgreSQL + Redis + 添付ファイル保存領域を構築
OIDC等のログイン、Collection権限、研究室共通Collectionを設定
Troubleshooting / Protocol等の文書テンプレートとタグ運用を決める
通常の全文検索、更新履歴、添付、リンク機能を研究室メンバーで試験する
PostgreSQL・添付・設定/secretのバックアップと復元手順を完成させる
この段階ではQdrant、Embedding、LLM、RAGを導入しない
PostgreSQL・添付ファイルの保存先を永続化し、docker compose down / ホスト再起動後もデータが残ることを確認する。開発環境ではnamed volume、本番では /srv/chienami/data 以下の配置方針を採用する。

## Phase 2: Document Import / Knowledge Circulation（将来拡張）

PDF、Word、PowerPoint、Markdown/TXTの取り込みサービスを追加する。
抽出本文・原本ファイル・出典metadata・content hashからOutline下書きを作成し、人間レビュー後に公開する。
重複文書・更新版をcontent hash等で検出し、同じ資料の無制限な重複登録を防ぐ。
スキャンPDF/画像はOCRを別機能として追加し、OCR結果は要レビューとして扱う。
AIによるノウハウ下書き、Git/GitHub・実験ログ・会議録連携、知識の古さ/重複検出へ拡張する。

## Phase 3: Chienami Search（Semantic Search）

Outline API → chienami-indexer → Qdrantを追加する
Qwen3-Embedding-0.6Bを初期候補としてSemantic Searchを実装する
検索結果から必ず元のOutlineページを開けるUI/APIを用意する
初期は全員閲覧可Collectionだけを索引し、制限付き文書を扱う前に権限フィルタを完成させる
実文書から検索評価セットを作り、Recall@k等でEmbedding/Chunkingを評価する

## Phase 4: Chienami AI（RAG / Local LLM）

BM25等のKeyword Searchを追加し、Vector SearchとHybrid化する
Qwen3-Reranker-0.6B等のRerankerを追加する
llama.cpp + Local LLM + chienami-apiを追加し、検索根拠から出典付き回答を生成する
ユーザー権限を検索Filterへ反映し、閲覧不可文書がAI回答へ混入しないことを試験する
根拠がない場合のabstention、citation correctness、latencyを評価する

# 13. 開発プロセス（GitHub Flow）

Chienamiの開発そのものをGitHubを用いた開発手法の習得機会とする。個人開発の初期段階でもmainへ直接変更を積み上げず、IssueとPull Requestを中心とした小規模チーム開発と同じ流れを採用する。mainは常に「テスト済みで、必要なら本番へ展開できる状態」を目標とする。

## 13.1 基本ルール

原則として「1 Issue = 1変更目的 = 1 Pull Request」とし、変更範囲を小さく保つ。
作業開始前にIssueを作成し、目的・作業内容・完了条件（Acceptance Criteria）を記載する。
最新のmainからIssue専用ブランチを作成し、main上では直接開発しない。
ブランチ名は feat/<issue番号>-<概要>、fix/<issue番号>-<概要>、docs/<issue番号>-<概要>、chore/<issue番号>-<概要> を基本とする。
commitは意味のある単位で作成し、例として feat: add PostgreSQL service、fix: correct healthcheck のように変更意図が分かるメッセージを使用する。
実装後はリモートへpushし、mainをbaseとするPull Requestを作成する。PR本文には変更内容、確認方法、確認結果、関連Issueを記載する。
PR本文に Closes #<Issue番号> を記載し、mainへのマージ時に対応Issueが自動的に閉じる運用を基本とする。

## 13.2 Pull Requestと自動テスト

Pull Requestを作成したらGitHub ActionsでCIを実行し、機械的に確認できる項目はマージ前に自動検証する。初期のPhase 1では次の軽量な検査から開始し、実装の成長に合わせてテストを追加する。
docker compose config によるCompose設定の妥当性確認。
YAML / Markdown等のlint。
scripts/配下を追加した後はShellCheck等によるシェルスクリプト検査。
Phase 2以降でPythonコードを追加した後はruff等のlint、型チェック、pytestを追加する。
統合テストが必要になった段階では、テスト用コンテナを起動してhealth checkやAPIテストを追加する。
利用中のGitHubプランでbranch protection / rulesetが利用可能な場合は、mainへのPull RequestとCI status check成功をマージ条件として強制する。機能が利用できない場合も、同じ手順を開発ルールとして手動で遵守する。

## 13.3 初期のレビュー・承認方針

初期は一人での開発学習を想定するため、Pull Requestの「Approveを1件以上必須」とする設定は行わない。ただし、PR画面でFiles changedを確認し、CIがすべて成功してからマージする自己レビューを必須とする。将来、研究室メンバーが開発へ参加した段階で「最低1名の承認」「未解決conversationがないこと」等をmainの保護ルールへ追加する。

## 13.4 mainへのマージ方針


## 13.5 Issue / PRの最小記載項目

Issueには「目的 / 作業内容 / 完了条件」を記載する。Pull Requestには「Closes #Issue番号 / 変更内容 / テスト・確認方法 / 確認結果」を記載する。テンプレートは.github/ISSUE_TEMPLATE/および.github/pull_request_template.mdとしてGit管理する。

# 14. Phase 1 完了条件（受入試験）



# 15. 採用・非採用の判断



# 16. リスクと対策



# 17. 研究者向けの使い方（Phase 1）


## ノウハウを書くとき

1) Outlineを開く。
2) 該当Collectionを選ぶ。
3) 「何が起きた / 何をした / どうなった」を書く。
4) 装置名・バージョン・実験IDなど、後から検索に使いそうな語を省略しない。
5) 関連ページやGit commitがあればリンクする。

## 将来の検索・AI機能（Phase 3 / 4）

1) Phase 3導入後はChienami Searchから意味検索できる。
2) 検索条件を具体的にする（例: Project-A、A100、FlashAttentionなど）。
3) 検索結果またはAI回答だけでなくSourcesからOutline原文を開く。
4) 重要な判断では必ず原文を確認する。
5) 不足している知識があれば、正しいノウハウをOutlineへ追記して知識を改善する。

# 18. 実装時の推奨ディレクトリ構成

.github/ISSUE_TEMPLATE/（Issueテンプレート）
.github/pull_request_template.md（PRテンプレート）
.github/workflows/ci.yml（Phase 1の最小CI）
main保護ルール / ruleset設定手順（利用プランで利用可能な場合）
compose.yamlには具体的なバージョン番号を固定します。特にOutline公式ドキュメントでもlatestタグではなくバージョン固定が推奨されています。

# 19. 公式情報・設計根拠

**[1] Outline Docker: **    Dockerが推奨。PostgreSQL/Redisを含むCompose例、バージョン固定の推奨。
**[2] Outline Requirements: **    Unix系OS、PostgreSQL 14+、Redis 4+、認証プロバイダが必要。
**[3] Outline API: **    RPC形式API、Bearer API key、OpenAPI仕様。
**[4] Outline API Guide: **    API keyのscopeと有効期限を制限可能。
**[5] Outline OIDC: **    OIDC互換IdPをサポート。Keycloak/Authentik等の例。
**[6] Outline File Storage: **    ローカルファイルストレージと永続ボリューム。
**[7] Qdrant Security: **    セルフホストは既定で安全化されていない。API key、network bind、TLS等を推奨。
**[8] llama.cpp: **    ローカルLLM推論、GGUF、OpenAI互換HTTP server。
**[9] Qwen3-Embedding-0.6B: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B    Phase 3の多言語Embedding初期候補。0.6B、1024次元、32K context、100+言語、Apache-2.0。**
[10] Qwen3-Reranker-0.6B: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B    Phase 4のReranker初期候補。0.6B、32K context、100+言語、Apache-2.0。
[11] GitHub Protected Branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches    main等の重要ブランチに対し、Pull Request、status checks、review等のマージ条件を設定できる。
[12] GitHub Status Checks: https://docs.github.com/en/pull-requests/reference/status-checks    GitHub Actions等のCI結果をPull Request上のcheckとして表示し、保護ブランチではマージ条件にできる。
[13] GitHub Linking Pull Requests to Issues: https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue    PR本文の Closes #<番号> 等でIssueを関連付け、既定ブランチへのマージ時にIssueを自動closeできる。
注: ソフトウェアのバージョンやモデル候補は更新が速いため、実装開始時に公式ドキュメントとライセンスを再確認します。上記は2026年9月5日時点で確認した情報を基にしています。

# 付録A. 用語集



# 付録B. 次に作る実装成果物

本設計書の次工程ではPhase 1（Chienami Knowledge）のみを実装対象とします。文書取り込み・検索・RAGはPhase 1の受入完了後に追加します。
Phase 1用・バージョン固定済み compose.yaml（Reverse Proxy / Outline / PostgreSQL / Redis）
Outline用 docker.env / secretテンプレート
Reverse Proxy + HTTPS設定
OIDC等の認証設定手順
初期Collection構成とTroubleshooting / Protocolテンプレート
添付ファイル永続化設定
Phase 2/3/4拡張用インターフェース方針（API・document_id・metadata・権限）
Phase 1受入試験チェックリスト
運用・更新手順書
バックアップ / 復元スクリプト
データ保存場所・Docker volume運用・本番 /srv/chienami 配置手順
Windows/WSL2開発環境からLinux本番環境への移行手順
研究室メンバー向け1ページ利用マニュアル