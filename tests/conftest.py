"""
pytest共通設定ファイル

このファイルはすべてのテストで共通して使う設定を定義します。
- DAGファイルのパス設定
- Airflow環境変数の設定
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path

# DAGファイルがあるディレクトリをPythonのパスに追加
# tests/conftest.py から見て、親の親がプロジェクトルート
project_root = Path(__file__).parent.parent
dag_dir = project_root / "dags"

# Pythonがdagsディレクトリを見つけられるようにする
sys.path.insert(0, str(dag_dir))

# Airflowの環境変数を設定
os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = str(dag_dir)
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
os.environ["AIRFLOW__CORE__UNIT_TEST_MODE"] = "True"

# テスト用のAirflow設定
os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = "sqlite:////tmp/airflow_test.db"

@pytest.fixture(scope="module")
def init_airflow_db():
    """各テストの前にAirflowデータベースを初期化"""
    print("🔧 Airflow DB初期化開始...")  # デバッグ出力追加
    result = subprocess.run(
        ["airflow", "db", "migrate"],
        check=True,
        capture_output=True,
        text=True
    )
    print(f"✅ Airflow DB初期化完了: {result.returncode}")  # デバッグ出力追加
    yield
    # テスト後の処理が必要ならここに