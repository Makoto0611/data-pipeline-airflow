# ETLパイプライン実装
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# 学習日: 2026-01-20

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
# 役割: データソース（PostgreSQL）から販売データを取得
# 入力: なし
# 出力: /tmp/extracted_data.csv（次のTransform処理で使用）
def extract_from_postgres():
    """
    PostgreSQLからデータを抽出する関数
    エラーハンドリング: DB接続エラー、クエリ実行エラーに対応
    """
    try:
        logger.info("Starting data extraction from PostgreSQL")
        
        # PostgreSQLに接続
        # source-postgres: docker-compose.ymlで定義されたサービス名
        conn = psycopg2.connect(
            host="source-postgres",
            database="sourcedb",
            user="sourceuser",
            password="sourcepass",
            port=5432
        )
        logger.info("Successfully connected to PostgreSQL")
        
        # salesテーブルから全データを取得
        # 実務では日付でフィルタリングすることが多い（例: WHERE sale_date >= '2026-01-01'）
        query = "SELECT * FROM sales"
        df = pd.read_sql(query, conn)
        
        # 接続を閉じる（リソース解放）
        conn.close()
        
        # データ確認（デバッグ用）
        logger.info(f"Extracted {len(df)} rows")
        print(df.head())
        
        # CSVファイルに保存（次のTransform処理で使用）
        # index=False: pandasのインデックス（0,1,2...）をCSVに含めない
        df.to_csv('/tmp/extracted_data.csv', index=False)
        logger.info("Data saved to /tmp/extracted_data.csv")
        
    except psycopg2.OperationalError as e:
        # DB接続エラー（サーバーダウン、ネットワークエラー等）
        logger.error(f"Database connection failed: {e}")
        raise  # Airflowに例外を投げてリトライさせる
    
    except psycopg2.DatabaseError as e:
        # クエリ実行エラー（テーブルが存在しない、権限エラー等）
        logger.error(f"Database query failed: {e}")
        raise
    
    except Exception as e:
        # その他の予期しないエラー
        logger.error(f"Unexpected error in extract: {e}")
        raise

# ========================================
# Transform: データを加工する
# ========================================
# 役割: 日付別に売上を集計（個別商品データ → 日次集計データ）
# 入力: /tmp/extracted_data.csv（Extract処理の出力）
# 出力: /tmp/transformed_data.csv（日付別の集計データ）
# 
# データの変化:
# 【変換前】5行の個別商品データ
#   id | product_name | amount | sale_date
#   1  | ノートPC     | 89800  | 2026-01-15
#   2  | マウス       | 2980   | 2026-01-16
#   3  | キーボード   | 8900   | 2026-01-16
# 
# 【変換後】4行の日次集計データ
#   sale_date  | total_amount | product_count
#   2026-01-15 | 89800        | 1
#   2026-01-16 | 11880        | 2  ← 2980 + 8900
def transform_sales_data():
    """
    データを変換する関数（日付別に集計）
    エラーハンドリング: ファイル読み込みエラー、pandas処理エラーに対応
    """
    try:
        logger.info("Starting data transformation")
        
        # 1. Extract処理で保存したCSVを読み込む
        df = pd.read_csv('/tmp/extracted_data.csv')
        logger.info(f"Loaded {len(df)} rows for transformation")
        print("Original data:")
        print(df.head())
        
        # データ検証: 必要なカラムが存在するか確認
        required_columns = ['sale_date', 'amount', 'id']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # 2. 日付でグループ化して集計
        # groupby('sale_date'): 同じ日付のデータをグループにまとめる
        # agg(): 各グループで集計処理を実行
        #   - 'amount': 'sum'  → 金額を合計（日次売上）
        #   - 'id': 'count'    → 行数をカウント（販売商品数）
        transformed_df = df.groupby('sale_date').agg({
            'amount': 'sum',    # 金額の合計
            'id': 'count'       # 商品数のカウント
        })

        # カラム名を分かりやすく変更
        # 'amount' → 'total_amount', 'id' → 'product_count'
        transformed_df.columns = ['total_amount', 'product_count']
        
        # reset_index(): sale_dateをIndexから普通のカラムに戻す
        transformed_df = transformed_df.reset_index()

        # 3. 結果を保存（次のLoad処理で使用）
        transformed_df.to_csv('/tmp/transformed_data.csv', index=False)
        logger.info("Transformed data saved to /tmp/transformed_data.csv")
        print("Transformed data:")
        print(transformed_df)
        
    except FileNotFoundError as e:
        # 前のタスク（Extract）が失敗してファイルが存在しない
        logger.error(f"Input file not found: {e}")
        raise
    
    except KeyError as e:
        # 必要なカラムが存在しない
        logger.error(f"Required column missing: {e}")
        raise
    
    except ValueError as e:
        # データ型エラーや値の問題
        logger.error(f"Data validation error: {e}")
        raise
    
    except Exception as e:
        # その他の予期しないエラー
        logger.error(f"Unexpected error in transform: {e}")
        raise

