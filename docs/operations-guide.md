# 運用手順書

**作成日**: 2026年01月30日  
**バージョン**: 1.0  
**対象**: data-pipeline-airflow プロジェクト

---

## 📋 目次

1. [環境構築](#環境構築)
2. [起動・停止手順](#起動停止手順)
3. [日常運用](#日常運用)
4. [監視とメンテナンス](#監視とメンテナンス)
5. [トラブルシューティング](#トラブルシューティング)
6. [バックアップとリカバリ](#バックアップとリカバリ)

---

## 🚀 環境構築

### 前提条件

#### 必要なソフトウェア
- Docker Desktop: 20.x以上
- Docker Compose: 2.x以上
- Git: 最新版
- テキストエディタ（VSCode推奨）

#### システム要件
- OS: Windows 10/11, macOS, Linux
- メモリ: 最低8GB（推奨16GB）
- ディスク: 最低10GB空き容量
- CPU: 2コア以上

### 初期セットアップ手順

#### 1. リポジトリのクローン

```bash
# GitHubからクローン
git clone https://github.com/yourusername/data-pipeline-airflow.git
cd data-pipeline-airflow
```

#### 2. 環境変数の設定

```bash
# .env.exampleをコピー
cp .env.example .env

# .envファイルを編集（必要に応じて）
# デフォルト設定で問題なければそのまま使用可能
```

#### 3. 必要なディレクトリの作成

```bash
# ログディレクトリ
mkdir -p logs

# プラグインディレクトリ
mkdir -p plugins

# 設定ディレクトリ
mkdir -p config
```

#### 4. Docker環境の起動

```bash
# 初回起動（初期化含む）
docker-compose up airflow-init

# 初期化が完了したら、全サービスを起動
docker-compose up -d
```

#### 5. 起動確認

```bash
# コンテナの状態確認
docker-compose ps

# 期待される出力
# NAME                          STATE
# airflow-webserver-1           running
# airflow-scheduler-1           running
# airflow-worker-1              running
# postgres-1                    running
# redis-1                       running
```

#### 6. Airflow UIへのアクセス

1. ブラウザで `http://localhost:8080` を開く
2. ログイン情報を入力
   - Username: `admin`
   - Password: `admin`
3. DAGリストが表示されることを確認

#### 7. サンプルデータの投入

```bash
# Postgresコンテナに接続
docker-compose exec postgres psql -U airflow

# SQLを実行
CREATE TABLE IF NOT EXISTS sales (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(100),
    amount INTEGER,
    sale_date DATE
);

INSERT INTO sales (product_name, amount, sale_date) VALUES
('ノートパソコン', 89800, '2026-01-15'),
('マウス', 2980, '2026-01-16'),
('キーボード', 8900, '2026-01-16'),
('モニター', 35000, '2026-01-17'),
('Webカメラ', 6500, '2026-01-18');

-- 確認
SELECT * FROM sales;

-- 終了
\q
```

---

## ⚙️ 起動・停止手順

### 通常起動

```bash
# バックグラウンドで起動
docker-compose up -d

# ログを確認しながら起動
docker-compose up
```

### 通常停止

```bash
# 停止（コンテナは削除されない）
docker-compose stop

# 停止＋コンテナ削除
docker-compose down
```

### 完全クリーンアップ

```bash
# コンテナ・ネットワーク・ボリュームをすべて削除
docker-compose down -v

# 注意: データベースのデータもすべて削除されます！
```

### 再起動

```bash
# 再起動
docker-compose restart

# 特定サービスのみ再起動
docker-compose restart airflow-webserver
```

### コンテナの状態確認

```bash
# 起動中のコンテナ確認
docker-compose ps

# ログ確認
docker-compose logs -f

# 特定サービスのログ
docker-compose logs -f airflow-scheduler
```

---

## 📊 日常運用

### DAGの管理

#### DAGの有効化/無効化

**Web UI**:
1. DAGリストで対象DAGを探す
2. トグルスイッチをクリック
3. 青色（ON）= 有効、グレー（OFF）= 無効

**CLI**:
```bash
# DAGを有効化
docker-compose exec airflow-webserver airflow dags unpause basic_etl_pipeline_base

# DAGを無効化
docker-compose exec airflow-webserver airflow dags pause basic_etl_pipeline_base
```

#### 手動実行

**Web UI**:
1. DAGを選択
2. 右上の「▶（Play）」ボタンをクリック
3. 「Trigger DAG」を選択
4. 実行日時を確認して「Trigger」

**CLI**:
```bash
# DAGを手動実行
docker-compose exec airflow-webserver airflow dags trigger basic_etl_pipeline_base
```

#### DAGの更新

1. `dags/`ディレクトリ内のファイルを編集
2. ファイルを保存
3. 自動的に反映される（約30秒後）
4. Web UIでリロードして確認

### タスクの監視

#### 実行状況の確認

**Web UI**:
1. DAGを選択
2. 「Graph」ビューでタスクの依存関係と状態を確認
3. タスクをクリックして詳細を表示

**タスクの状態**:
- 🟢 **success**: 成功
- 🔴 **failed**: 失敗
- 🟡 **running**: 実行中
- ⚪ **queued**: キューに追加済み
- ⚫ **scheduled**: スケジュール済み
- 🟣 **upstream_failed**: 上流タスクが失敗

#### ログの確認

**Web UI**:
1. タスクをクリック
2. 「Log」タブを選択
3. 実行ログが表示される

**CLI**:
```bash
# タスクログを表示
docker-compose exec airflow-webserver airflow tasks logs \
  basic_etl_pipeline_base extract_from_postgres 2026-01-30
```

#### タスクの再実行

**Web UI**:
1. 失敗したタスクをクリック
2. 「Clear」ボタンをクリック
3. 再実行の範囲を選択
4. 「Clear」で確定

### データの確認

#### PostgreSQLのデータ確認

```bash
# PostgreSQLに接続
docker-compose exec postgres psql -U airflow

# テーブル一覧
\dt

# salesテーブルの確認
SELECT * FROM sales ORDER BY sale_date DESC LIMIT 10;

# daily_summaryテーブルの確認
SELECT * FROM daily_summary ORDER BY date DESC LIMIT 10;

# 終了
\q
```

---

## 🔍 監視とメンテナンス

### 定期監視項目

#### 毎日確認すべき項目

1. **DAGの実行状態**
   - すべてのDAGが正常に完了しているか
   - 失敗したタスクがないか

2. **ディスク容量**
   ```bash
   # ディスク使用量確認
   docker system df
   
   # ログディレクトリの容量
   du -sh logs/
   ```

3. **コンテナの健全性**
   ```bash
   # コンテナの状態確認
   docker-compose ps
   
   # リソース使用量
   docker stats --no-stream
   ```

#### 週次確認項目

1. **ログのローテーション**
   ```bash
   # 古いログを削除（7日以上前）
   find logs/ -name "*.log" -mtime +7 -delete
   ```

2. **データベースのバックアップ**
   ```bash
   # PostgreSQLのバックアップ
   docker-compose exec postgres pg_dump -U airflow airflow > backup_$(date +%Y%m%d).sql
   ```

3. **Dockerイメージの更新確認**
   ```bash
   # イメージの更新確認
   docker-compose pull
   ```

### パフォーマンス監視

#### メトリクス確認

```bash
# コンテナのCPU/メモリ使用量
docker stats

# PostgreSQLの接続数
docker-compose exec postgres psql -U airflow -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Redisの情報
docker-compose exec redis redis-cli INFO
```

#### スロークエリの確認

```bash
# PostgreSQLのスロークエリログを有効化
docker-compose exec postgres psql -U airflow -c \
  "ALTER SYSTEM SET log_min_duration_statement = 1000;"

# 設定を反映
docker-compose restart postgres
```

---

## 🚨 トラブルシューティング

### よくある問題と解決方法

#### 問題1: Airflow UIにアクセスできない

**症状**:
- `http://localhost:8080` にアクセスできない

**確認手順**:
```bash
# 1. コンテナが起動しているか確認
docker-compose ps

# 2. airflow-webserverのログ確認
docker-compose logs airflow-webserver

# 3. ポートが使用されているか確認
netstat -an | grep 8080  # Windows: netstat -an | findstr 8080
```

**解決方法**:
- コンテナが停止している場合: `docker-compose up -d`
- ポートが競合している場合: `docker-compose.yaml`の8080を別のポート（例: 8081）に変更

#### 問題2: DAGが表示されない

**症状**:
- Web UIでDAGリストが空

**確認手順**:
```bash
# 1. DAGファイルの場所確認
ls -la dags/

# 2. DAGファイルのパース確認
docker-compose exec airflow-webserver airflow dags list

# 3. エラーログ確認
docker-compose logs airflow-scheduler | grep ERROR
```

**解決方法**:
- DAGファイルに構文エラーがある場合: ファイルを修正
- マウントが失敗している場合: `docker-compose down` → `docker-compose up -d`

#### 問題3: タスクが失敗する

**症状**:
- タスクが継続的に失敗する

**確認手順**:
```bash
# 1. タスクログ確認（Web UIで）
# DAG → Task → Log

# 2. データベース接続確認
docker-compose exec postgres psql -U airflow -c "SELECT 1;"

# 3. Python環境確認
docker-compose exec airflow-worker python --version
docker-compose exec airflow-worker pip list
```

**解決方法**:
- データベース接続エラー: 接続情報を確認
- Pythonライブラリエラー: `requirements.txt`に追加して再ビルド

#### 問題4: PostgreSQLに接続できない

**症状**:
- `psycopg2.OperationalError: could not connect`

**確認手順**:
```bash
# 1. PostgreSQLコンテナ確認
docker-compose ps postgres

# 2. PostgreSQL接続テスト
docker-compose exec postgres psql -U airflow -c "SELECT version();"

# 3. ネットワーク確認
docker network ls
docker network inspect data-pipeline-airflow_default
```

**解決方法**:
- PostgreSQLが起動していない: `docker-compose up -d postgres`
- 接続情報が間違っている: `.env`ファイルを確認

#### 問題5: ディスク容量不足

**症状**:
- `No space left on device`

**確認手順**:
```bash
# ディスク使用量確認
df -h
docker system df

# ログファイルのサイズ確認
du -sh logs/
```

**解決方法**:
```bash
# 不要なDockerリソース削除
docker system prune -a

# 古いログ削除
find logs/ -name "*.log" -mtime +7 -delete

# 不要なDockerボリューム削除
docker volume prune
```

### エラーメッセージ別対応

| エラーメッセージ | 原因 | 対処方法 |
|-----------------|------|----------|
| `Connection refused` | サービスが起動していない | `docker-compose up -d` |
| `Permission denied` | ファイル権限の問題 | `chmod 755 dags/` |
| `Module not found` | Pythonライブラリ不足 | `pip install`して再ビルド |
| `Database locked` | SQLiteの同時アクセス | PostgreSQLを使用 |
| `Out of memory` | メモリ不足 | Worker数を減らす |

---

## 💾 バックアップとリカバリ

### バックアップ

#### PostgreSQLデータのバックアップ

```bash
# 全データベースをバックアップ
docker-compose exec postgres pg_dumpall -U airflow > backup_full_$(date +%Y%m%d).sql

# 特定のデータベースをバックアップ
docker-compose exec postgres pg_dump -U airflow airflow > backup_airflow_$(date +%Y%m%d).sql
```

#### DAGファイルのバックアップ

```bash
# dagsディレクトリをバックアップ
tar -czf dags_backup_$(date +%Y%m%d).tar.gz dags/

# Gitで管理している場合
git add .
git commit -m "Backup DAGs $(date +%Y%m%d)"
git push
```

#### 環境設定のバックアップ

```bash
# .envファイルをバックアップ
cp .env .env.backup_$(date +%Y%m%d)

# docker-compose.yamlをバックアップ
cp docker-compose.yaml docker-compose.yaml.backup_$(date +%Y%m%d)
```

### リストア

#### PostgreSQLデータのリストア

```bash
# データベースをリストア
docker-compose exec -T postgres psql -U airflow < backup_airflow_20260130.sql

# または、全データベースをリストア
docker-compose exec -T postgres psql -U airflow < backup_full_20260130.sql
```

#### DAGファイルのリストア

```bash
# バックアップから復元
tar -xzf dags_backup_20260130.tar.gz

# Gitから復元
git checkout dags/
```

### 災害復旧手順

#### 完全な環境再構築

```bash
# 1. 既存環境を完全削除
docker-compose down -v

# 2. 最新のコードを取得
git pull origin main

# 3. 環境変数を復元
cp .env.backup_20260130 .env

# 4. Docker環境を再構築
docker-compose up airflow-init
docker-compose up -d

# 5. データをリストア
docker-compose exec -T postgres psql -U airflow < backup_airflow_20260130.sql

# 6. DAGを確認
# Web UIで確認
```

---

## 📝 チェックリスト

### 環境構築チェックリスト

- [ ] Docker Desktopがインストール済み
- [ ] リポジトリをクローン
- [ ] `.env`ファイルを作成
- [ ] `docker-compose up airflow-init`を実行
- [ ] `docker-compose up -d`を実行
- [ ] `http://localhost:8080`にアクセス可能
- [ ] サンプルデータを投入
- [ ] DAGが表示される

### 日次運用チェックリスト

- [ ] すべてのDAGが正常に完了
- [ ] 失敗したタスクがないか確認
- [ ] ディスク容量を確認
- [ ] コンテナが正常に動作

### 週次メンテナンスチェックリスト

- [ ] 古いログを削除
- [ ] データベースをバックアップ
- [ ] Dockerイメージの更新確認
- [ ] パフォーマンスメトリクスを確認

---

## 🔗 関連ドキュメント

- [アーキテクチャ図](./architecture.md)
- [テスト仕様書](./testing-guide.md)
- [学習総括](./learning-summary.md)
- [README](../README.md)

---

**最終更新**: 2026年01月30日  
**担当**: Makoto  
**次回レビュー**: 2026年02月28日
