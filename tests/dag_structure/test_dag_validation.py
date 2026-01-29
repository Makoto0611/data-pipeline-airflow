"""
DAG構造テスト

このテストは以下を確認します：
1. DAGファイルがエラーなく読み込めるか
2. DAGオブジェクトが正しく作成されているか
3. タスクが定義されているか
"""

import pytest
from airflow.models import DagBag

# テストするDAGファイルのリスト
DAG_FILES = [
    "01_basic_etl_dag_base",
    "02_basic_etl_dag_error_handling",
    "03_basic_etl_dag_data_quality",
    "04_basic_etl_dag_performance"
]


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_loads_without_errors(init_airflow_db, dag_file):
    """DAGファイルがエラーなく読み込めるかテスト"""
    # 1. 準備：DagBagでDAGファイルを読み込む
    dag_bag = DagBag(include_examples=False)
    
    # 2. 検証：読み込みエラーがないか
    assert len(dag_bag.import_errors) == 0, f"DAG読み込みエラー: {dag_bag.import_errors}"
    
    # 3. 検証：DAGが存在するか
    # ファイル名から期待されるDAG IDを生成
    # 例: "01_basic_etl_dag_base" → "basic_etl_pipeline_base"
    dag_suffix = dag_file.replace("01_basic_etl_dag_", "").replace("02_basic_etl_dag_", "").replace("03_basic_etl_dag_", "").replace("04_basic_etl_dag_", "")
    dag_id = f"basic_etl_pipeline_{dag_suffix}"
    assert dag_id in dag_bag.dags, f"DAG {dag_id} が見つかりません"


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_has_tasks(init_airflow_db, dag_file):
    """DAGにタスクが定義されているかテスト"""
    # 1. 準備
    dag_bag = DagBag(include_examples=False)
    
    # ファイル名からDAG IDを生成
    dag_suffix = dag_file.replace("01_basic_etl_dag_", "").replace("02_basic_etl_dag_", "").replace("03_basic_etl_dag_", "").replace("04_basic_etl_dag_", "")
    dag_id = f"basic_etl_pipeline_{dag_suffix}"
    
    # 2. 実行：DAGを取得
    dag = dag_bag.get_dag(dag_id)
    
    # 3. 検証：タスクが存在するか
    assert dag is not None, f"DAG {dag_id} が見つかりません"
    assert len(dag.tasks) > 0, f"DAG {dag_id} にタスクがありません"
    assert len(dag.tasks) >= 3, f"DAG {dag_id} のタスク数が少なすぎます（期待: 3以上, 実際: {len(dag.tasks)}）"


@pytest.mark.parametrize("dag_file", DAG_FILES)
def test_dag_has_no_cycles(init_airflow_db, dag_file):
    """DAGに循環依存がないかテスト"""
    # 1. 準備
    dag_bag = DagBag(include_examples=False)
    
    # ファイル名からDAG IDを生成
    dag_suffix = dag_file.replace("01_basic_etl_dag_", "").replace("02_basic_etl_dag_", "").replace("03_basic_etl_dag_", "").replace("04_basic_etl_dag_", "")
    dag_id = f"basic_etl_pipeline_{dag_suffix}"
    
    # 2. 実行：DAGを取得
    dag = dag_bag.get_dag(dag_id)
    
    # 3. 検証：循環依存がないか
    # Airflowは内部で循環依存をチェックしており、
    # 循環があればDAG作成時にエラーになる
    assert dag is not None, f"DAG {dag_id} の作成に失敗（循環依存の可能性）"