# ========================================
# Load: データをPostgreSQLに保存
# ========================================
# 役割: 集計データをsales_summaryテーブルに保存
# 入力: /tmp/transformed_data.csv（Transform処理の出力）
# 出力: PostgreSQLのsales_summaryテーブルにデータを格納
# 
# 保存方針:
#   今回は「全データ置き換え」方式（if_exists='replace'）
#   理由: シンプルで実装しやすく、学習に最適
#   実務では「UPSERT」（既存データは更新、新規は追加）が望ましい
#   ※UPSERTはPhase 3で学習予定
def load_to_postgres():
    """
    データをPostgreSQLに保存する関数
    エラーハンドリング: ファイル読み込みエラー、DB書き込みエラーに対応
    """
    try:
        logger.info("Starting data load to PostgreSQL")
        
        # 1. Transform処理で作成したCSVを読み込む
        df = pd.read_csv('/tmp/transformed_data.csv')
        logger.info(f"Loading {len(df)} rows to PostgreSQL")
        print("Data to load:")
        print(df)
        
        # データ検証: 空のDataFrameでないか確認
        if df.empty:
            raise ValueError("No data to load - DataFrame is empty")
        
        # 2. PostgreSQLへの接続を作成
        engine = create_engine('postgresql://sourceuser:sourcepass@source-postgres:5432/sourcedb')
        logger.info("Database engine created")
        
        # 3. データをPostgreSQLに保存
        df.to_sql('sales_summary', engine, if_exists='replace', index=False)
        logger.info(f"Successfully loaded {len(df)} rows to sales_summary table")
        
        # 4. 接続を閉じる（リソース解放）
        engine.dispose()
        logger.info("Database connection closed")
        
    except FileNotFoundError as e:
        # 前のタスク（Transform）が失敗してファイルが存在しない
        logger.error(f"Input file not found: {e}")
        raise
    
    except ValueError as e:
        # データが空など、値の問題
        logger.error(f"Data validation error: {e}")
        raise
    
    except Exception as e:
        # DB接続エラー、書き込みエラー等
        logger.error(f"Failed to load data to PostgreSQL: {e}")
        raise

# ========================================
# DAG定義
# ========================================
# DAG (Directed Acyclic Graph): タスクの実行順序を定義
# dag_id: Airflow UIで表示される名前
# start_date: DAGの開始日（過去の日付でOK）
# schedule: 実行スケジュール（None=手動実行のみ）
# catchup: False=過去分を遡って実行しない
with DAG(
    dag_id='basic_etl_pipeline',
    default_args=default_args,  # エラーハンドリング設定を適用
    start_date=datetime(2026, 1, 20),
    schedule='0 16 * * *',
    catchup=False,
    tags=['etl', 'postgres', 'bigquery']
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
    # extract_task >> transform_task >> load_task: Extract→Transform→Loadの順に実行
    extract_task >> transform_task >> load_task

