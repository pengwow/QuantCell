"""Agent管理CLI单元测试"""

import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
from typer.testing import CliRunner


runner = CliRunner()


class TestAgentCliSession:
    """测试会话管理命令"""

    @patch("scripts.agent_cli.SessionManager")
    def test_session_list_empty(self, mock_sm_cls):
        """测试空会话列表"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.list_sessions.return_value = []
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "list"])
        assert result.exit_code == 0
        assert "暂无会话" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_list_with_data(self, mock_sm_cls):
        """测试有数据的会话列表"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.list_sessions.return_value = [
            {"key": "session-1", "updated_at": "2024-01-01T00:00:00"},
            {"key": "session-2", "updated_at": "2024-01-02T00:00:00"},
        ]
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "list"])
        assert result.exit_code == 0
        assert "session-1" in result.output
        assert "共 2 个会话" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_list_json(self, mock_sm_cls):
        """测试JSON格式输出"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.list_sessions.return_value = [{"key": "session-1"}]
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "list", "--format", "json"])
        assert result.exit_code == 0
        assert "\"key\"" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_info_found(self, mock_sm_cls):
        """测试会话信息存在"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.get_session_info.return_value = {
            "id": "session-1",
            "name": "测试会话",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
            "message_count": 5,
        }
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "info", "session-1"])
        assert result.exit_code == 0
        assert "session-1" in result.output
        assert "测试会话" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_info_not_found(self, mock_sm_cls):
        """测试会话信息不存在"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.get_session_info.return_value = None
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "info", "nonexistent"])
        assert result.exit_code == 1

    @patch("scripts.agent_cli.SessionManager")
    def test_session_create(self, mock_sm_cls):
        """测试创建会话"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.create_session.return_value = {"id": "session-new", "name": "新会话"}
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "create"])
        assert result.exit_code == 0
        assert "session-new" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_create_with_name(self, mock_sm_cls):
        """测试带名称创建会话"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.create_session.return_value = {"id": "session-new", "name": "自定义名称"}
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "create", "--name", "自定义名称"])
        assert result.exit_code == 0
        assert "自定义名称" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_delete_success(self, mock_sm_cls):
        """测试删除会话成功"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.delete.return_value = True
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "delete", "session-1", "--force"])
        assert result.exit_code == 0
        assert "已删除" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_delete_cancel(self, mock_sm_cls):
        """测试取消删除会话"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "delete", "session-1"], input="n\n")
        assert result.exit_code == 0
        assert "已取消" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_session_clear(self, mock_sm_cls):
        """测试清空会话"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["session", "clear", "session-1"])
        assert result.exit_code == 0
        assert "已清空" in result.output


class TestAgentCliTool:
    """测试工具管理命令"""

    @patch("scripts.agent_cli._get_tools_from_registry")
    def test_tool_list_empty(self, mock_get_tools):
        """测试空工具列表"""
        from scripts.agent_cli import app

        mock_get_tools.return_value = []

        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "暂无工具" in result.output

    @patch("scripts.agent_cli._get_tools_from_registry")
    def test_tool_list_with_data(self, mock_get_tools):
        """测试有数据的工具列表"""
        from scripts.agent_cli import app

        mock_get_tools.return_value = [
            {"name": "tool-1", "description": "工具1"},
            {"name": "tool-2", "description": "工具2"},
        ]

        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "tool-1" in result.output
        assert "工具1" in result.output

    @patch("scripts.agent_cli._get_tools_from_registry")
    def test_tool_list_json(self, mock_get_tools):
        """测试JSON格式输出"""
        from scripts.agent_cli import app

        mock_get_tools.return_value = [{"name": "tool-1"}]

        result = runner.invoke(app, ["tool", "list", "--format", "json"])
        assert result.exit_code == 0
        assert "\"name\"" in result.output

    @patch("scripts.agent_cli._get_tools_from_registry")
    def test_tool_info_found(self, mock_get_tools):
        """测试工具信息存在"""
        from scripts.agent_cli import app

        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.description = "工具描述"
        mock_tool.__class__.__name__ = "ToolClass"
        mock_tool.__class__.__module__ = "agent.tools"
        mock_tool.parameters = {
            "properties": {"param1": {"type": "string", "description": "参数1"}},
            "required": ["param1"]
        }
        mock_registry.tool_names = ["tool-1"]
        mock_registry.get.return_value = mock_tool

        with patch("agent.tools.create_registry", return_value=mock_registry):
            result = runner.invoke(app, ["tool", "info", "tool-1"])
            assert result.exit_code == 0
            assert "tool-1" in result.output
            assert "工具描述" in result.output

    @patch("scripts.agent_cli._get_tools_from_registry")
    def test_tool_info_not_found(self, mock_get_tools):
        """测试工具信息不存在"""
        from scripts.agent_cli import app

        mock_registry = MagicMock()
        mock_registry.tool_names = ["tool-1"]
        mock_registry.get.return_value = None

        with patch("agent.tools.create_registry", return_value=mock_registry):
            result = runner.invoke(app, ["tool", "info", "nonexistent"])
            assert result.exit_code == 1
            assert "不存在" in result.output


