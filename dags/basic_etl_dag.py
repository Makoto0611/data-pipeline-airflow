# ETLパイプライン実装
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# 学習日: 2026-01-20

from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import pandas as pd

# ========================================
# Extract: PostgreSQLからデータを抽出
# ========================================
# 役割: データソース（PostgreSQL）から販売データを取得
# 入力: なし
# 出力: /tmp/extracted_data.csv（次のTransform処理で使用）
def extract_from_postgres():
    # PostgreSQLに接続
    # source-postgres: docker-compose.ymlで定義されたサービス名
    conn = psycopg2.connect(
        host="source-postgres",
        database="sourcedb",
        user="sourceuser",
        password="sourcepass",
        port=5432
    )
    
    # salesテーブルから全データを取得
    # 実務では日付でフィルタリングすることが多い（例: WHERE sale_date >= '2026-01-01'）
    query = "SELECT * FROM sales"
    df = pd.read_sql(query, conn)
    
    # 接続を閉じる（リソース解放）
    conn.close()
    
    # データ確認（デバッグ用）
    print(f"Extracted {len(df)} rows")
    print(df.head())
    
    # CSVファイルに保存（次のTransform処理で使用）
    # index=False: pandasのインデックス（0,1,2...）をCSVに含めない
    df.to_csv('/tmp/extracted_data.csv', index=False)
    print("Data saved to /tmp/extracted_data.csv")

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
    # 1. Extract処理で保存したCSVを読み込む
    df = pd.read_csv('/tmp/extracted_data.csv')
    print(f"Loaded {len(df)} rows for transformation")
    print("Original data:")
    print(df.head())
    
    # 2. 日付でグループ化して集計
    # groupby('sale_date'): 同じ日付のデータをグループにまとめる
    # agg(): 各グループで集計処理を実行
    #   - 'amount': 'sum'  → 金額を合計（日次売上）
    #   - 'id': 'count'    → 行数をカウント（販売商品数）
    transformed_df = df.groupby('sale_date').agg({
        'amount': 'sum',    # 金額の合計
        'id': 'count'       # 商品数のカウント
    })
    # この時点でのデータ構造:
    #              amount  id
    # sale_date              
    # 2026-01-15   89800   1   ← sale_dateがIndex（行の名前）
    # 2026-01-16   11880   2

    # カラム名を分かりやすく変更
    # 'amount' → 'total_amount', 'id' → 'product_count'
    transformed_df.columns = ['total_amount', 'product_count']
    
    # reset_index(): sale_dateをIndexから普通のカラムに戻す
    # 理由: CSVやBigQueryに保存する時、全てのデータをカラムとして扱いたい
    # reset_index()後:
    #   sale_date  | total_amount | product_count
    #   2026-01-15 | 89800        | 1
    #   2026-01-16 | 11880        | 2
    transformed_df = transformed_df.reset_index()

    # 3. 結果を保存（次のLoad処理で使用）
    transformed_df.to_csv('/tmp/transformed_data.csv', index=False)
    print("Transformed data saved to /tmp/transformed_data.csv")
    print("Transformed data:")
    print(transformed_df)

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
    start_date=datetime(2026, 1, 20),
    schedule=None,  # 手動実行（実務では '@daily' などを指定）
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
    
    # タスクの依存関係を定義（実行順序）
    # extract_task >> transform_task: Extractが成功したらTransformを実行
    # 実務では: extract_task >> transform_task >> load_task
    extract_task >> transform_task