"""
Agent 工具参数管理系统 - 单元测试和集成测试

覆盖范围:
- ToolParamResolver 参数解析器
- ToolParamManager 参数管理器
- 参数模板发现机制
- 敏感信息保护
- 集成测试（工具实际使用新系统）
"""

import os
import pytest
from datetime import datetime


class TestToolParamResolver:
    """参数解析器测试"""

    def test_resolve_from_database(self):
        """测试从数据库解析参数"""
        from agent.config.tool_params import ToolParamResolver
        
        # 延迟导入避免循环依赖
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig
        
        test_key = "agent.tools.web_search.api_key"
        original_value = None
        
        try:
            # 初始化数据库
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            # 设置测试值
            config = SystemConfig(
                key=test_key,
                value="db_test_key_12345",
                plugin="agent",
                name="web_search",
                is_sensitive=True
            )
            
            if original:
                original.value = "db_test_key_12345"
            else:
                db.add(config)
            db.commit()
            
            # 测试解析
            value = ToolParamResolver.resolve("web_search", "api_key")
            assert value == "db_test_key_12345", f"期望 db_test_key_12345, 得到 {value}"
            
        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()

    def test_resolve_default_value(self):
        """测试默认值回退"""
        from agent.config.tool_params import ToolParamResolver

        value = ToolParamResolver.resolve("web_search", "max_results")
        assert value == 5, f"期望默认值 5, 得到 {value}"

    def test_type_conversion_integer(self):
        """测试整数类型转换"""
        from agent.config.tool_params import ToolParamResolver
        
        # max_results 默认是整数类型
        value = ToolParamResolver.resolve("web_search", "max_results")
        assert isinstance(value, int), f"期望 int 类型, 得到 {type(value)}"

    def test_validate_valid_value(self):
        """测试验证有效值"""
        from agent.config.tool_params import ToolParamResolver

        is_valid, error = ToolParamResolver.validate("web_search", "max_results", 7)
        assert is_valid is True, f"验证应该通过, 错误: {error}"

    def test_validate_invalid_range(self):
        """测试验证无效范围值"""
        from agent.config.tool_params import ToolParamResolver

        is_valid, error = ToolParamResolver.validate("web_search", "max_results", 99)
        assert is_valid is False, "验证应该失败（超出最大值）"
        assert "最大值" in error or "max" in error.lower(), f"错误信息应包含范围提示, 得到: {error}"


