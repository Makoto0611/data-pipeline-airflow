# DAG仕様書

**作成日**: 2026年01月27日  
**対象**: Phase 3で作成した4つのETL DAG  
**目的**: 各DAGファイルの役割と実装内容を明確化

---

## 📋 4つのDAGの全体像

Phase 3では、ETLパイプラインを段階的に改善していく4つのバージョンを作成しました。

| ファイル名 | バージョン | 主要機能 | 行数 |
|-----------|----------|---------|------|
| 01_basic_etl_dag_base.py | 基本版 | 基本的なETL処理のみ | 約150行 |
| 02_basic_etl_dag_error_handling.py | エラー対応版 | リトライ・タイムアウト追加 | 約220行 |
| 03_basic_etl_dag_data_quality.py | 品質保証版 | データ品質チェック追加 | 約330行 |
| 04_basic_etl_dag_performance.py | 最適化版 | パフォーマンス計測追加 | 約380行 |

**進化の方向性**: シンプル → 堅牢 → 安全 → 高速

---

## 📄 01_basic_etl_dag_base.py

### 🎯 目的

**最もシンプルなETLパイプラインの実装**

エラーハンドリング、データ品質チェック、パフォーマンス改善などは含まず、ETLの基本的な流れだけを実装したベースライン版。

### 📊 処理フロー

```
Extract → Transform → Load
```

### 🔧 実装内容

#### Extract（抽出）
- **処理**: PostgreSQLの`sales`テーブルから全データを取得
- **出力**: `/tmp/extracted_data.csv`
- **技術**: psycopg2 + pandas

```python
query = "SELECT * FROM sales"
df = pd.read_sql(query, conn)
df.to_csv('/tmp/extracted_data.csv', index=False)
```

#### Transform（変換）
- **処理**: 日付別に売上を集計
- **入力**: `/tmp/extracted_data.csv`
- **出力**: `/tmp/transformed_data.csv`
- **集計内容**:
  - `total_amount`: 日付ごとの売上合計
  - `product_count`: 日付ごとの商品数

```python
transformed_df = df.groupby('sale_date').agg({
    'amount': 'sum',
    'id': 'count'
})
```

#### Load（読み込み）
- **処理**: 集計データをPostgreSQLに保存
- **入力**: `/tmp/transformed_data.csv`
- **保存先**: PostgreSQL `sales_summary`テーブル
- **技術**: SQLAlchemy

```python
df.to_sql('sales_summary', engine, if_exists='replace', index=False)
```

### 📈 データの変化

**Extract前（salesテーブル）**:
```
id | product_name | amount | sale_date
1  | ノートPC     | 89800  | 2026-01-15
2  | マウス       | 2980   | 2026-01-16
3  | キーボード   | 8900   | 2026-01-16
```

**Transform後（集計データ）**:
```
sale_date  | total_amount | product_count
2026-01-15 | 89800        | 1
2026-01-16 | 11880        | 2
```

### ⚠️ 制限事項

- エラー発生時の対応なし
- データ品質のチェックなし
- パフォーマンス計測なし
- 学習用のシンプル実装

### 🎓 学習ポイント

- ETLパイプラインの基本構造
- Airflowでのタスク定義方法
- pandasでのデータ集計
- タスク間の依存関係（`>>`演算子）

---

## 📄 02_basic_etl_dag_error_handling.py

### 🎯 目的

**エラーハンドリング機能を追加したETLパイプライン**

本番環境で必要となる、エラー発生時の自動リトライやタイムアウト設定を実装。

### 🆕 01からの追加機能

#### ① default_args（エラーハンドリング設定）

```python
default_args = {
    'retries': 3,                              # 失敗時3回まで自動リトライ
    'retry_delay': timedelta(minutes=2),       # 最初は2分待つ
    'retry_exponential_backoff': True,         # 2分→4分→8分と間隔を広げる
    'max_retry_delay': timedelta(hours=1),     # 最大1時間まで待つ
    'execution_timeout': timedelta(minutes=30), # 30分でタイムアウト
}
```

**効果**:
- ネットワーク一時障害でも自動復旧
- DB接続エラーでも数回リトライ
- 無限ループを防ぐタイムアウト

#### ② try-except（例外処理）

**Extract関数の例外処理**:
```python
try:
    conn = psycopg2.connect(...)
    df = pd.read_sql(query, conn)
except psycopg2.OperationalError as e:
    logger.error(f"Database connection failed: {e}")
    raise
except psycopg2.DatabaseError as e:
    logger.error(f"Database query failed: {e}")
    raise
```

**エラーの種類別に対応**:
- `OperationalError`: DB接続エラー
- `DatabaseError`: SQLクエリエラー
- `FileNotFoundError`: ファイル読み込みエラー
- `KeyError`: カラム不足エラー
- `ValueError`: データ検証エラー

#### ③ ロギング

```python
logger.info("Starting data extraction from PostgreSQL")
logger.error(f"Database connection failed: {e}")
```

**効果**:
- 処理の進捗が追跡可能
- エラー原因の特定が容易
- トラブルシューティングが効率的