class TestAgentCliChat:
    """测试对话交互命令"""

    @patch("scripts.agent_cli.asyncio.run")
    def test_chat_send_success(self, mock_asyncio_run):
        """测试发送消息成功"""
        from scripts.agent_cli import app

        mock_asyncio_run.return_value = None

        result = runner.invoke(app, ["chat", "send", "你好"])
        assert result.exit_code == 0

    @patch("scripts.agent_cli.asyncio.run")
    def test_chat_send_init_failed(self, mock_asyncio_run):
        """测试Agent初始化失败"""
        from scripts.agent_cli import app

        mock_asyncio_run.side_effect = Exception("初始化失败")

        result = runner.invoke(app, ["chat", "send", "你好"])
        assert result.exit_code == 1

    @patch("scripts.agent_cli.SessionManager")
    def test_chat_history(self, mock_sm_cls):
        """测试查看历史消息"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.get_history.return_value = {
            "history": [
                {"role": "user", "content": "你好", "timestamp": "2024-01-01T00:00:00"},
                {"role": "assistant", "content": "你好！", "timestamp": "2024-01-01T00:00:01"},
            ],
            "total_messages": 2,
        }
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["chat", "history", "session-1"])
        assert result.exit_code == 0
        assert "用户:" in result.output
        assert "Agent:" in result.output

    @patch("scripts.agent_cli.SessionManager")
    def test_chat_history_empty(self, mock_sm_cls):
        """测试无历史消息"""
        from scripts.agent_cli import app

        mock_sm = MagicMock()
        mock_sm.get_history.return_value = {"history": [], "total_messages": 0}
        mock_sm_cls.return_value = mock_sm

        result = runner.invoke(app, ["chat", "history", "session-1"])
        assert result.exit_code == 0
        assert "暂无历史消息" in result.output


class TestAgentCliWorkspace:
    """测试工作空间管理命令"""

    @patch("scripts.agent_cli.asyncio.get_event_loop")
    def test_workspace_list(self, mock_get_loop):
        """测试列出工作空间文件"""
        from scripts.agent_cli import app

        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = json.dumps({
            "files": [{"name": "file1.py", "size": 100}],
            "directories": [{"name": "dir1"}]
        })
        mock_get_loop.return_value = mock_loop

        result = runner.invoke(app, ["workspace", "list"])
        assert result.exit_code == 0
        assert "file1.py" in result.output

    @patch("scripts.agent_cli.asyncio.get_event_loop")
    def test_workspace_list_empty(self, mock_get_loop):
        """测试空工作空间"""
        from scripts.agent_cli import app

        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = json.dumps({"files": [], "directories": []})
        mock_get_loop.return_value = mock_loop

        result = runner.invoke(app, ["workspace", "list"])
        assert result.exit_code == 0
        assert "空目录" in result.output

    @patch("scripts.agent_cli.asyncio.get_event_loop")
    def test_workspace_cat(self, mock_get_loop):
        """测试查看文件"""
        from scripts.agent_cli import app

        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = "文件内容"
        mock_get_loop.return_value = mock_loop

        with patch("scripts.agent_cli.WORKSPACE") as mock_workspace:
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_file.is_file.return_value = True
            mock_file.__str__ = MagicMock(return_value="/workspace/file.py")
            mock_workspace.__truediv__ = MagicMock(return_value=mock_file)

            result = runner.invoke(app, ["workspace", "cat", "file.py"])
            assert result.exit_code == 0
            assert "文件内容" in result.output

    def test_workspace_cat_not_found(self):
        """测试查看不存在的文件"""
        from scripts.agent_cli import app

        with patch("scripts.agent_cli.WORKSPACE") as mock_workspace:
            mock_file = MagicMock()
            mock_file.exists.return_value = False
            mock_workspace.__truediv__ = MagicMock(return_value=mock_file)

            result = runner.invoke(app, ["workspace", "cat", "nonexistent.py"])
            assert result.exit_code == 1

    def test_workspace_clean(self):
        """测试清理工作空间"""
        from scripts.agent_cli import app

        with patch("scripts.agent_cli.WORKSPACE") as mock_workspace:
            mock_workspace.iterdir.return_value = []

            result = runner.invoke(app, ["workspace", "clean", "--force"])
            assert result.exit_code == 0
            assert "已清理" in result.output

    def test_workspace_clean_cancel(self):
        """测试取消清理"""
        from scripts.agent_cli import app

        result = runner.invoke(app, ["workspace", "clean"], input="n\n")
        assert result.exit_code == 0
        assert "已取消" in result.output


class TestAgentCliParams:
    """测试参数管理命令"""

    @patch("agent.config.manager.ToolParamManager")
    def test_params_tools(self, mock_tpm_cls):
        """测试显示工具列表"""
        from scripts.agent_cli import app

        mock_tpm = MagicMock()
        mock_tpm.get_registered_tools.return_value = [
            {"name": "tool-1", "has_required_params": True, "configured_count": 2, "param_count": 3},
        ]
        mock_tpm_cls.return_value = mock_tpm

        result = runner.invoke(app, ["params", "tools"])
        assert result.exit_code == 0
        assert "已注册的工具" in result.output

    @patch("agent.config.manager.ToolParamManager")
    def test_params_show(self, mock_tpm_cls):
        """测试显示参数"""
        from scripts.agent_cli import app

        mock_tpm = MagicMock()
        mock_tpm.get_tool_params.return_value = {
            "api_key": {"value": "test-key", "sensitive": False, "source": "database", "type": "str", "description": "API密钥"},
        }
        mock_tpm_cls.return_value = mock_tpm

        result = runner.invoke(app, ["params", "show", "tool-1"])
        assert result.exit_code == 0
        assert "工具: tool-1" in result.output

    @patch("agent.config.manager.ToolParamManager.set_tool_param")
    def test_params_set(self, mock_set):
        """测试设置参数"""
        from scripts.agent_cli import app

        mock_set.return_value = True

        result = runner.invoke(app, ["params", "set", "tool-1", "api_key", "new-key"])
        assert result.exit_code == 0
        assert "已更新" in result.output

    @patch("agent.config.manager.ToolParamManager.set_tool_param")
    def test_params_set_failed(self, mock_set):
        """测试设置参数失败"""
        from scripts.agent_cli import app

        mock_set.side_effect = ValueError("更新失败")

        result = runner.invoke(app, ["params", "set", "tool-1", "api_key", "new-key"])
        assert result.exit_code == 1
        assert "更新失败" in result.output

    @patch("agent.config.manager.ToolParamManager.delete_tool_param")
    def test_params_delete(self, mock_delete):
        """测试删除参数"""
        from scripts.agent_cli import app

        mock_delete.return_value = True

        result = runner.invoke(app, ["params", "delete", "tool-1", "api_key"])
        assert result.exit_code == 0
        assert "已删除" in result.output

    @patch("agent.config.manager.ToolParamManager.delete_tool_param")
    def test_params_delete_failed(self, mock_delete):
        """测试删除参数失败"""
        from scripts.agent_cli import app

        mock_delete.return_value = False

        result = runner.invoke(app, ["params", "delete", "tool-1", "api_key"])
        assert result.exit_code == 1
        assert "不存在" in result.output

    @patch("agent.config.manager.ToolParamManager.import_config")
    @patch("builtins.open", new_callable=mock_open, read_data=b'{"tools": {"tool-1": {"api_key": "test"}}}')
    @patch("os.path.exists")
    def test_params_import(self, mock_exists, mock_file, mock_import):
        """测试从JSON导入参数"""
        from scripts.agent_cli import app

        mock_exists.return_value = True
        mock_import.return_value = (1, 0, [])

        result = runner.invoke(app, ["params", "import", "params.json"])
        assert result.exit_code == 0
        assert "导入完成" in result.output

    @patch("agent.config.manager.ToolParamManager.export_config")
    @patch("builtins.open", new_callable=mock_open)
    def test_params_export(self, mock_file, mock_export):
        """测试导出参数到JSON"""
        from scripts.agent_cli import app

        mock_export.return_value = {
            "export_time": "2024-01-01T00:00:00",
            "version": "1.0",
            "tools": {"tool-1": {"api_key": "test"}}
        }

        result = runner.invoke(app, ["params", "export"])
        assert result.exit_code == 0
        assert "已导出" in result.output

    @patch("agent.config.templates.get_tool_template")
    @patch("agent.config.tool_params.ToolParamResolver.resolve")
    def test_params_validate(self, mock_resolve, mock_get_template):
        """测试验证参数配置"""
        from scripts.agent_cli import app

        mock_get_template.return_value = {
            "api_key": {"required": True},
            "secret": {"required": False},
        }
        mock_resolve.return_value = "test-value"

        result = runner.invoke(app, ["params", "validate", "tool-1"])
        assert result.exit_code == 0
        assert "所有必要参数已正确配置" in result.output

    @patch("agent.config.templates.get_tool_template")
    @patch("agent.config.tool_params.ToolParamResolver.resolve")
    def test_params_validate_with_errors(self, mock_resolve, mock_get_template):
        """测试验证参数配置有错误"""
        from scripts.agent_cli import app

        mock_get_template.return_value = {
            "api_key": {"required": True},
        }
        mock_resolve.return_value = None

        result = runner.invoke(app, ["params", "validate", "tool-1"])
        assert result.exit_code == 0
        assert "未配置" in result.output


class TestAgentCliAction:
    """测试高级操作命令"""

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_generate_strategy(self, mock_run_tool):
        """测试策略生成"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = json.dumps({
            "success": True,
            "file_path": "/path/to/strategy.py",
            "code": "# 策略代码",
        })

        result = runner.invoke(app, ["action", "generate-strategy", "--requirement", "双均线策略", "--name", "ma_strategy"])
        assert result.exit_code == 0
        assert "策略代码已生成" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_analyze_backtest(self, mock_run_tool):
        """测试回测分析"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = json.dumps({"analysis": "分析结果", "success": True})

        result = runner.invoke(app, ["action", "analyze-backtest", "--backtest-id", "backtest-1"])
        assert result.exit_code == 0
        assert "分析结果" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_optimize_params(self, mock_run_tool):
        """测试参数优化"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = "优化结果"

        result = runner.invoke(app, ["action", "optimize-params", "--strategy-name", "strategy-1", "--param-ranges", "{}"])
        assert result.exit_code == 0
        assert "优化结果" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_diagnose(self, mock_run_tool):
        """测试策略诊断"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = json.dumps({"diagnosis": "诊断结果", "success": True})

        result = runner.invoke(app, ["action", "diagnose", "--strategy-name", "strategy-1"])
        assert result.exit_code == 0
        assert "诊断结果" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_fetch_market(self, mock_run_tool):
        """测试市场数据获取"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = json.dumps({"data": "市场数据", "success": True})

        result = runner.invoke(app, ["action", "fetch-market", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0
        assert "市场数据" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_deploy(self, mock_run_tool):
        """测试策略部署"""
        from scripts.agent_cli import app

        mock_run_tool.return_value = json.dumps({"status": "已部署", "success": True})

        result = runner.invoke(app, ["action", "deploy", "--strategy-name", "strategy-1", "--symbols", "BTCUSDT"])
        assert result.exit_code == 0
        assert "已部署" in result.output

    @patch("scripts.agent_cli._run_tool_async")
    def test_action_error(self, mock_run_tool):
        """测试高级操作错误"""
        from scripts.agent_cli import app

        mock_run_tool.side_effect = Exception("生成失败")

        result = runner.invoke(app, ["action", "generate-strategy", "--requirement", "测试", "--name", "test"])
        assert result.exit_code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
