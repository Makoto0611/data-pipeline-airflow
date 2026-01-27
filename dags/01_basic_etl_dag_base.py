# ETLパイプライン実装 - 基本版（Phase 2完成版）
# 目的: PostgreSQLのsalesデータを日付別に集計してBigQueryへ送る
# 学習日: 2026-01-20

"""
========================================
基本実装の内容
========================================

このファイルは最もシンプルなETLパイプラインの実装です。
エラーハンドリング、データ品質チェック、パフォーマンス改善などは
含まれていません。

実装内容:
- Extract: PostgreSQLからデータを抽出
- Transform: 日付別に集計
- Load: PostgreSQLに保存

これがベースラインとなり、以降のファイルで段階的に機能を追加していきます。
"""

from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
import psycopg2
import pandas as pd
from sqlalchemy import create_engine

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
    # 1. Transform処理で作成したCSVを読み込む
    # このCSVには日付別の集計データ（date, total_amount, product_count）が入っている
    df = pd.read_csv('/tmp/transformed_data.csv')
    print(f"Loading {len(df)} rows to PostgreSQL")
    print("Data to load:")
    print(df)
    
    # 2. PostgreSQLへの接続を作成
    # SQLAlchemy: データベース接続を統一的に扱うライブラリ
    # create_engine(): 接続情報からengineオブジェクトを作成
    # 
    # 接続文字列の形式: postgresql://ユーザー名:パスワード@ホスト:ポート/データベース名
    # - sourceuser: PostgreSQLのユーザー名
    # - sourcepass: パスワード
    # - source-postgres: Dockerコンテナのサービス名（docker-compose.ymlで定義）
    # - 5432: PostgreSQLのデフォルトポート
    # - sourcedb: データベース名
    engine = create_engine('postgresql://sourceuser:sourcepass@source-postgres:5432/sourcedb')
    
    # 3. データをPostgreSQLに保存
    # df.to_sql(): pandasのDataFrameをSQLテーブルに保存
    # 
    # パラメータ説明:
    # - 'sales_summary': 保存先のテーブル名
    # - engine: PostgreSQL接続情報
    # - if_exists='replace': テーブルが既に存在する場合の動作
    #   * 'fail': エラーを出す（デフォルト）
    #   * 'replace': テーブルを削除して作り直す（全データ置き換え）← 今回はこれ
    #   * 'append': 既存データに追加（重複チェックなし）
    # - index=False: pandasのインデックス（0,1,2...）をテーブルに含めない
    # 
    # 今回'replace'を選んだ理由:
    #   - シンプルで確実にデータが更新される
    #   - 集計データは毎回全て再計算するので、全置き換えでOK
    #   - 欠点: 一瞬データが消える（実務では問題になる可能性）
    # 
    # より良い方法（Phase 3で学習）:
    #   - UPSERT: 既存の日付は更新、新しい日付は追加
    #   - トランザクション: エラー時はロールバック（元に戻す）
    df.to_sql('sales_summary', engine, if_exists='replace', index=False)
    
    print(f"Successfully loaded {len(df)} rows to sales_summary table")
    
    # 4. 接続を閉じる（リソース解放）
    engine.dispose()

# ========================================
# DAG定義
# ========================================
# DAG (Directed Acyclic Graph): タスクの実行順序を定義
# dag_id: Airflow UIで表示される名前
# start_date: DAGの開始日（過去の日付でOK）
# schedule: 実行スケジュール（None=手動実行のみ）
# catchup: False=過去分を遡って実行しない
with DAG(
    dag_id='basic_etl_pipeline_base',
    start_date=datetime(2026, 1, 20),
    schedule='0 16 * * *',
    catchup=False,
    tags=['etl', 'postgres', 'base']
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

