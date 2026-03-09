"""TemplateLibrary 单元测试

测试策略模板库的单例模式、模板加载、模板渲染和分类过滤功能
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# 直接从文件加载模块，避免触发 ai_model/__init__.py 的完整导入链
_test_file = Path(__file__).resolve()
_backend_dir = _test_file.parent.parent.parent.parent  # tests/unit/ai_model -> tests/unit -> tests -> backend
_ai_model_dir = _backend_dir / "ai_model"

# 加载 template_library 模块
spec = importlib.util.spec_from_file_location(
    "template_library", _ai_model_dir / "template_library.py"
)
assert spec is not None and spec.loader is not None, "无法加载 template_library 模块"
library_module = importlib.util.module_from_spec(spec)
sys.modules["template_library"] = library_module
spec.loader.exec_module(library_module)

TemplateLibrary = library_module.TemplateLibrary
StrategyTemplate = library_module.StrategyTemplate
TemplateParameter = library_module.TemplateParameter
TemplateCategory = library_module.TemplateCategory


@pytest.fixture
def create_test_library_file():
    """创建测试用的模板库YAML文件"""
    yaml_content = """
version: "1.0.0"
description: "测试模板库"

categories:
  - id: "trend_following"
    name: "趋势跟踪"
    description: "基于趋势的交易策略"
  - id: "mean_reversion"
    name: "均值回归"
    description: "基于均值回归的策略"

templates:
  - id: "dual_ma"
    name: "双均线策略"
    category: "trend_following"
    description: "双均线交叉策略"
    author: "Test"
    version: "1.0.0"
    tags: ["均线", "趋势"]
    parameters:
      - name: "fast_period"
        type: "int"
        default: 10
        min: 2
        max: 100
        description: "短期均线周期"
      - name: "slow_period"
        type: "int"
        default: 30
        min: 5
        max: 200
        description: "长期均线周期"
      - name: "trade_size"
        type: "float"
        default: 0.1
        min: 0.001
        max: 1000
        description: "交易数量"
    code_template: |
      class {{strategy_name}}:
          fast_period = {{fast_period}}
          slow_period = {{slow_period}}
          trade_size = {{trade_size}}

  - id: "rsi"
    name: "RSI策略"
    category: "mean_reversion"
    description: "RSI超买超卖策略"
    author: "Test"
    version: "1.0.0"
    tags: ["RSI", "超买超卖"]
    parameters:
      - name: "rsi_period"
        type: "int"
        default: 14
        min: 2
        max: 50
        description: "RSI周期"
      - name: "oversold"
        type: "int"
        default: 30
        min: 0
        max: 50
        description: "超卖阈值"
    code_template: |
      class {{strategy_name}}:
          rsi_period = {{rsi_period}}
          oversold = {{oversold}}
"""

    def _create():
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            return Path(f.name)

    return _create


class TestTemplateLibrarySingleton:
    """测试 TemplateLibrary 单例模式"""

    def test_singleton_instance(self, create_test_library_file):
        """测试多次实例化返回同一对象"""
        library_file = create_test_library_file()

        # 重置单例
        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library1 = TemplateLibrary(library_file)
        library2 = TemplateLibrary(library_file)
        assert library1 is library2

    def test_singleton_same_data(self, create_test_library_file):
        """测试单例模式下数据共享"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library1 = TemplateLibrary(library_file)
        library2 = TemplateLibrary(library_file)
        assert library1._templates is library2._templates
        assert library1._categories is library2._categories


