# QuantCell 测试运行指南

## 1. 前置条件和环境配置

### 1.1 必要环境

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.12 | 项目要求 |
| uv | 最新版 | 包管理工具 |
| pytest | >= 9.0.1 | 已在 pyproject.toml 中声明 |

### 1.2 环境检查

```bash
cd backend
python3 --version
uv --version
```

### 1.3 安装依赖

```bash
cd backend
uv sync
```

---

## 2. 测试文件结构

测试按用途分散在若干目录下：

```
tests/
├── README.md            # 本文件
├── unit/                # 单元测试（主要部分）
│   ├── <子包>/          # 按被测模块组织：strategy/ worker/ rl/ engine/
│   │                    #   services/ axon_bridge/ api/ scripts/ share/ credentials/ ...
│   └── test_*.py        # 也有部分跨模块的顶层测试文件
├── integration/         # 集成测试（API、回测、行情等端到端）
├── conformance/         # 一致性/契约测试
├── backtest/            # 回测相关测试
├── decision/            # 决策引擎测试
├── realtime/            # 实时行情链路测试
├── agent/               # AI Agent 测试
├── exchange/            # 交易所适配测试
├── manual/              # 需要手动触发/联网的脚本式测试
└── fixtures/           # 测试夹具与 mock
```

新增测试请放到与被测模块对应的子包下，顶层零散文件保持最少。

---

## 3. 命令行指令

### 3.1 基础命令

```bash
# 运行全部单元测试
cd backend && .venv/bin/python -m pytest tests/unit -q -p no:cacheprovider

# 运行单个测试文件
cd backend && .venv/bin/python -m pytest tests/unit/strategy/test_base.py -v

# 运行特定测试类 / 方法
cd backend && .venv/bin/python -m pytest tests/unit/strategy/test_base.py::TestXxx -v
cd backend && .venv/bin/python -m pytest tests/unit/strategy/test_base.py::TestXxx::test_yyy -v
```

### 3.2 过滤

```bash
# 按关键字
cd backend && .venv/bin/python -m pytest tests/unit -k "keyword" -q

# 遇错立即停止
cd backend && .venv/bin/python -m pytest tests/unit -x -q

# 只收集不执行（查看有哪些测试）
cd backend && .venv/bin/python -m pytest tests/unit --collect-only -q
```

### 3.3 常用参数速查表

| 参数 | 说明 |
|------|------|
| `-v` | 详细输出 |
| `-s` | 显示 print/日志输出 |
| `-x` | 遇到失败立即停止 |
| `-q` | 精简输出 |
| `--tb=short` / `--tb=long` | 简短 / 详细错误回溯 |
| `-k <keyword>` | 按关键字过滤 |
| `-m <marker>` | 按标记过滤 |
| `--durations=N` | 显示最慢的 N 个测试 |
| `--collect-only` | 只收集不执行 |
| `--timeout=N` | 设置超时（秒） |
| `-p no:cacheprovider` | 关闭 pytest 缓存（CI/隔离环境常用） |

---

## 4. 测试结果解读

| 状态 | 含义 | 处理方式 |
|------|------|---------|
| **PASSED** | 测试通过 | 无需处理 |
| **FAILED** | 断言失败 | 检查代码逻辑 |
| **ERROR** | 执行错误 | 检查 fixture 或环境 |
| **SKIPPED** | 被跳过 | 检查跳过条件 |
| **XFAIL** | 预期失败 | 正常，已标记 |
| **XPASS** | 预期失败但通过 | 可能需要更新测试 |

---

## 5. 故障排查

### 5.1 模块导入错误

`ModuleNotFoundError: No module named 'strategy'` 时，确保在 `backend` 目录下运行，
或显式设置 `PYTHONPATH`：

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit -q
```

### 5.2 异步测试错误

异步测试依赖 `pytest-asyncio`（已在 dev 依赖中声明），如报错先确认依赖已安装：

```bash
cd backend && uv sync
```

### 5.3 测试超时

部分性能测试较慢，可用 `--timeout` 限制单个测试耗时，或只跑单个文件定位问题。

---

## 6. CI/CD 配置示例

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: cd backend && uv sync

      - name: Run unit tests
        run: cd backend && .venv/bin/python -m pytest tests/unit -q -p no:cacheprovider
```

---

**维护者：** QuantCell 开发团队
