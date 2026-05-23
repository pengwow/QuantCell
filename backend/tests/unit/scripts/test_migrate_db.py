"""数据库迁移脚本单元测试"""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


class TestGetDbPath:
    """测试 get_db_path 函数"""

    def test_get_db_path_found(self, tmp_path):
        """测试找到数据库文件"""
        from scripts.migrate_db import get_db_path

        db_file = tmp_path / "data" / "quantcell_sqlite.db"
        db_file.parent.mkdir(parents=True)
        db_file.write_text("")

        with patch("scripts.migrate_db.Path") as mock_path_cls:
            mock_instance = MagicMock()
            mock_instance.parent.parent = tmp_path
            mock_instance.__truediv__ = lambda self, other: tmp_path / other
            mock_path_cls.return_value = mock_instance

            result = get_db_path()
            assert result.exists() is True

    def test_get_db_path_not_found(self, tmp_path):
        """测试数据库文件不存在的情况"""
        from scripts.migrate_db import get_db_path

        mock_instance = MagicMock()
        mock_instance.exists.return_value = False
        mock_instance.parent.parent = mock_instance
        mock_instance.__truediv__ = MagicMock(return_value=mock_instance)

        with patch("scripts.migrate_db.Path", return_value=mock_instance):
            with pytest.raises(FileNotFoundError):
                get_db_path()


class TestCheckColumnExists:
    """测试 check_column_exists 函数"""

    def test_column_exists(self):
        """测试列已存在的情况"""
        from scripts.migrate_db import check_column_exists

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (0, "id", "INTEGER", 1, None, 1),
            (1, "name", "TEXT", 0, None, 0),
            (2, "parameters", "TEXT", 0, None, 0),
        ]
        mock_conn.execute.return_value = mock_cursor

        result = check_column_exists(mock_conn, "strategies", "parameters")
        assert result is True

    def test_column_not_exists(self):
        """测试列不存在的情况"""
        from scripts.migrate_db import check_column_exists

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (0, "id", "INTEGER", 1, None, 1),
            (1, "name", "TEXT", 0, None, 0),
        ]
        mock_conn.execute.return_value = mock_cursor

        result = check_column_exists(mock_conn, "strategies", "parameters")
        assert result is False


class TestMigrateStrategiesTable:
    """测试 migrate_strategies_table 函数"""

    def test_migrate_success(self):
        """测试迁移成功的情况"""
        from scripts.migrate_db import migrate_strategies_table

        mock_conn = MagicMock()

        with patch("scripts.migrate_db.check_column_exists", return_value=False):
            result = migrate_strategies_table(mock_conn)

        assert result is True
        mock_conn.execute.assert_called_once_with("ALTER TABLE strategies ADD COLUMN parameters TEXT")
        mock_conn.commit.assert_called_once()

    def test_migrate_skip_existing(self):
        """测试列已存在时跳过迁移"""
        from scripts.migrate_db import migrate_strategies_table

        mock_conn = MagicMock()

        with patch("scripts.migrate_db.check_column_exists", return_value=True):
            result = migrate_strategies_table(mock_conn)

        assert result is False
        mock_conn.execute.assert_not_called()
        mock_conn.commit.assert_not_called()


class TestMain:
    """测试 main 函数"""

    @patch("scripts.migrate_db.get_db_path")
    @patch("sqlite3.connect")
    def test_main_success(self, mock_connect, mock_get_db_path):
        """测试完整迁移流程成功"""
        from scripts.migrate_db import main

        mock_db_path = MagicMock()
        mock_db_path.__str__ = MagicMock(return_value="/fake/db/path.db")
        mock_get_db_path.return_value = mock_db_path

        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with patch("scripts.migrate_db.migrate_strategies_table", return_value=True):
            result = main()

        assert result == 0
        mock_connect.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("scripts.migrate_db.get_db_path")
    @patch("sqlite3.connect")
    def test_main_no_migration_needed(self, mock_connect, mock_get_db_path):
        """测试无需迁移的情况"""
        from scripts.migrate_db import main

        mock_db_path = MagicMock()
        mock_get_db_path.return_value = mock_db_path

        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with patch("scripts.migrate_db.migrate_strategies_table", return_value=False):
            result = main()

        assert result == 0
        mock_conn.close.assert_called_once()

    @patch("scripts.migrate_db.get_db_path")
    def test_main_db_not_found(self, mock_get_db_path):
        """测试数据库文件不存在"""
        from scripts.migrate_db import main

        mock_get_db_path.side_effect = FileNotFoundError("未找到数据库文件")

        result = main()
        assert result == 1

    @patch("scripts.migrate_db.get_db_path")
    @patch("sqlite3.connect")
    def test_main_sqlite_error(self, mock_connect, mock_get_db_path):
        """测试数据库操作错误"""
        from scripts.migrate_db import main

        mock_db_path = MagicMock()
        mock_get_db_path.return_value = mock_db_path
        mock_connect.side_effect = sqlite3.Error("数据库连接失败")

        result = main()
        assert result == 1

    @patch("scripts.migrate_db.get_db_path")
    @patch("sqlite3.connect")
    def test_main_unexpected_error(self, mock_connect, mock_get_db_path):
        """测试意外错误"""
        from scripts.migrate_db import main

        mock_db_path = MagicMock()
        mock_get_db_path.return_value = mock_db_path
        mock_connect.side_effect = Exception("未知错误")

        result = main()
        assert result == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