class TestTemplateLibraryLoading:
    """测试 TemplateLibrary 模板加载功能"""

    def test_load_templates(self, create_test_library_file):
        """测试模板加载"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        # 检查模板是否加载
        assert len(library._templates) == 2
        assert "dual_ma" in library._templates
        assert "rsi" in library._templates

    def test_load_categories(self, create_test_library_file):
        """测试分类加载"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        # 检查分类是否加载
        assert len(library._categories) == 2
        assert "trend_following" in library._categories
        assert "mean_reversion" in library._categories

    def test_load_template_parameters(self, create_test_library_file):
        """测试模板参数加载"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        template = library._templates["dual_ma"]
        assert len(template.parameters) == 3

        param_names = [p.name for p in template.parameters]
        assert "fast_period" in param_names
        assert "slow_period" in param_names
        assert "trade_size" in param_names

    def test_file_not_found(self):
        """测试文件不存在时抛出异常"""
        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        with pytest.raises(FileNotFoundError):
            TemplateLibrary("/nonexistent/path/library.yaml")


class TestTemplateLibraryGetters:
    """测试 TemplateLibrary 查询功能"""

    def test_get_all_templates(self, create_test_library_file):
        """测试获取所有模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        templates = library.get_all_templates()

        assert len(templates) == 2
        template_ids = [t.id for t in templates]
        assert "dual_ma" in template_ids
        assert "rsi" in template_ids

    def test_get_all_templates_with_category_filter(self, create_test_library_file):
        """测试按分类过滤获取模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        trend_templates = library.get_all_templates(category="trend_following")
        assert len(trend_templates) == 1
        assert trend_templates[0].id == "dual_ma"

        mean_reversion_templates = library.get_all_templates(category="mean_reversion")
        assert len(mean_reversion_templates) == 1
        assert mean_reversion_templates[0].id == "rsi"

    def test_get_template(self, create_test_library_file):
        """测试获取单个模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        template = library.get_template("dual_ma")
        assert template is not None
        assert template.id == "dual_ma"
        assert template.name == "双均线策略"

    def test_get_nonexistent_template(self, create_test_library_file):
        """测试获取不存在的模板返回None"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        template = library.get_template("nonexistent")
        assert template is None

    def test_get_categories(self, create_test_library_file):
        """测试获取所有分类"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        categories = library.get_categories()

        assert len(categories) == 2
        category_ids = [c.id for c in categories]
        assert "trend_following" in category_ids
        assert "mean_reversion" in category_ids

    def test_get_category(self, create_test_library_file):
        """测试获取单个分类"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        category = library.get_category("trend_following")
        assert category is not None
        assert category.id == "trend_following"
        assert category.name == "趋势跟踪"

    def test_get_templates_by_category(self, create_test_library_file):
        """测试按分类获取模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        templates = library.get_templates_by_category("trend_following")
        assert len(templates) == 1
        assert templates[0].id == "dual_ma"


