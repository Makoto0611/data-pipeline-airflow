# 必要なライブラリをインポート
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

# DAGの定義
# with文を使うことで、この中で定義したタスクは自動的にこのDAGに紐付けられる
with DAG(
    dag_id='hello_world',  # DAGの一意な識別名（Airflow UIに表示される）
    start_date=datetime(2026, 1, 19),  # このDAGが実行可能になる開始日時
    schedule=None,  # 自動スケジュール実行なし（手動実行のみ）
    catchup=False,  # 過去の未実行分を実行しない
) as dag:
    # ここにタスクを定義する（次のステップ）
    hello_task = BashOperator(
        task_id='say_hello',
        bash_command='echo "Hello World"',
    )