# ETLパイプライン実装 - エラーハンドリング版
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# Phase 3: エラーハンドリング機能を追加
# 学習日: 2026-01-21

"""
========================================
エラーハンドリング追加ポイント一覧
========================================

【追加①】ロギング機能
    場所: 12-13行目、各関数内
    内容: logger.info()とlogger.error()でログ出力
    効果: 処理の進行状況とエラー内容を記録

【追加②】自動リトライ設定
    場所: 30-36行目（default_args）
    内容: retries=3, retry_delay, exponential_backoff設定
    効果: 一時的なエラーからの自動復旧

【追加③】try-except-finallyブロック
    場所: 各関数（extract/transform/load）
    内容: エラーの種類ごとに適切な処理を実装
    効果: エラー時の適切なハンドリングとログ記録

【追加④】データ検証
    場所: transform関数（required_columns）、load関数（df.empty）
    内容: 処理前に必要なデータが揃っているか確認
    効果: 早期エラー検出とわかりやすいエラーメッセージ
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import pandas as pd
from sqlalchemy import create_engine
import logging

# 【追加①】ロガーの設定
logger = logging.getLogger(__name__)

# 【追加②】エラーハンドリング設定（全タスクに適用）
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
    【追加③】エラーハンドリング: DB接続エラー、クエリ実行エラーに対応
    """
    try:  # 【追加③】try-exceptブロックでエラーをキャッチ
        logger.info("Starting data extraction from PostgreSQL")  # 【追加①】ロギング
        
        # PostgreSQLに接続
        conn = psycopg2.connect(
            host="source-postgres",
            database="sourcedb",
            user="sourceuser",
            password="sourcepass",
            port=5432
        )
        logger.info("Successfully connected to PostgreSQL")  # 【追加①】ロギング
        
        # salesテーブルから全データを取得
        query = "SELECT * FROM sales"
        df = pd.read_sql(query, conn)
        
        # 接続を閉じる
        conn.close()
        
        # データ確認
        logger.info(f"Extracted {len(df)} rows")  # 【追加①】ロギング
        print(df.head())
        
        # CSVファイルに保存
        df.to_csv('/tmp/extracted_data.csv', index=False)
        logger.info("Data saved to /tmp/extracted_data.csv")  # 【追加①】ロギング
        
    except psycopg2.OperationalError as e:  # 【追加③】DB接続エラーをキャッチ
        logger.error(f"Database connection failed: {e}")  # 【追加①】エラーログ
        raise  # 【追加③】エラーを再度投げて上位に通知
    
    except psycopg2.DatabaseError as e:  # 【追加③】クエリ実行エラーをキャッチ
        logger.error(f"Database query failed: {e}")  # 【追加①】エラーログ
        raise  # 【追加③】エラーを再度投げて上位に通知
    
    except Exception as e:  # 【追加③】予期しないエラーをキャッチ
        logger.error(f"Unexpected error in extract: {e}")  # 【追加①】エラーログ
        raise  # 【追加③】エラーを再度投げて上位に通知

# ========================================
# Transform: データを加工する
# ========================================
def transform_sales_data():
    """
    データを変換する関数（日付別に集計）
    【追加③】エラーハンドリング: ファイル読み込みエラー、pandas処理エラーに対応
    """
    try:  # 【追加③】try-exceptブロック
        logger.info("Starting data transformation")  # 【追加①】ロギング
        
        # CSVを読み込む
        df = pd.read_csv('/tmp/extracted_data.csv')
        logger.info(f"Loaded {len(df)} rows for transformation")  # 【追加①】ロギング
        print("Original data:")
        print(df.head())
        
        # 【追加④】データ検証: 必要なカラムが存在するか確認
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
        logger.info("Transformed data saved to /tmp/transformed_data.csv")  # 【追加①】ロギング
        print("Transformed data:")
        print(transformed_df)
        
    except FileNotFoundError as e:  # 【追加③】ファイルが見つからないエラー
        logger.error(f"Input file not found: {e}")  # 【追加①】エラーログ
        raise
    
    except KeyError as e:  # 【追加③】必要なカラムが存在しない
        logger.error(f"Required column missing: {e}")  # 【追加①】エラーログ
        raise
    
    except ValueError as e:  # 【追加③】データ検証エラー
        logger.error(f"Data validation error: {e}")  # 【追加①】エラーログ
        raise
    
    except Exception as e:  # 【追加③】予期しないエラー
        logger.error(f"Unexpected error in transform: {e}")  # 【追加①】エラーログ
        raise

# ========================================
# Load: データをPostgreSQLに保存
# ========================================
def load_to_postgres():
    """
    データをPostgreSQLに保存する関数
    【追加③】エラーハンドリング: ファイル読み込みエラー、DB書き込みエラーに対応
    """
    try:  # 【追加③】try-exceptブロック
        logger.info("Starting data load to PostgreSQL")  # 【追加①】ロギング
        
        # CSVを読み込む
        df = pd.read_csv('/tmp/transformed_data.csv')
        logger.info(f"Loading {len(df)} rows to PostgreSQL")  # 【追加①】ロギング
        print("Data to load:")
        print(df)
        
        # 【追加④】データ検証: 空のDataFrameでないか確認
        if df.empty:
            raise ValueError("No data to load - DataFrame is empty")
        
        # PostgreSQLへの接続を作成
        engine = create_engine('postgresql://sourceuser:sourcepass@source-postgres:5432/sourcedb')
        logger.info("Database engine created")  # 【追加①】ロギング
        
        # データをPostgreSQLに保存
        df.to_sql('sales_summary', engine, if_exists='replace', index=False)
        logger.info(f"Successfully loaded {len(df)} rows to sales_summary table")  # 【追加①】ロギング
        
        # 接続を閉じる
        engine.dispose()
        logger.info("Database connection closed")  # 【追加①】ロギング
        
    except FileNotFoundError as e:  # 【追加③】ファイルが見つからない
        logger.error(f"Input file not found: {e}")  # 【追加①】エラーログ
        raise
    
    except ValueError as e:  # 【追加③】データ検証エラー
        logger.error(f"Data validation error: {e}")  # 【追加①】エラーログ
        raise
    
    except Exception as e:  # 【追加③】DB接続エラー、書き込みエラー等
        logger.error(f"Failed to load data to PostgreSQL: {e}")  # 【追加①】エラーログ
        raise

# ========================================
# DAG定義
# ========================================
with DAG(
    dag_id='basic_etl_pipeline_error_handling',
    default_args=default_args,  # 【追加②】エラーハンドリング設定を適用
    start_date=datetime(2026, 1, 21),
    schedule='0 16 * * *',
    catchup=False,
    tags=['etl', 'postgres', 'error-handling']
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
    
    # タスク3: Load（データ保存）
    load_task = PythonOperator(
        task_id='load_to_postgres',
        python_callable=load_to_postgres
    )
    
    # タスクの依存関係を定義（実行順序）
    extract_task >> transform_task >> load_task
