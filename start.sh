#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# --- 1. .env の確認・作成 ---
# AIRFLOW_UID が無いと、airflow-init の chown が効かず、
# logs/dags/plugins/config が root 所有のまま残ってしまい、
# scheduler/webserver が PermissionError で起動失敗する（2026-06-16に発生した問題）。
if [ ! -f .env ]; then
  echo "[start.sh] .env が無いので新規作成します"
  cat > .env << EOF
POSTGRES_USER=airflow
POSTGRES_PASSWORD=airflow
POSTGRES_DB=airflow
AIRFLOW_UID=$(id -u)
EOF
elif ! grep -q "^AIRFLOW_UID=" .env; then
  echo "[start.sh] .env に AIRFLOW_UID が無いので追記します"
  # 末尾に改行が無いファイルに直接 >> すると前の行と連結してしまうため、
  # 先に改行だけ追加してから追記する
  echo "" >> .env
  echo "AIRFLOW_UID=$(id -u)" >> .env
fi

# --- 2. 必要なディレクトリを事前に作成 ---
# Docker に自動生成させると、root 所有・権限666 のような
# 中途半端な状態で作られることがあるため、先に自分で用意しておく。
mkdir -p logs dags plugins config

# --- 3. Airflow起動 ---
echo "[start.sh] docker-compose up -d を実行します"
docker-compose up -d

echo "[start.sh] 起動コマンドを実行しました。30秒ほど待ってから http://localhost:8080 にアクセスしてください。"
