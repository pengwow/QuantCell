"""Agent管理CLI单元测试

当前口径：`tool` / `params` 为真实功能；`session` / `chat` / `workspace` / `action`
未实现，必须显式失败（非 0 退出码 + 提示语），不允许静默 no-op 或假成功输出。
"""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestAgentCliSession:
    """会话命令：显式未实现（不静默）"""

    @pytest.mark.parametrize(
        "args",
        [
            ["session", "list"],
            ["session", "list", "--format", "json"],
            ["session", "info", "session-1"],
            ["session", "create", "--name", "自定义名称"],
            ["session", "delete", "session-1", "--force"],
            ["session", "delete", "session-1"],
            ["session", "clear", "session-1"],
        ],
    )
    def test_session_commands_fail_explicitly(self, args):
        """任何 session 子命令都必须非 0 退出并提示未实现"""
        from cli.agent import app

        result = runner.invoke(app, args)

        assert result.exit_code == 1
        assert "未实现" in result.output
        # 提示语必须指向可用替代路径，而不是留个死胡同
        assert "agent/session/manager.py" in result.output

    def test_session_help_lists_all_commands(self):
        """命令注册面不因实现清空而减少"""
        from cli.agent import app

        result = runner.invoke(app, ["session", "--help"])

        assert result.exit_code == 0
        for cmd in ("list", "info", "create", "delete", "clear"):
            assert cmd in result.output


class TestAgentCliSurface:
    """命令组注册面冒烟"""

    def test_agent_help_lists_subcommand_groups(self):
        from cli.agent import app

        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        for group in ("session", "tool", "chat", "workspace", "params", "action"):
            assert group in result.output

    def test_params_help_lists_commands(self):
        from cli.agent import app

        result = runner.invoke(app, ["params", "--help"])

        assert result.exit_code == 0
        assert "tools" in result.output


class TestAgentCliTool:
    """测试工具管理命令"""

    @patch("cli.agent._get_tools_from_registry")
    def test_tool_list_empty(self, mock_get_tools):
        """测试空工具列表"""
        from cli.agent import app

        mock_get_tools.return_value = []

        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "暂无工具" in result.output

    @patch("cli.agent._get_tools_from_registry")
    def test_tool_list_with_data(self, mock_get_tools):
        """测试有数据的工具列表"""
        from cli.agent import app

        mock_get_tools.return_value = [
            {"name": "tool-1", "description": "工具1"},
            {"name": "tool-2", "description": "工具2"},
        ]

        result = runner.invoke(app, ["tool", "list"])
        assert result.exit_code == 0
        assert "tool-1" in result.output
        assert "工具1" in result.output

    @patch("cli.agent._get_tools_from_registry")
    def test_tool_list_json(self, mock_get_tools):
        """测试JSON格式输出"""
        from cli.agent import app

        mock_get_tools.return_value = [{"name": "tool-1"}]

        result = runner.invoke(app, ["tool", "list", "--format", "json"])
        assert result.exit_code == 0
        assert '"name"' in result.output

    @patch("cli.agent._get_tools_from_registry")
    def test_tool_info_found(self, mock_get_tools):
        """测试工具信息存在"""
        from cli.agent import app

        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.description = "工具描述"
        mock_tool.__class__.__name__ = "ToolClass"
        mock_tool.__class__.__module__ = "agent.tools"
        mock_tool.parameters = {
            "properties": {"param1": {"type": "string", "description": "参数1"}},
            "required": ["param1"],
        }
        mock_registry.tool_names = ["tool-1"]
        mock_registry.get.return_value = mock_tool

        with patch("agent.tools.create_registry", return_value=mock_registry):
            result = runner.invoke(app, ["tool", "info", "tool-1"])
            assert result.exit_code == 0
            assert "tool-1" in result.output
            assert "工具描述" in result.output

    @patch("cli.agent._get_tools_from_registry")
    def test_tool_info_not_found(self, mock_get_tools):
        """测试工具信息不存在"""
        from cli.agent import app

        mock_registry = MagicMock()
        mock_registry.tool_names = ["tool-1"]
        mock_registry.get.return_value = None

        with patch("agent.tools.create_registry", return_value=mock_registry):
            result = runner.invoke(app, ["tool", "info", "nonexistent"])
            assert result.exit_code == 1
            assert "不存在" in result.output