### 📊 処理フロー

```
Extract（+ エラーハンドリング）
  ↓
Transform（+ エラーハンドリング）
  ↓
Load（+ エラーハンドリング）
```

### 🎓 学習ポイント

- 本番環境で必要なエラー対策
- リトライの重要性
- エラーログの活用方法
- 例外の種類別処理

### 💼 実務での価値

- **自動復旧**: 夜間バッチが一時的なエラーで止まらない
- **原因特定**: エラーログで問題箇所を素早く発見
- **運用負荷軽減**: 手動介入が減る

---

## 📄 03_basic_etl_dag_data_quality.py

### 🎯 目的

**データ品質チェック機能を追加したETLパイプライン**

不正なデータがDBに保存されることを防ぐため、Transform後にデータ品質をチェック。

### 🆕 02からの追加機能

#### ① check_data_quality関数（新規タスク）

Transform後、Load前に実行される品質チェック専用タスク。

```python
def check_data_quality():
    df = pd.read_csv('/tmp/transformed_data.csv')
    
    # 4種類のチェックを実行
    # 問題があればValueErrorを発生させてタスクを停止
```

#### ② 4種類の品質チェック

**チェック①: データ件数チェック**
```python
if len(df) == 0:
    raise ValueError("❌ データが0件です！")
```
- **目的**: Extract/Transform処理が正常に動作したか確認
- **失敗例**: SQLクエリが間違っている、フィルタ条件が厳しすぎる

**チェック②: NULL値チェック**
```python
if df['sale_date'].isnull().any():
    null_count = df['sale_date'].isnull().sum()
    raise ValueError(f"❌ sale_dateに{null_count}件のNULLがあります！")
```
- **目的**: 必須カラムに値が入っているか確認
- **失敗例**: データソースにNULLが含まれる、結合処理でNULLが発生

**チェック③: データ型チェック**
```python
if not pd.api.types.is_numeric_dtype(df['total_amount']):
    raise ValueError(f"❌ total_amountが数値型ではありません")
```
- **目的**: 期待するデータ型になっているか確認
- **失敗例**: 文字列が数値カラムに混入、型変換失敗

**チェック④: 異常値チェック**
```python
# 売上がマイナスは異常
negative_amounts = df[df['total_amount'] < 0]
if len(negative_amounts) > 0:
    raise ValueError(f"❌ 売上金額がマイナスのデータが{len(negative_amounts)}件あります！")

# 商品数が0以下は異常
invalid_counts = df[df['product_count'] <= 0]
if len(invalid_counts) > 0:
    raise ValueError(f"❌ 商品数が0以下のデータが{len(invalid_counts)}件あります！")

# 1日の売上が1000万円を超えたら警告
high_amount_data = df[df['total_amount'] > 10000000]
if len(high_amount_data) > 0:
    logger.warning(f"⚠️ 異常に高額な売上があります！")
```
- **目的**: ビジネスロジック的におかしいデータを検出
- **失敗例**: マイナス売上、0個販売、異常に高額な売上

### 📊 処理フロー

```
Extract（+ エラーハンドリング）
  ↓
Transform（+ エラーハンドリング）
  ↓
★ Check Data Quality（新規）★
  ↓
Load（+ エラーハンドリング）
```

### 🎓 学習ポイント

- データ品質保証の重要性
- 早期エラー検出（Fail Fast原則）
- ビジネスロジックの検証方法
- NULL値・異常値の扱い方

### 💼 実務での価値

- **データ破損防止**: 不正データがDBに入らない
- **早期発見**: LoadされてからではなくTransform直後に検出
- **信頼性向上**: 下流システムに正しいデータだけを渡す
- **デバッグ効率化**: どこで問題が起きたか明確

### ⚠️ 注意点

**チェックが厳しすぎる場合**:
- 正常なデータもエラーになる可能性
- ビジネス要件に合わせて調整が必要

**例**: 
- セール期間中は売上が1000万円超えることもある
- 返品処理でマイナス金額が発生することもある

→ 実務では要件定義が重要

---

## 📄 04_basic_etl_dag_performance.py

### 🎯 目的

**パフォーマンス計測機能を追加したETLパイプライン**

処理時間とメモリ使用量を計測して、ボトルネックを見つけやすくする。

### 🆕 03からの追加機能

#### ① クエリ最適化

**変更前（01-03）**:
```python
query = "SELECT * FROM sales"  # 全カラム取得
```

**変更後（04）**:
```python
# 【改善①】必要なカラムだけ取得
query = """
    SELECT 
        id,
        sale_date,
        amount
    FROM sales
"""
```

**効果**:
- ネットワーク転送量が削減
- メモリ使用量が削減
- 実行速度が向上（特に大量データで顕著）

**実務例**:
- 100カラムあるテーブルで3カラムだけ使う場合
- 転送量が1/30以下になることも

#### ② 処理時間計測

```python
import time

def extract_from_postgres():
    start_time = time.time()  # 開始時刻を記録
    
    # Extract処理
    
    elapsed_time = time.time() - start_time  # 経過時間を計算
    logger.info(f"⏱️ Extract処理時間: {elapsed_time:.2f}秒")
```