class TestToolParamManager:
    """参数管理器测试"""

    def test_set_and_get_param(self):
        """测试设置和获取参数"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.max_results"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            # 设置参数
            success = ToolParamManager.set_tool_param("web_search", "max_results", "10")
            assert success is True, "设置参数应该成功"

            # 获取参数
            params = ToolParamManager.get_tool_params("web_search")
            assert "max_results" in params, "参数 max_results 应该存在"
            assert params["max_results"]["configured"] is True, "参数应该标记为已配置"
            assert params["max_results"]["source"] == "database", "来源应该是 database"
            
        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()

    def test_sensitive_param_masking(self):
        """测试敏感参数脱敏"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.api_key"
        secret_value = "test_sensitive_masking_key"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            # 设置敏感参数
            ToolParamManager.set_tool_param("web_search", "api_key", secret_value)

            # 不包含敏感值
            params = ToolParamManager.get_tool_params("web_search", include_sensitive=False)
            assert params["api_key"]["value"] != secret_value, "敏感值应该被脱敏"
            assert "*" in str(params["api_key"]["value"]), "脱敏值应包含 * 号"

            # 包含敏感值
            params = ToolParamManager.get_tool_params("web_search", include_sensitive=True)
            assert params["api_key"]["value"] == secret_value, "应该返回真实敏感值"
            
        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()

    def test_batch_update(self):
        """测试批量更新"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        key1 = "agent.tools.web_search.max_results"
        key2 = "agent.tools.web_fetch.max_chars"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            orig1 = db.query(SystemConfig).filter_by(key=key1).first()
            orig2 = db.query(SystemConfig).filter_by(key=key2).first()
            orig_val1 = orig1.value if orig1 else None
            orig_val2 = orig2.value if orig2 else None
            
            result = ToolParamManager.batch_update(
                "web_search",
                {"max_results": "8"},
                overwrite=True
            )
            
            # 注意：batch_update 只能更新同一工具的参数
            # 所以我们只测试 web_search 的 max_results
            assert len(result["updated"]) >= 1, f"至少更新1个参数, 实际更新 {len(result['updated'])}个"
            assert len(result["errors"]) == 0, f"不应该有错误, 得到: {result['errors']}"
            
            # 验证值是否正确保存
            params = ToolParamManager.get_tool_params("web_search")
            assert params["max_results"]["configured"] is True
            
        finally:
            # 恢复原始值
            try:
                if orig_val1 is not None:
                    o1 = db.query(SystemConfig).filter_by(key=key1).first()
                    if o1: o1.value = orig_val1
                else:
                    db.query(SystemConfig).filter_by(key=key1).delete()
                    
                if orig_val2 is not None:
                    o2 = db.query(SystemConfig).filter_by(key=key2).first()
                    if o2: o2.value = orig_val2
                else:
                    db.query(SystemConfig).filter_by(key=key2).delete()
                    
                db.commit()
            except:
                pass
            finally:
                db.close()

    def test_delete_param_fallback(self):
        """测试删除参数后回退到默认值/环境变量"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.proxy"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 设置参数
            ToolParamManager.set_tool_param("web_search", "proxy", "http://test.proxy")

            # 验证存在
            params = ToolParamManager.get_tool_params("web_search")
            assert params["proxy"]["configured"] is True

            # 删除参数
            success = ToolParamManager.delete_tool_param("web_search", "proxy")
            assert success is True, "删除应该成功"

            # 验证已删除（回退到默认值）
            params = ToolParamManager.get_tool_params("web_search")
            assert params["proxy"]["configured"] is False, "删除后不应标记为已配置"
            
        finally:
            pass

    def test_export_config(self):
        """测试导出配置"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.max_results"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            # 设置一些配置（使用有效范围内的值）
            ToolParamManager.set_tool_param("web_search", "max_results", "8")

            # 导出
            config = ToolParamManager.export_config("web_search")

            assert "export_time" in config, "导出数据应包含时间戳"
            assert "tools" in config, "导出数据应包含工具配置"
            assert "web_search" in config["tools"], "导出数据应包含 web_search"

        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()


class TestIntegration:
    """集成测试"""

    def test_web_search_tool_uses_new_system(self):
        """测试WebSearchTool使用新的参数系统"""
        from agent.tools.web import WebSearchTool
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_api_key = "test_integration_key_98765"
        test_key = "agent.tools.web_search.api_key"

        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            # 在数据库中设置API key
            config = SystemConfig(
                key=test_key,
                value=test_api_key,
                plugin="agent",
                name="web_search",
                is_sensitive=True
            )
            
            if original:
                original.value = test_api_key
            else:
                db.add(config)
            db.commit()

            tool = WebSearchTool()

            assert tool.api_key == test_api_key, (
                f"工具应该从数据库获取api_key, "
                f"期望 {test_api_key}, 得到 {tool.api_key}"
            )

        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()

    def test_web_search_tool_manual_override_priority(self):
        """测试手动构造函数参数优先级高于数据库"""
        from agent.tools.web import WebSearchTool

        manual_key = "manual_override_key"
        
        tool = WebSearchTool(api_key=manual_key)

        assert tool.api_key == manual_key, (
            f"手动设置的api_key优先级应该更高, "
            f"期望 {manual_key}, 得到 {tool.api_key}"
        )

    def test_fallback_to_environment_variable(self):
        """测试回退到环境变量"""
        from agent.tools.web import WebSearchTool

        env_key = "BRAVE_API_KEY"
        env_value = "env_fallback_value_xyz"

        original_env = os.environ.get(env_key)

        try:
            os.environ[env_key] = env_value

            tool = WebSearchTool()

            assert tool.api_key == env_value, (
                f"应该从环境变量获取api_key, "
                f"期望 {env_value}, 得到 {tool.api_key}"
            )

        finally:
            if original_env is not None:
                os.environ[env_key] = original_env
            elif env_key in os.environ:
                del os.environ[env_key]

    def test_registered_tools_list_includes_web_search(self):
        """测试已注册工具列表包含 web_search"""
        from agent.config.manager import ToolParamManager

        tools = ToolParamManager.get_registered_tools()

        tool_names = [t["name"] for t in tools]
        assert "web_search" in tool_names, "已注册工具列表应包含 web_search"
        assert "web_fetch" in tool_names, "已注册工具列表应包含 web_fetch"


class TestEdgeCases:
    """边界情况测试"""

    def test_unknown_tool_raises_error(self):
        """测试未知工具抛出异常"""
        from agent.config.manager import ToolParamManager

        with pytest.raises(ValueError) as exc_info:
            ToolParamManager.get_tool_params("nonexistent_tool_xyz")

        assert "未知工具" in str(exc_info.value) or "unknown" in str(exc_info.value).lower()

    def test_empty_string_value_handling(self):
        """测试空字符串值处理"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.proxy"
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            success = ToolParamManager.set_tool_param("web_search", "proxy", "")
            assert success is True, "设置空字符串应该成功"

            params = ToolParamManager.get_tool_params("web_search")
            assert params["proxy"]["value"] == "", "空字符串应该正确存储"

        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()

    def test_special_characters_in_value(self):
        """测试特殊字符值处理"""
        from agent.config.manager import ToolParamManager
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig

        test_key = "agent.tools.web_search.proxy"
        special_value = 'value with "quotes" and <tags> & ampersands'
        
        try:
            init_database_config()
            db = SessionLocal()
            
            # 保存原始值
            original = db.query(SystemConfig).filter_by(key=test_key).first()
            original_value = original.value if original else None
            
            success = ToolParamManager.set_tool_param("web_search", "proxy", special_value)
            assert success is True

            params = ToolParamManager.get_tool_params("web_search")
            assert params["proxy"]["value"] == special_value, "特殊字符应该正确存储"

        finally:
            # 恢复原始值
            try:
                if original_value is not None:
                    orig = db.query(SystemConfig).filter_by(key=test_key).first()
                    if orig:
                        orig.value = original_value
                        db.commit()
                else:
                    db.query(SystemConfig).filter_by(key=test_key).delete()
                    db.commit()
            except:
                pass
            finally:
                db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