class TestAgentCliChat:
    """对话命令：显式未实现（不静默）"""

    def test_chat_send_fails_explicitly(self):
        """chat send 不再打印「消息已发送」假成功"""
        from cli.agent import app

        result = runner.invoke(app, ["chat", "send", "你好"])

        assert result.exit_code == 1
        assert "未实现" in result.output
        assert "消息已发送" not in result.output
        assert "/api/v1/agent/chat/stream" in result.output

    def test_chat_send_with_session_fails_explicitly(self):
        from cli.agent import app

        result = runner.invoke(app, ["chat", "send", "你好", "--session", "session-1"])

        assert result.exit_code == 1
        assert "未实现" in result.output

    def test_chat_history_fails_explicitly(self):
        """chat history 不再返回恒空历史"""
        from cli.agent import app

        result = runner.invoke(app, ["chat", "history", "session-1"])

        assert result.exit_code == 1
        assert "未实现" in result.output
        assert "暂无历史消息" not in result.output

    def test_chat_help_lists_commands(self):
        from cli.agent import app

        result = runner.invoke(app, ["chat", "--help"])

        assert result.exit_code == 0
        assert "send" in result.output


class TestAgentCliWorkspace:
    """工作空间命令：显式未实现（不静默）"""

    def test_workspace_list_fails_explicitly(self):
        """workspace list 不再返回恒空目录"""
        from cli.agent import app

        result = runner.invoke(app, ["workspace", "list"])

        assert result.exit_code == 1
        assert "未实现" in result.output
        assert "空目录" not in result.output

    def test_workspace_cat_fails_explicitly(self):
        from cli.agent import app

        result = runner.invoke(app, ["workspace", "cat", "file.py"])

        assert result.exit_code == 1
        assert "未实现" in result.output

    def test_workspace_cat_missing_file_not_misreported(self):
        """不再用「文件不存在」掩盖功能缺失（backend/workspace 根本不存在）"""
        from cli.agent import app

        result = runner.invoke(app, ["workspace", "cat", "nonexistent.py"])

        assert result.exit_code == 1
        assert "不存在" not in result.output
        assert "未实现" in result.output

    def test_workspace_help_lists_commands(self):
        from cli.agent import app

        result = runner.invoke(app, ["workspace", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output

    def test_workspace_clean(self):
        """workspace clean 仍走真实文件操作（未被下架）"""
        from cli.agent import app

        with patch("cli.agent.WORKSPACE") as mock_workspace:
            mock_workspace.iterdir.return_value = []

            result = runner.invoke(app, ["workspace", "clean", "--force"])
            assert result.exit_code == 0
            assert "已清理" in result.output

    def test_workspace_clean_cancel(self):
        """测试取消清理"""
        from cli.agent import app

        result = runner.invoke(app, ["workspace", "clean"], input="n\n")
        assert result.exit_code == 0
        assert "已取消" in result.output


class TestAgentCliParams:
    """测试参数管理命令"""

    @patch("agent.config.manager.ToolParamManager")
    def test_params_tools(self, mock_tpm_cls):
        """测试显示工具列表"""
        from cli.agent import app

        mock_tpm = MagicMock()
        mock_tpm.get_registered_tools.return_value = [
            {
                "name": "tool-1",
                "has_required_params": True,
                "configured_count": 2,
                "param_count": 3,
            },
        ]
        mock_tpm_cls.return_value = mock_tpm

        result = runner.invoke(app, ["params", "tools"])
        assert result.exit_code == 0
        assert "已注册的工具" in result.output

    @patch("agent.config.manager.ToolParamManager")
    def test_params_show(self, mock_tpm_cls):
        """测试显示参数"""
        from cli.agent import app

        mock_tpm = MagicMock()
        mock_tpm.get_tool_params.return_value = {
            "api_key": {
                "value": "test-key",
                "sensitive": False,
                "source": "database",
                "type": "str",
                "description": "API密钥",
            },
        }
        mock_tpm_cls.return_value = mock_tpm

        result = runner.invoke(app, ["params", "show", "tool-1"])
        assert result.exit_code == 0
        assert "工具: tool-1" in result.output

    @patch("agent.config.manager.ToolParamManager.set_tool_param")
    def test_params_set(self, mock_set):
        """测试设置参数"""
        from cli.agent import app

        mock_set.return_value = True

        result = runner.invoke(app, ["params", "set", "tool-1", "api_key", "new-key"])
        assert result.exit_code == 0
        assert "已更新" in result.output

    @patch("agent.config.manager.ToolParamManager.set_tool_param")
    def test_params_set_failed(self, mock_set):
        """测试设置参数失败"""
        from cli.agent import app

        mock_set.side_effect = ValueError("更新失败")

        result = runner.invoke(app, ["params", "set", "tool-1", "api_key", "new-key"])
        assert result.exit_code == 1
        assert "更新失败" in result.output

    @patch("agent.config.manager.ToolParamManager.delete_tool_param")
    def test_params_delete(self, mock_delete):
        """测试删除参数"""
        from cli.agent import app

        mock_delete.return_value = True

        result = runner.invoke(app, ["params", "delete", "tool-1", "api_key"])
        assert result.exit_code == 0
        assert "已删除" in result.output

    @patch("agent.config.manager.ToolParamManager.delete_tool_param")
    def test_params_delete_failed(self, mock_delete):
        """测试删除参数失败"""
        from cli.agent import app

        mock_delete.return_value = False

        result = runner.invoke(app, ["params", "delete", "tool-1", "api_key"])
        assert result.exit_code == 1
        assert "不存在" in result.output

    @patch("agent.config.manager.ToolParamManager.import_config")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=b'{"tools": {"tool-1": {"api_key": "test"}}}',
    )
    @patch("os.path.exists")
    def test_params_import(self, mock_exists, mock_file, mock_import):
        """测试从JSON导入参数"""
        from cli.agent import app

        mock_exists.return_value = True
        mock_import.return_value = (1, 0, [])

        result = runner.invoke(app, ["params", "import", "params.json"])
        assert result.exit_code == 0
        assert "导入完成" in result.output

    @patch("agent.config.manager.ToolParamManager.export_config")
    @patch("builtins.open", new_callable=mock_open)
    def test_params_export(self, mock_file, mock_export):
        """测试导出参数到JSON"""
        from cli.agent import app

        mock_export.return_value = {
            "export_time": "2024-01-01T00:00:00",
            "version": "1.0",
            "tools": {"tool-1": {"api_key": "test"}},
        }

        result = runner.invoke(app, ["params", "export"])
        assert result.exit_code == 0
        assert "已导出" in result.output

    @patch("agent.config.templates.get_tool_template")
    @patch("agent.config.tool_params.ToolParamResolver.resolve")
    def test_params_validate(self, mock_resolve, mock_get_template):
        """测试验证参数配置"""
        from cli.agent import app

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
        from cli.agent import app

        mock_get_template.return_value = {
            "api_key": {"required": True},
        }
        mock_resolve.return_value = None

        result = runner.invoke(app, ["params", "validate", "tool-1"])
        assert result.exit_code == 0
        assert "未配置" in result.output


class TestAgentCliAction:
    """测试高级操作命令"""

    @patch("cli.agent._run_tool_async")
    def test_action_generate_strategy(self, mock_run_tool):
        """测试策略生成"""
        from cli.agent import app

        mock_run_tool.return_value = json.dumps(
            {
                "success": True,
                "file_path": "/path/to/strategy.py",
                "code": "# 策略代码",
            }
        )

        result = runner.invoke(
            app,
            [
                "action",
                "generate-strategy",
                "--requirement",
                "双均线策略",
                "--name",
                "ma_strategy",
            ],
        )
        assert result.exit_code == 0
        assert "策略代码已生成" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_analyze_backtest(self, mock_run_tool):
        """测试回测分析"""
        from cli.agent import app

        mock_run_tool.return_value = json.dumps({"analysis": "分析结果", "success": True})

        result = runner.invoke(app, ["action", "analyze-backtest", "--backtest-id", "backtest-1"])
        assert result.exit_code == 0
        assert "分析结果" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_optimize_params(self, mock_run_tool):
        """测试参数优化"""
        from cli.agent import app

        mock_run_tool.return_value = "优化结果"

        result = runner.invoke(
            app,
            [
                "action",
                "optimize-params",
                "--strategy-name",
                "strategy-1",
                "--param-ranges",
                "{}",
            ],
        )
        assert result.exit_code == 0
        assert "优化结果" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_diagnose(self, mock_run_tool):
        """测试策略诊断"""
        from cli.agent import app

        mock_run_tool.return_value = json.dumps({"diagnosis": "诊断结果", "success": True})

        result = runner.invoke(app, ["action", "diagnose", "--strategy-name", "strategy-1"])
        assert result.exit_code == 0
        assert "诊断结果" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_fetch_market(self, mock_run_tool):
        """测试市场数据获取"""
        from cli.agent import app

        mock_run_tool.return_value = json.dumps({"data": "市场数据", "success": True})

        result = runner.invoke(app, ["action", "fetch-market", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0
        assert "市场数据" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_deploy(self, mock_run_tool):
        """测试策略部署"""
        from cli.agent import app

        mock_run_tool.return_value = json.dumps({"status": "已部署", "success": True})

        result = runner.invoke(
            app,
            [
                "action",
                "deploy",
                "--strategy-name",
                "strategy-1",
                "--symbols",
                "BTCUSDT",
            ],
        )
        assert result.exit_code == 0
        assert "已部署" in result.output

    @patch("cli.agent._run_tool_async")
    def test_action_error(self, mock_run_tool):
        """测试高级操作错误"""
        from cli.agent import app

        mock_run_tool.side_effect = Exception("生成失败")

        result = runner.invoke(
            app,
            ["action", "generate-strategy", "--requirement", "测试", "--name", "test"],
        )
        assert result.exit_code == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