**全関数で計測**:
- Extract処理時間
- Transform処理時間
- Load処理時間

#### ③ メモリ使用量計測

```python
import psutil
import os

def extract_from_postgres():
    process = psutil.Process(os.getpid())
    start_memory = process.memory_info().rss / 1024 / 1024  # MB単位
    
    # Extract処理
    
    end_memory = process.memory_info().rss / 1024 / 1024
    memory_used = end_memory - start_memory
    logger.info(f"💾 Extract メモリ使用量: {memory_used:.2f}MB")
```

**計測タイミング**:
- 各関数の開始時と終了時
- メモリ増加量を記録

#### ④ パフォーマンスサマリー

```python
def load_to_postgres():
    # Load処理
    
    # 【改善④】全体のパフォーマンスサマリーを出力
    logger.info("=" * 50)
    logger.info("📊 パフォーマンスサマリー")
    logger.info(f"⏱️ 処理時間合計: {total_time:.2f}秒")
    logger.info(f"💾 メモリ使用量合計: {total_memory:.2f}MB")
    logger.info("=" * 50)
```

**実行例**:
```
==================================================
📊 パフォーマンスサマリー
⏱️ 処理時間合計: 0.12秒
💾 メモリ使用量合計: 6.88MB
==================================================
```

### 📊 処理フロー

```
Extract（+ エラーハンドリング + ⏱️時間計測 + 💾メモリ計測）
  ↓
Transform（+ エラーハンドリング + ⏱️時間計測 + 💾メモリ計測）
  ↓
Check Data Quality
  ↓
Load（+ エラーハンドリング + ⏱️時間計測 + 💾メモリ計測 + 📊サマリー）
```

### 🎓 学習ポイント

- パフォーマンス計測の重要性
- SQLクエリ最適化の効果
- ボトルネック特定の方法
- メモリ使用量の監視

### 💼 実務での価値

**改善前の問題**:
- どこが遅いのかわからない
- メモリ不足で突然落ちる
- 改善効果が測れない

**改善後のメリット**:
- ボトルネックが明確
- メモリ使用量を監視できる
- 改善効果を数値で証明できる

**実務例**:
```
Extract: 0.5秒 → クエリ最適化 → 0.2秒（60%削減）
Transform: 2.0秒 → アルゴリズム改善 → 0.8秒（60%削減）
Load: 0.3秒 → バッチ挿入 → 0.1秒（67%削減）
```

### ⚠️ 注意点

**小規模データでは効果が見えにくい**:
- 今回のテストデータ: 数行〜数十行
- 処理時間: 0.1秒程度
- メモリ: 数MB程度

**本番環境では大きな差**:
- データ量: 数百万行〜数億行
- 処理時間: 数分〜数時間
- メモリ: 数GB〜数十GB

→ 最適化の効果が数十倍〜数百倍になることも

---

## 📊 4つのDAGの比較表

| 機能 | 01_base | 02_error | 03_quality | 04_performance |
|-----|---------|----------|------------|----------------|
| **基本ETL** | ✅ | ✅ | ✅ | ✅ |
| **エラーハンドリング** | ❌ | ✅ | ✅ | ✅ |
| **リトライ設定** | ❌ | ✅ | ✅ | ✅ |
| **ロギング** | ❌ | ✅ | ✅ | ✅ |
| **データ品質チェック** | ❌ | ❌ | ✅ | ✅ |
| **NULL値チェック** | ❌ | ❌ | ✅ | ✅ |
| **異常値チェック** | ❌ | ❌ | ✅ | ✅ |
| **クエリ最適化** | ❌ | ❌ | ❌ | ✅ |
| **処理時間計測** | ❌ | ❌ | ❌ | ✅ |
| **メモリ計測** | ❌ | ❌ | ❌ | ✅ |
| **パフォーマンスサマリー** | ❌ | ❌ | ❌ | ✅ |

### 進化の流れ

```
01_base（シンプル）
  ↓ + エラー対策
02_error（堅牢）
  ↓ + 品質保証
03_quality（安全）
  ↓ + 最適化
04_performance（高速）
```

---

## 🎓 Phase 3で学んだこと

### 技術的なポイント

1. **段階的な改善の重要性**
   - いきなり完璧を目指さない
   - 1つずつ機能を追加して理解を深める

2. **本番運用に必要な要素**
   - エラーハンドリング: 自動復旧
   - データ品質チェック: 不正データ防止
   - パフォーマンス計測: ボトルネック特定

3. **実務で使える実装パターン**
   - try-except の使い分け
   - ロギングの活用方法
   - データ検証の実装方法

### 実務への応用

**今回の学習内容は実務でそのまま使える**:
- ETLパイプラインの基本構造
- エラー対策の実装方法
- データ品質保証の考え方
- パフォーマンス改善の手法

**次のステップ**:
- より大規模なデータでの実装
- BigQueryへの実装
- 監視・アラート設定
- テスト自動化

---

**作成日**: 2026年01月27日  
**作成者**: Claude  
**承認**: Makoto
