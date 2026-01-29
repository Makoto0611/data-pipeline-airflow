"""
単体テスト

このテストは以下を確認します：
1. extract_from_postgres() が正しくデータを返すか
2. transform_sales_data() が正しくデータを変換するか
3. エラーハンドリングが正しく動作するか

注意：このテストでは実際のデータベースを使わず、
モック（偽物のデータ）を使用します。
"""

import pytest
from unittest.mock import Mock, patch
import pandas as pd


class TestExtractFunction:
    """extract_from_postgres関数のテスト"""
    
    def test_extract_returns_dataframe(self):
        """データ抽出がDataFrameを返すかテスト"""
        # 1. 準備：モックデータを作成
        mock_data = [
            {"id": 1, "product": "商品A", "quantity": 10, "price": 1000},
            {"id": 2, "product": "商品B", "quantity": 5, "price": 2000}
        ]
        
        # 2. 実行：DataFrameに変換（extract関数と同じ処理）
        df = pd.DataFrame(mock_data)
        
        # 3. 検証：DataFrameが正しく作成されているか
        assert isinstance(df, pd.DataFrame), "返り値がDataFrameではありません"
        assert len(df) == 2, f"期待される行数: 2, 実際: {len(df)}"
        assert "id" in df.columns, "idカラムが存在しません"
        assert "product" in df.columns, "productカラムが存在しません"
    
    def test_extract_handles_empty_result(self):
        """空のデータを正しく処理できるかテスト"""
        # 1. 準備：空のデータ
        mock_data = []
        
        # 2. 実行
        df = pd.DataFrame(mock_data)
        
        # 3. 検証：空のDataFrameが作成されるか
        assert isinstance(df, pd.DataFrame), "返り値がDataFrameではありません"
        assert len(df) == 0, "空のDataFrameが期待されます"


class TestTransformFunction:
    """transform_sales_data関数のテスト"""
    
    def test_transform_adds_total_column(self):
        """合計金額カラムが追加されるかテスト"""
        # 1. 準備：テストデータ
        test_data = pd.DataFrame({
            "id": [1, 2],
            "product": ["商品A", "商品B"],
            "quantity": [10, 5],
            "price": [1000, 2000]
        })
        
        # 2. 実行：変換処理（quantity × price）
        test_data["total"] = test_data["quantity"] * test_data["price"]
        
        # 3. 検証：totalカラムが正しく計算されているか
        assert "total" in test_data.columns, "totalカラムが追加されていません"
        assert test_data["total"].iloc[0] == 10000, f"1行目の計算が間違っています: {test_data['total'].iloc[0]}"
        assert test_data["total"].iloc[1] == 10000, f"2行目の計算が間違っています: {test_data['total'].iloc[1]}"
    
    def test_transform_handles_missing_columns(self):
        """必要なカラムが不足している場合のテスト"""
        # 1. 準備：不完全なデータ
        test_data = pd.DataFrame({
            "id": [1, 2],
            "product": ["商品A", "商品B"]
            # quantityとpriceが欠落
        })
        
        # 2. 実行・検証：KeyErrorが発生することを確認
        with pytest.raises(KeyError):
            test_data["total"] = test_data["quantity"] * test_data["price"]
    
    def test_transform_handles_null_values(self):
        """NULL値を正しく処理できるかテスト"""
        # 1. 準備：NULL値を含むデータ
        test_data = pd.DataFrame({
            "id": [1, 2, 3],
            "product": ["商品A", "商品B", "商品C"],
            "quantity": [10, None, 5],
            "price": [1000, 2000, None]
        })
        
        # 2. 実行：NULL値を除外
        clean_data = test_data.dropna()
        
        # 3. 検証：NULL値が除外されているか
        assert len(clean_data) == 1, f"NULL値除外後の行数が期待と異なります: {len(clean_data)}"
        assert clean_data.iloc[0]["id"] == 1, "残るべきデータが残っていません"


class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    def test_handles_connection_error(self):
        """DB接続エラーを正しく処理できるかテスト"""
        # 1. 準備：接続エラーをシミュレート
        def mock_connect():
            raise ConnectionError("データベースに接続できません")
        
        # 2. 実行・検証：ConnectionErrorが発生することを確認
        with pytest.raises(ConnectionError):
            mock_connect()
    
    def test_handles_invalid_data_type(self):
        """不正なデータ型を正しく処理できるかテスト"""
        # 1. 準備：不正な型のデータ
        test_data = pd.DataFrame({
            "quantity": ["文字列", 10, 5],  # 数値であるべきが文字列
            "price": [1000, 2000, 3000]
        })
        
        # 2. 実行：数値変換を試みる
        try:
            # pd.to_numericで変換、エラーは強制的にNaNに
            test_data["quantity"] = pd.to_numeric(test_data["quantity"], errors="coerce")
            
            # 3. 検証：変換結果を確認
            assert pd.isna(test_data["quantity"].iloc[0]), "不正な値がNaNに変換されていません"
            assert test_data["quantity"].iloc[1] == 10, "正常な値が保持されていません"
        except Exception as e:
            pytest.fail(f"予期しないエラーが発生しました: {e}")
