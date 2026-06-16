# data-pipeline-airflow

## 🎯 このプロジェクトの目的

### 何を作るのか？

**データを自動的に移動・加工するパイプライン（ETLパイプライン）を作る**

```
[PostgreSQL] → [データ加工] → [BigQuery]
```

### なぜ作るのか？

実務でよくあるシナリオ：
- 古いシステム（PostgreSQL）にデータが溜まっている
- 新しい分析システム（BigQuery）でそのデータを使いたい
- でも、そのまま移すんじゃなくて、途中で計算や整理をしたい
- しかも、毎日自動的にやりたい

→ これを実現するのが**ETLパイプライン**

---

## 📚 ETLとは？

**ETL = Extract（抽出）+ Transform（変換）+ Load（読み込み）**

### Extract（抽出）- データを取り出す
- PostgreSQLから販売データ（sales）を取得
- **目的**: データソースからデータを取り出す

### Transform（変換）- データを加工する
- 金額の合計を計算
- 日付ごとにグループ化
- **目的**: 分析しやすい形に整える

### Load（読み込み）- 別の場所に保存
- BigQueryにデータを送る
- **目的**: 分析ツールで使える場所に保存

---

## 💼 実務での使われ方

### 例1: ECサイトの日次売上集計
```
毎朝6時に自動実行
↓
昨日の販売データを取得（Extract）
↓
商品カテゴリ別に集計（Transform）
↓
BIツールで見られる場所に保存（Load）
```

### 例2: ログデータの分析準備
```
1時間ごとに自動実行
↓
サーバーログを取得（Extract）
↓
エラーだけ抽出、時間帯別に集計（Transform）
↓
監視ダッシュボードに送信（Load）
```

---

## 🏗️ 今回の実装内容

### Phase 2（基本ETL）で作るもの

**データの流れ**:
```
[PostgreSQL: salesテーブル]
  ↓ Extract
[pandas DataFrame]
  ↓ Transform
[加工済みデータ]
  ↓ Load
[BigQuery]
```

### 使用する技術
- **Docker**: 開発環境を簡単に構築
- **Apache Airflow**: パイプラインのスケジュール実行
- **PostgreSQL**: データの保管場所（ソース）
- **pandas**: Pythonでデータを加工
- **BigQuery**: データの保管場所（デスティネーション）

---

## 🚀 セットアップ・起動方法

### 初回・2回目以降ともにこれだけでOK

```bash
chmod +x start.sh   # 初回のみ
./start.sh
```

30秒ほど待ってから `http://localhost:8080` にアクセス（ユーザー名・パスワードはどちらも `airflow`）。

### `start.sh` がやっていること（なぜ必要か）

`docker-compose up -d` を直接叩くと、以下の理由で起動に失敗することがある（2026-06-16に実際に発生・原因調査済み）。

1. **`AIRFLOW_UID` 未設定問題**: `.env` に `AIRFLOW_UID`（ホスト側のユーザーID）が無いと、`airflow-init` の `chown` が効かず、`logs`/`dags`/`plugins`/`config` が `root` 所有のまま残る。その結果、webserver/scheduler が `PermissionError: ... logs/scheduler` で起動失敗する。
2. **フォルダ自動生成時の権限不備**: `logs` などのフォルダが存在しない状態で `docker-compose up` すると、Dockerがホスト側に自動でディレクトリを作るが、その際に実行権限（x）が無い中途半端なパーミッション（666など）で作られることがある。

`start.sh` は `.env` に `AIRFLOW_UID` が無ければ追記し、`logs`/`dags`/`plugins`/`config` を事前に `mkdir -p` してから `docker-compose up -d` を実行することで、この2つを防いでいる。

### うまく起動しない場合の確認コマンド

```bash
docker ps -a                                              # 各コンテナの状態確認
docker logs data-pipeline-airflow-airflow-webserver-1     # webserverのエラー確認
ls -la                                                    # logs/dags/plugins/config の所有者確認
```

---

## 🎓 このプロジェクトで学べること

1. **ETLパイプラインの基本概念**
   - データがどう流れるか
   - なぜ各ステップが必要か

2. **Airflowの使い方**
   - DAG（有向非巡回グラフ）の書き方
   - タスクの依存関係
   - スケジュール実行

3. **pandasでのデータ加工**
   - SQLから取得したデータの処理
   - 集計・変換の実装

4. **実務で使えるスキル**
   - データエンジニアの基本業務
   - 自動化の考え方

---

## 📊 データの例

### Extract前（PostgreSQL: salesテーブル）
```
id | product_name    | amount  | sale_date
---|-----------------|---------|------------
1  | ノートパソコン  | 89800   | 2026-01-15
2  | マウス          | 2980    | 2026-01-16
3  | キーボード      | 8900    | 2026-01-16
4  | モニター        | 35000   | 2026-01-17
5  | Webカメラ       | 6500    | 2026-01-18
```

### Transform後（加工されたデータ）
```
date       | total_amount | product_count
-----------|--------------|---------------
2026-01-15 | 89800        | 1
2026-01-16 | 11880        | 2
2026-01-17 | 35000        | 1
2026-01-18 | 6500         | 1
```

### Load後（BigQuery）
- 分析ツールで見られる
- SQLで集計できる
- ダッシュボードに表示できる

---

## 🚀 現在の進捗

### ✅ 完了
- [x] Airflow環境構築（Docker Compose）
- [x] PostgreSQL環境準備（salesテーブル作成）
- [x] Hello World DAG作成
- [x] **Extract実装**（PostgreSQL → pandas）

### 🔄 進行中
- [ ] Transform実装（pandasでデータ加工）
- [ ] Load実装（BigQuery へ送信）

### ⏸️ 未着手
- [ ] エラーハンドリング
- [ ] スケジュール設定
- [ ] 監視・ログ設定

---

## 💡 重要なポイント

### なぜpandasを使うのか？
- SQLだけでは複雑な処理が難しい
- Pythonの豊富なライブラリが使える
- データサイエンスの標準ツール

### なぜAirflowを使うのか？
- スケジュール実行が簡単
- 依存関係の管理が楽
- 実行履歴が見られる
- エラー時の再実行が簡単

### 実務での価値
- 手作業を自動化できる
- 毎日同じ処理を確実に実行
- エラーを早期発見
- データ分析の前準備を効率化

---

**作成日**: 2026年01月20日  
**学習サイクル**: Cycle 4 Phase 2
