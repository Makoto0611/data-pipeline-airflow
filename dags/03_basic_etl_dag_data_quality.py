# ETLパイプライン実装 - データ品質チェック版
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# Phase 3: データ品質チェック機能を追加
# 学習日: 2026-01-23

"""
========================================
データ品質チェック追加ポイント一覧
========================================

【追加①】check_data_quality関数の追加
    場所: 106-203行目付近
    内容: Transform後のデータ品質をチェックする関数
    効果: 不適切なデータがLoadされる前にエラーを検出

【追加②】4種類の品質チェック
    チェック①: データ件数チェック（データが0件でないか）
    チェック②: NULL値チェック（必須カラムにNULLがないか）
    チェック③: データ型チェック（カラムのデータ型が正しいか）
    チェック④: 異常値チェック（ビジネスロジック的におかしいデータがないか）

【追加③】品質チェックタスクのDAGへの組み込み
    場所: DAG定義部分
    内容: TransformとLoadの間にquality_check_taskを挿入
    効果: Extract → Transform → Quality Check → Load の順で実行

【追加④】エラー時のパイプライン停止
    内容: 品質チェック失敗時にValueErrorを発生させる
    効果: 不適切なデータがDBに保存されることを防ぐ
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import pandas as pd
from sqlalchemy import create_engine
import logging

# ロガーの設定
logger = logging.getLogger(__name__)

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
    """
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
        
        # salesテーブルから全データを取得
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

# ========================================
# Transform: データを加工する
# ========================================
def transform_sales_data():
    """
    データを変換する関数（日付別に集計）
    エラーハンドリング: ファイル読み込みエラー、pandas処理エラーに対応
    """
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

# ========================================
# Data Quality Check: データ品質チェック 【追加①】
# ========================================
def check_data_quality():  # 【追加①】新規関数
    """
    Transform後のデータ品質をチェックする関数
    
    チェック項目:
    1. データ件数チェック - データが0件でないか
    2. NULL値チェック - 必須カラムにNULLがないか
    3. データ型チェック - カラムのデータ型が正しいか
    4. 異常値チェック - ビジネスロジック的におかしいデータがないか
    
    問題があればValueErrorを投げてタスクを失敗させる
    """
    try:
        logger.info("Starting data quality checks")
        
        # Transform後のCSVを読み込む
        df = pd.read_csv('/tmp/transformed_data.csv')
        logger.info(f"Checking {len(df)} rows")
        
        # ========================================
        # 【追加②】チェック①: データ件数チェック
        # ========================================
        logger.info("Check 1/4: Row count check")
        if len(df) == 0:
            raise ValueError("❌ データが0件です！Extract/Transform処理を確認してください")
        logger.info(f"✓ 件数チェックOK: {len(df)}件のデータ")
        
        # ========================================
        # 【追加②】チェック②: NULL値チェック
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
        # 【追加②】チェック③: データ型チェック
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
        # 【追加②】チェック④: 異常値チェック
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

# ========================================
# Load: データをPostgreSQLに保存
# ========================================
def load_to_postgres():
    """
    データをPostgreSQLに保存する関数
    エラーハンドリング: ファイル読み込みエラー、DB書き込みエラーに対応
    """
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

# ========================================
# DAG定義
# ========================================
with DAG(
    dag_id='basic_etl_pipeline_data_quality',
    default_args=default_args,
    start_date=datetime(2026, 1, 23),
    schedule='0 16 * * *',
    catchup=False,
    tags=['etl', 'postgres', 'data-quality']
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
    
    # 【追加③】タスク3: Data Quality Check（データ品質チェック）
    quality_check_task = PythonOperator(  # 【追加③】新規タスク
        task_id='check_data_quality',
        python_callable=check_data_quality
    )
    
    # タスク4: Load（データ保存）
    load_task = PythonOperator(
        task_id='load_to_postgres',
        python_callable=load_to_postgres
    )
    
    # 【追加③】タスクの依存関係を定義（実行順序）
    # Extract → Transform → Quality Check → Load
    extract_task >> transform_task >> quality_check_task >> load_task  # 【追加③】Quality Checkを挿入
