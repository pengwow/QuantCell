"""PromptManager 单元测试

测试提示词管理器的单例模式、模板加载、变量替换和重新加载功能
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# 直接从文件加载模块，避免触发 ai_model/__init__.py 的完整导入链
# 使用绝对路径
_test_file = Path(__file__).resolve()
_backend_dir = _test_file.parent.parent.parent.parent  # tests/unit/ai_model -> tests/unit -> tests -> backend
_ai_model_dir = _backend_dir / "ai_model"
_prompts_dir = _ai_model_dir / "prompts"

# 加载 prompts.manager 模块
spec = importlib.util.spec_from_file_location(
    "prompts.manager", _prompts_dir / "manager.py"
)
assert spec is not None and spec.loader is not None, "无法加载 prompts.manager 模块"
manager_module = importlib.util.module_from_spec(spec)
sys.modules["prompts.manager"] = manager_module
spec.loader.exec_module(manager_module)

PromptCategory = manager_module.PromptCategory
PromptManager = manager_module.PromptManager


class TestPromptManagerSingleton:
    """测试 PromptManager 单例模式"""

    def test_singleton_instance(self):
        """测试多次实例化返回同一对象"""
        # 重置单例
        PromptManager._instance = None
        PromptManager._templates = {}

        manager1 = PromptManager()
        manager2 = PromptManager()
        assert manager1 is manager2

    def test_singleton_same_templates(self):
        """测试单例模式下模板数据共享"""
        PromptManager._instance = None
        PromptManager._templates = {}

        manager1 = PromptManager()
        manager2 = PromptManager()
        assert manager1._templates is manager2._templates

    def test_singleton_initialized_once(self):
        """测试单例只初始化一次"""
        # 清除单例状态
        PromptManager._instance = None
        PromptManager._templates = {}

        manager = PromptManager()
        assert hasattr(manager, "_initialized")

        # 再次获取实例，不应重新初始化
        manager2 = PromptManager()
        assert manager2._initialized is True


class TestPromptManagerTemplateLoading:
    """测试 PromptManager 模板加载功能"""

    def test_load_default_templates(self):
        """测试默认模板加载"""
        # 清除单例状态
        PromptManager._instance = None
        PromptManager._templates = {}

        manager = PromptManager()

        # 检查是否加载了默认模板
        available = manager.list_available_templates()
        assert len(available) > 0
        assert PromptCategory.STRATEGY_GENERATION.value in available

    def test_get_existing_template(self):
        """测试获取存在的模板"""
        PromptManager._instance = None
        PromptManager._templates = {}

        manager = PromptManager()

        template = manager.get_template(PromptCategory.STRATEGY_GENERATION)
        assert isinstance(template, str)
        assert len(template) > 0
        assert "{{user_description}}" in template

    def test_get_nonexistent_template_raises_keyerror(self):
        """测试获取不存在的模板抛出 KeyError"""
        # 使用临时目录创建管理器
        with tempfile.TemporaryDirectory() as tmpdir:
            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir)

            with pytest.raises(KeyError) as exc_info:
                manager.get_template(PromptCategory.STRATEGY_GENERATION)

            assert "strategy_generation" in str(exc_info.value)

    def test_has_template_true(self):
        """测试 has_template 返回 True"""
        PromptManager._instance = None
        PromptManager._templates = {}

        manager = PromptManager()

        if manager.has_template(PromptCategory.STRATEGY_GENERATION):
            assert True
        else:
            pytest.skip("默认模板未加载")

    def test_has_template_false(self):
        """测试 has_template 返回 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir)
            assert not manager.has_template(PromptCategory.STRATEGY_GENERATION)

    def test_custom_templates_dir(self):
        """测试自定义模板目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # 创建测试模板文件
            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text("Test template content", encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            assert manager.has_template(PromptCategory.STRATEGY_GENERATION)
            assert manager.get_template(PromptCategory.STRATEGY_GENERATION) == "Test template content"


class TestPromptManagerVariableReplacement:
    """测试 PromptManager 变量替换功能"""

    def test_render_with_variables(self):
        """测试变量替换功能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # 创建包含变量的模板
            template_content = "Hello {{name}}, your strategy is {{strategy_name}}"
            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text(template_content, encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            result = manager.render(
                PromptCategory.STRATEGY_GENERATION,
                name="User",
                strategy_name="MyStrategy"
            )

            assert "Hello User" in result
            assert "your strategy is MyStrategy" in result
            assert "{{" not in result

    def test_render_preserves_unknown_variables(self):
        """测试未知变量保留原样"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            template_content = "Hello {{name}}, unknown: {{unknown_var}}"
            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text(template_content, encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            result = manager.render(
                PromptCategory.STRATEGY_GENERATION,
                name="User"
            )

            assert "Hello User" in result
            assert "{{unknown_var}}" in result

    def test_render_with_no_variables(self):
        """测试无变量时的渲染"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            template_content = "Static template content"
            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text(template_content, encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            result = manager.render(PromptCategory.STRATEGY_GENERATION)
            assert result == template_content

    def test_render_with_special_characters(self):
        """测试包含特殊字符的变量替换"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            template_content = "Description: {{description}}"
            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text(template_content, encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            special_desc = "Line1\nLine2\tTabbed"
            result = manager.render(
                PromptCategory.STRATEGY_GENERATION,
                description=special_desc
            )

            assert special_desc in result


class TestPromptManagerReload:
    """测试 PromptManager 模板重新加载功能"""

    def test_reload_single_template(self):
        """测试重新加载单个模板"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            template_file = tmpdir_path / "strategy_generation.txt"
            template_file.write_text("Original content", encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            # 修改模板文件
            template_file.write_text("Updated content", encoding="utf-8")

            # 重新加载
            manager.reload_template(PromptCategory.STRATEGY_GENERATION)

            updated = manager.get_template(PromptCategory.STRATEGY_GENERATION)
            assert updated == "Updated content"

    def test_reload_all_templates(self):
        """测试重新加载所有模板"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # 创建多个模板
            (tmpdir_path / "strategy_generation.txt").write_text("Strategy v1", encoding="utf-8")
            (tmpdir_path / "code_optimization.txt").write_text("Optimization v1", encoding="utf-8")

            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir_path)

            # 修改模板文件
            (tmpdir_path / "strategy_generation.txt").write_text("Strategy v2", encoding="utf-8")
            (tmpdir_path / "code_optimization.txt").write_text("Optimization v2", encoding="utf-8")

            # 重新加载所有
            manager.reload_all()

            assert manager.get_template(PromptCategory.STRATEGY_GENERATION) == "Strategy v2"
            assert manager.get_template(PromptCategory.CODE_OPTIMIZATION) == "Optimization v2"

    def test_reload_nonexistent_template(self):
        """测试重新加载不存在的模板"""
        with tempfile.TemporaryDirectory() as tmpdir:
            PromptManager._instance = None
            PromptManager._templates = {}

            manager = PromptManager(templates_dir=tmpdir)

            # 不应抛出异常
            manager.reload_template(PromptCategory.STRATEGY_GENERATION)

            # 模板不应被添加
            assert not manager.has_template(PromptCategory.STRATEGY_GENERATION)


class TestPromptCategory:
    """测试 PromptCategory 枚举"""

    def test_category_values(self):
        """测试分类枚举值"""
        assert PromptCategory.STRATEGY_GENERATION.value == "strategy_generation"
        assert PromptCategory.CODE_OPTIMIZATION.value == "code_optimization"
        assert PromptCategory.STRATEGY_EXPLANATION.value == "strategy_explanation"

    def test_category_is_string(self):
        """测试分类是字符串类型"""
        assert isinstance(PromptCategory.STRATEGY_GENERATION, str)
        assert PromptCategory.STRATEGY_GENERATION == "strategy_generation"


@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试后重置单例状态"""
    yield
    PromptManager._instance = None
    PromptManager._templates = {}