class TestTemplateLibraryRendering:
    """测试 TemplateLibrary 模板渲染功能"""

    def test_render_template_with_defaults(self, create_test_library_file):
        """测试使用默认参数渲染模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        code = library.render_template("dual_ma", strategy_name="MyStrategy")

        assert "class MyStrategy:" in code
        assert "fast_period = 10" in code
        assert "slow_period = 30" in code
        assert "trade_size = 0.1" in code

    def test_render_template_with_custom_params(self, create_test_library_file):
        """测试使用自定义参数渲染模板"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        code = library.render_template(
            "dual_ma",
            strategy_name="CustomStrategy",
            fast_period=20,
            slow_period=50,
            trade_size=1.0
        )

        assert "class CustomStrategy:" in code
        assert "fast_period = 20" in code
        assert "slow_period = 50" in code
        assert "trade_size = 1.0" in code

    def test_render_template_default_strategy_name(self, create_test_library_file):
        """测试默认策略名称"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        code = library.render_template("dual_ma")

        assert "class GeneratedStrategy:" in code

    def test_render_nonexistent_template_raises_keyerror(self, create_test_library_file):
        """测试渲染不存在的模板抛出 KeyError"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        with pytest.raises(KeyError) as exc_info:
            library.render_template("nonexistent")

        assert "nonexistent" in str(exc_info.value)

    def test_render_with_invalid_params_raises_valueerror(self, create_test_library_file):
        """测试无效参数抛出 ValueError"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        with pytest.raises(ValueError) as exc_info:
            library.render_template("dual_ma", fast_period=1)  # 小于最小值2

        assert "参数验证失败" in str(exc_info.value)


class TestTemplateParameterValidation:
    """测试模板参数验证功能"""

    def test_validate_valid_params(self, create_test_library_file):
        """测试有效参数验证"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        is_valid, errors = template.validate_params({
            "fast_period": 15,
            "slow_period": 40,
            "trade_size": 0.5
        })

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid_min_value(self, create_test_library_file):
        """测试小于最小值的参数"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        is_valid, errors = template.validate_params({
            "fast_period": 1,  # 小于最小值2
        })

        assert is_valid is False
        assert any("不能小于" in e for e in errors)

    def test_validate_invalid_max_value(self, create_test_library_file):
        """测试大于最大值的参数"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        is_valid, errors = template.validate_params({
            "fast_period": 200,  # 大于最大值100
        })

        assert is_valid is False
        assert any("不能大于" in e for e in errors)

    def test_validate_unknown_param(self, create_test_library_file):
        """测试未知参数"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        is_valid, errors = template.validate_params({
            "unknown_param": 100,
        })

        assert is_valid is False
        assert any("未知参数" in e for e in errors)


class TestTemplateLibrarySearch:
    """测试 TemplateLibrary 搜索功能"""

    def test_search_by_name(self, create_test_library_file):
        """测试按名称搜索"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        results = library.search_templates("RSI")
        assert len(results) == 1
        assert results[0].id == "rsi"

    def test_search_by_description(self, create_test_library_file):
        """测试按描述搜索"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        results = library.search_templates("超买超卖")
        assert len(results) == 1
        assert results[0].id == "rsi"

    def test_search_by_tag(self, create_test_library_file):
        """测试按标签搜索"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        results = library.search_templates("均线")
        assert len(results) == 1
        assert results[0].id == "dual_ma"

    def test_search_no_results(self, create_test_library_file):
        """测试无结果搜索"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        results = library.search_templates("nonexistent")
        assert len(results) == 0


class TestTemplateLibraryUtilityMethods:
    """测试 TemplateLibrary 工具方法"""

    def test_list_template_ids(self, create_test_library_file):
        """测试获取模板ID列表"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        ids = library.list_template_ids()
        assert "dual_ma" in ids
        assert "rsi" in ids

    def test_list_category_ids(self, create_test_library_file):
        """测试获取分类ID列表"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        ids = library.list_category_ids()
        assert "trend_following" in ids
        assert "mean_reversion" in ids

    def test_has_template(self, create_test_library_file):
        """测试检查模板是否存在"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        assert library.has_template("dual_ma") is True
        assert library.has_template("nonexistent") is False

    def test_get_library_info(self, create_test_library_file):
        """测试获取库信息"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        info = library.get_library_info()
        assert info["version"] == "1.0.0"
        assert info["description"] == "测试模板库"
        assert info["template_count"] == 2
        assert info["category_count"] == 2

    def test_reload(self, create_test_library_file):
        """测试重新加载"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)

        # 修改内部状态
        library._templates.clear()

        # 重新加载
        library.reload()

        assert len(library._templates) == 2


class TestTemplateDataClasses:
    """测试数据类功能"""

    def test_template_to_dict(self, create_test_library_file):
        """测试模板转换为字典"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        data = template.to_dict()
        assert data["id"] == "dual_ma"
        assert data["name"] == "双均线策略"
        assert "parameters" in data
        assert len(data["parameters"]) == 3

    def test_template_get_default_params(self, create_test_library_file):
        """测试获取默认参数"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        template = library.get_template("dual_ma")

        defaults = template.get_default_params()
        assert defaults["fast_period"] == 10
        assert defaults["slow_period"] == 30
        assert defaults["trade_size"] == 0.1

    def test_category_to_dict(self, create_test_library_file):
        """测试分类转换为字典"""
        library_file = create_test_library_file()

        TemplateLibrary._instance = None
        TemplateLibrary._templates = {}
        TemplateLibrary._categories = {}

        library = TemplateLibrary(library_file)
        category = library.get_category("trend_following")

        data = category.to_dict()
        assert data["id"] == "trend_following"
        assert data["name"] == "趋势跟踪"


@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试后重置单例状态"""
    yield
    TemplateLibrary._instance = None
    TemplateLibrary._templates = {}
    TemplateLibrary._categories = {}
