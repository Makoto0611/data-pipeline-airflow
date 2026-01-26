# ETLパイプライン実装 - パフォーマンス改善版
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# Phase 3: パフォーマンス改善機能を追加
# 学習日: 2026-01-26

"""
========================================
パフォーマンス改善ポイント一覧
========================================

【改善①】クエリ最適化
    場所: extract_from_postgres関数（67行目付近）
    内容: SELECT * → SELECT id, sale_date, amount
    効果: 不要なカラムを取得しないことで、ネットワーク転送量とメモリ使用量を削減

【改善②】処理時間計測
    場所: すべての関数（extract/transform/check/load）
    内容: time.time()で各処理の開始・終了時刻を記録
    効果: どの処理に時間がかかっているかを可視化

【改善③】メモリ使用量計測
    場所: すべての関数（extract/transform/check/load）
    内容: psutil.Process()で各処理のメモリ使用量を記録
    効果: メモリ不足のリスクを事前に検知

【改善④】改善効果サマリー
    場所: load_to_postgres関数の最後（最終行付近）
    内容: 全処理の合計時間とメモリ使用量を出力
    効果: パイプライン全体のパフォーマンスを一目で把握
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import pandas as pd
from sqlalchemy import create_engine
import logging
import time  # 【改善②】処理時間計測用
import psutil  # 【改善③】メモリ計測用
import os  # 【改善③】プロセスID取得用

# ロガーの設定
logger = logging.getLogger(__name__)

# パフォーマンス計測データを保存する辞書 【改善④】
performance_metrics = {
    'extract': {'time': 0, 'memory': 0},
    'transform': {'time': 0, 'memory': 0},
    'quality_check': {'time': 0, 'memory': 0},
    'load': {'time': 0, 'memory': 0}
}

# エラーハンドリング設定（全タスクに適用）
default_args = {
    'retries': 3,                              # 失敗時3回まで自動リトライ
    'retry_delay': timedelta(minutes=2),       # 最初は2分待つ
    'retry_exponential_backoff': True,         # 2分→4分→8分と間隔を広げる
    'max_retry_delay': timedelta(hours=1),     # 最大1時間まで待つ
    'execution_timeout': timedelta(minutes=30), # 30分でタイムアウト
}

# ========================================
# Extract: PostgreSQLからデータを抽出
# ========================================
def extract_from_postgres():
    """
    PostgreSQLからデータを抽出する関数
    エラーハンドリング: DB接続エラー、クエリ実行エラーに対応
    パフォーマンス改善: クエリ最適化、時間・メモリ計測
    """
    # 【改善②】処理時間計測 - 開始時刻を記録
    start_time = time.time()
    
    # 【改善③】メモリ計測 - 開始時のメモリ使用量を記録
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB単位
    
    try:
        logger.info("Starting data extraction from PostgreSQL")
        
        # PostgreSQLに接続
        conn = psycopg2.connect(
            host="source-postgres",
            database="sourcedb",
            user="sourceuser",
            password="sourcepass",
            port=5432
        )
        logger.info("Successfully connected to PostgreSQL")
        
        # 【改善①】クエリ最適化: SELECT * → 必要なカラムのみ取得
        # 変更前: query = "SELECT * FROM sales"
        # 変更後: 必要なカラム（id, sale_date, amount）のみ取得
        query = "SELECT id, sale_date, amount FROM sales"
        logger.info("【改善①】最適化されたクエリを実行: 必要なカラムのみ取得")
        
        df = pd.read_sql(query, conn)
        
        # 接続を閉じる
        conn.close()
        
        # データ確認
        logger.info(f"Extracted {len(df)} rows")
        print(df.head())
        
        # CSVファイルに保存
        df.to_csv('/tmp/extracted_data.csv', index=False)
        logger.info("Data saved to /tmp/extracted_data.csv")
        
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        raise
    
    except psycopg2.DatabaseError as e:
        logger.error(f"Database query failed: {e}")
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error in extract: {e}")
        raise
    
    finally:
        # 【改善②】処理時間計測 - 終了時刻を記録して経過時間を計算
        end_time = time.time()
        elapsed_time = end_time - start_time
        performance_metrics['extract']['time'] = elapsed_time
        logger.info(f"⏱️ 【改善②】Extract処理時間: {elapsed_time:.2f}秒")
        
        # 【改善③】メモリ計測 - 終了時のメモリ使用量を記録
        mem_after = process.memory_info().rss / 1024 / 1024  # MB単位
        mem_used = mem_after - mem_before
        performance_metrics['extract']['memory'] = mem_used
        logger.info(f"💾 【改善③】Extract使用メモリ: {mem_used:.2f}MB")

# ========================================
# Transform: データを加工する
# ========================================
def transform_sales_data():
    """
    データを変換する関数（日付別に集計）
    エラーハンドリング: ファイル読み込みエラー、pandas処理エラーに対応
    パフォーマンス改善: 時間・メモリ計測
    """
    # 【改善②】処理時間計測 - 開始時刻を記録
    start_time = time.time()
    
    # 【改善③】メモリ計測 - 開始時のメモリ使用量を記録
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB単位
    
    try:
        logger.info("Starting data transformation")
        
        # CSVを読み込む
        df = pd.read_csv('/tmp/extracted_data.csv')
        logger.info(f"Loaded {len(df)} rows for transformation")
        print("Original data:")
        print(df.head())
        
        # データ検証: 必要なカラムが存在するか確認
        required_columns = ['sale_date', 'amount', 'id']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # 日付でグループ化して集計
        transformed_df = df.groupby('sale_date').agg({
            'amount': 'sum',
            'id': 'count'
        })

        # カラム名を変更
        transformed_df.columns = ['total_amount', 'product_count']
        transformed_df = transformed_df.reset_index()

        # 結果を保存
        transformed_df.to_csv('/tmp/transformed_data.csv', index=False)
        logger.info("Transformed data saved to /tmp/transformed_data.csv")
        print("Transformed data:")
        print(transformed_df)
        
    except FileNotFoundError as e:
        logger.error(f"Input file not found: {e}")
        raise
    
    except KeyError as e:
        logger.error(f"Required column missing: {e}")
        raise
    
    except ValueError as e:
        logger.error(f"Data validation error: {e}")
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error in transform: {e}")
        raise
    
    finally:
        # 【改善②】処理時間計測 - 終了時刻を記録して経過時間を計算
        end_time = time.time()
        elapsed_time = end_time - start_time
        performance_metrics['transform']['time'] = elapsed_time
        logger.info(f"⏱️ 【改善②】Transform処理時間: {elapsed_time:.2f}秒")
        
        # 【改善③】メモリ計測 - 終了時のメモリ使用量を記録
        mem_after = process.memory_info().rss / 1024 / 1024  # MB単位
        mem_used = mem_after - mem_before
        performance_metrics['transform']['memory'] = mem_used
        logger.info(f"💾 【改善③】Transform使用メモリ: {mem_used:.2f}MB")

# ========================================
# Data Quality Check: データ品質チェック
# ========================================
def check_data_quality():
    """
    Transform後のデータ品質をチェックする関数
    
    チェック項目:
    1. データ件数チェック - データが0件でないか
    2. NULL値チェック - 必須カラムにNULLがないか
    3. データ型チェック - カラムのデータ型が正しいか
    4. 異常値チェック - ビジネスロジック的におかしいデータがないか
    
    問題があればValueErrorを投げてタスクを失敗させる
    パフォーマンス改善: 時間・メモリ計測
    """
    # 【改善②】処理時間計測 - 開始時刻を記録
    start_time = time.time()
    
    # 【改善③】メモリ計測 - 開始時のメモリ使用量を記録
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB単位
    
    try:
        logger.info("Starting data quality checks")
        
        # Transform後のCSVを読み込む
        df = pd.read_csv('/tmp/transformed_data.csv')
        logger.info(f"Checking {len(df)} rows")
        
        # ========================================
        # チェック①: データ件数チェック
        # ========================================
        logger.info("Check 1/4: Row count check")
        if len(df) == 0:
            raise ValueError("❌ データが0件です！Extract/Transform処理を確認してください")
        logger.info(f"✓ 件数チェックOK: {len(df)}件のデータ")
        
        # ========================================
        # チェック②: NULL値チェック
        # ========================================
        logger.info("Check 2/4: NULL value check")
        
        # sale_dateのNULLチェック
        if df['sale_date'].isnull().any():
            null_count = df['sale_date'].isnull().sum()
            raise ValueError(f"❌ sale_dateに{null_count}件のNULLがあります！")
        
        # total_amountのNULLチェック
        if df['total_amount'].isnull().any():
            null_count = df['total_amount'].isnull().sum()
            raise ValueError(f"❌ total_amountに{null_count}件のNULLがあります！")
        
        # product_countのNULLチェック
        if df['product_count'].isnull().any():
            null_count = df['product_count'].isnull().sum()
            raise ValueError(f"❌ product_countに{null_count}件のNULLがあります！")
        
        logger.info("✓ NULL値チェックOK: すべての必須カラムにデータが存在")
        
        # ========================================
        # チェック③: データ型チェック
        # ========================================
        logger.info("Check 3/4: Data type check")
        
        # total_amountは数値型であるべき
        if not pd.api.types.is_numeric_dtype(df['total_amount']):
            actual_type = df['total_amount'].dtype
            raise ValueError(f"❌ total_amountが数値型ではありません（実際の型: {actual_type}）")
        
        # product_countも数値型であるべき
        if not pd.api.types.is_numeric_dtype(df['product_count']):
            actual_type = df['product_count'].dtype
            raise ValueError(f"❌ product_countが数値型ではありません（実際の型: {actual_type}）")
        
        logger.info("✓ データ型チェックOK: すべてのカラムが正しい型")
        
        # ========================================
        # チェック④: 異常値チェック
        # ========================================
        logger.info("Check 4/4: Anomaly check")
        
        # 売上がマイナスは異常
        negative_amounts = df[df['total_amount'] < 0]
        if len(negative_amounts) > 0:
            logger.error(f"異常データ:\n{negative_amounts}")
            raise ValueError(f"❌ 売上金額がマイナスのデータが{len(negative_amounts)}件あります！")
        
        # 商品数が0以下は異常
        invalid_counts = df[df['product_count'] <= 0]
        if len(invalid_counts) > 0:
            logger.error(f"異常データ:\n{invalid_counts}")
            raise ValueError(f"❌ 商品数が0以下のデータが{len(invalid_counts)}件あります！")
        
        # 1日の売上が1000万円を超えたら警告（異常に高額）
        high_amount_data = df[df['total_amount'] > 10000000]
        if len(high_amount_data) > 0:
            logger.warning(f"⚠️ 異常に高額な売上があります！確認してください:")
            logger.warning(f"\n{high_amount_data}")
        
        logger.info("✓ 異常値チェックOK: ビジネスロジック的に問題なし")
        
        # ========================================
        # すべてのチェック完了
        # ========================================
        logger.info("=" * 50)
        logger.info("🎉 All data quality checks passed!")
        logger.info("=" * 50)
        
    except FileNotFoundError as e:
        logger.error(f"Transform後のファイルが見つかりません: {e}")
        raise
    
    except ValueError as e:
        # データ品質エラー - タスクを失敗させる
        logger.error(f"データ品質チェック失敗: {e}")
        raise
    
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        raise
    
    finally:
        # 【改善②】処理時間計測 - 終了時刻を記録して経過時間を計算
        end_time = time.time()
        elapsed_time = end_time - start_time
        performance_metrics['quality_check']['time'] = elapsed_time
        logger.info(f"⏱️ 【改善②】Quality Check処理時間: {elapsed_time:.2f}秒")
        
        # 【改善③】メモリ計測 - 終了時のメモリ使用量を記録
        mem_after = process.memory_info().rss / 1024 / 1024  # MB単位
        mem_used = mem_after - mem_before
        performance_metrics['quality_check']['memory'] = mem_used
        logger.info(f"💾 【改善③】Quality Check使用メモリ: {mem_used:.2f}MB")

# ========================================
# Load: データをPostgreSQLに保存
# ========================================
def load_to_postgres():
    """
    データをPostgreSQLに保存する関数
    エラーハンドリング: ファイル読み込みエラー、DB書き込みエラーに対応
    パフォーマンス改善: 時間・メモリ計測、改善効果サマリー出力
    """
    # 【改善②】処理時間計測 - 開始時刻を記録
    start_time = time.time()
    
    # 【改善③】メモリ計測 - 開始時のメモリ使用量を記録
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB単位
    
    try:
        logger.info("Starting data load to PostgreSQL")
        
        # CSVを読み込む
        df = pd.read_csv('/tmp/transformed_data.csv')
        logger.info(f"Loading {len(df)} rows to PostgreSQL")
        print("Data to load:")
        print(df)
        
        # データ検証
        if df.empty:
            raise ValueError("No data to load - DataFrame is empty")
        
        # PostgreSQLへの接続を作成
        engine = create_engine('postgresql://sourceuser:sourcepass@source-postgres:5432/sourcedb')
        logger.info("Database engine created")
        
        # データをPostgreSQLに保存
        df.to_sql('sales_summary', engine, if_exists='replace', index=False)
        logger.info(f"Successfully loaded {len(df)} rows to sales_summary table")
        
        # 接続を閉じる
        engine.dispose()
        logger.info("Database connection closed")
        
    except FileNotFoundError as e:
        logger.error(f"Input file not found: {e}")
        raise
    
    except ValueError as e:
        logger.error(f"Data validation error: {e}")
        raise
    
    except Exception as e:
        logger.error(f"Failed to load data to PostgreSQL: {e}")
        raise
    
    finally:
        # 【改善②】処理時間計測 - 終了時刻を記録して経過時間を計算
        end_time = time.time()
        elapsed_time = end_time - start_time
        performance_metrics['load']['time'] = elapsed_time
        logger.info(f"⏱️ 【改善②】Load処理時間: {elapsed_time:.2f}秒")
        
        # 【改善③】メモリ計測 - 終了時のメモリ使用量を記録
        mem_after = process.memory_info().rss / 1024 / 1024  # MB単位
        mem_used = mem_after - mem_before
        performance_metrics['load']['memory'] = mem_used
        logger.info(f"💾 【改善③】Load使用メモリ: {mem_used:.2f}MB")
        
        # ========================================
        # 【改善④】パフォーマンスサマリーを出力
        # ========================================
        logger.info("=" * 70)
        logger.info("📊 【改善④】パフォーマンス改善サマリー")
        logger.info("=" * 70)
        
        # 合計時間の計算
        total_time = (
            performance_metrics['extract']['time'] +
            performance_metrics['transform']['time'] +
            performance_metrics['quality_check']['time'] +
            performance_metrics['load']['time']
        )
        
        # 合計メモリの計算
        total_memory = (
            performance_metrics['extract']['memory'] +
            performance_metrics['transform']['memory'] +
            performance_metrics['quality_check']['memory'] +
            performance_metrics['load']['memory']
        )
        
        logger.info("⏱️ 処理時間:")
        logger.info(f"  - Extract:        {performance_metrics['extract']['time']:>8.2f}秒")
        logger.info(f"  - Transform:      {performance_metrics['transform']['time']:>8.2f}秒")
        logger.info(f"  - Quality Check:  {performance_metrics['quality_check']['time']:>8.2f}秒")
        logger.info(f"  - Load:           {performance_metrics['load']['time']:>8.2f}秒")
        logger.info(f"  - 合計:           {total_time:>8.2f}秒")
        logger.info("")
        logger.info("💾 メモリ使用量:")
        logger.info(f"  - Extract:        {performance_metrics['extract']['memory']:>8.2f}MB")
        logger.info(f"  - Transform:      {performance_metrics['transform']['memory']:>8.2f}MB")
        logger.info(f"  - Quality Check:  {performance_metrics['quality_check']['memory']:>8.2f}MB")
        logger.info(f"  - Load:           {performance_metrics['load']['memory']:>8.2f}MB")
        logger.info(f"  - 合計:           {total_memory:>8.2f}MB")
        logger.info("")
        logger.info("🎯 主な改善点:")
        logger.info("  ✅ 【改善①】クエリ最適化: SELECT * → SELECT id, sale_date, amount")
        logger.info("  ✅ 【改善②】処理時間計測: 各ステップの実行時間を記録")
        logger.info("  ✅ 【改善③】メモリ計測: 各ステップのメモリ使用量を記録")
        logger.info("=" * 70)

# ========================================
# DAG定義
# ========================================
with DAG(
    dag_id='basic_etl_pipeline_performance',
    default_args=default_args,
    start_date=datetime(2026, 1, 26),
    schedule='0 16 * * *',
    catchup=False,
    tags=['etl', 'postgres', 'performance']
) as dag:
    
    # タスク1: Extract（データ抽出）
    extract_task = PythonOperator(
        task_id='extract_from_postgres',
        python_callable=extract_from_postgres
    )
    
    # タスク2: Transform（データ変換）
    transform_task = PythonOperator(
        task_id='transform_sales_data',
        python_callable=transform_sales_data
    )
    
    # タスク3: Data Quality Check（データ品質チェック）
    quality_check_task = PythonOperator(
        task_id='check_data_quality',
        python_callable=check_data_quality
    )
    
    # タスク4: Load（データ保存）
    load_task = PythonOperator(
        task_id='load_to_postgres',
        python_callable=load_to_postgres
    )
    
    # タスクの依存関係を定義（実行順序）
    # Extract → Transform → Quality Check → Load
    extract_task >> transform_task >> quality_check_task >> load_task
