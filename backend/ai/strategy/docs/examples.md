# 策略生成 API 使用示例

本文档提供策略生成 API 的详细使用示例，涵盖代码验证、历史记录管理、模板库使用和性能统计等场景。

## 目录

- [代码验证示例](#代码验证示例)
  - [验证成功场景](#验证成功场景)
  - [验证失败场景](#验证失败场景)
- [历史记录使用示例](#历史记录使用示例)
  - [创建历史记录](#创建历史记录)
  - [查询历史记录](#查询历史记录)
  - [删除历史记录](#删除历史记录)
  - [重新生成策略](#重新生成策略)
- [模板库使用示例](#模板库使用示例)
  - [获取模板列表](#获取模板列表)
  - [获取模板详情](#获取模板详情)
  - [基于模板生成](#基于模板生成)
- [性能统计查询示例](#性能统计查询示例)
- [完整端到端流程示例](#完整端到端流程示例)

---

## 代码验证示例

### 验证成功场景

以下示例展示如何验证一段正确的策略代码：

```python
import requests

# API 基础配置
BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# 正确的策略代码
correct_code = '''
class DualMAStrategy:
    """双均线策略"""

    def __init__(self):
        self.fast_period = 10
        self.slow_period = 20
        self.position = None

    def on_bar(self, bar):
        """处理K线数据"""
        fast_ma = self.calculate_ma(bar.close, self.fast_period)
        slow_ma = self.calculate_ma(bar.close, self.slow_period)

        if fast_ma > slow_ma and not self.position:
            self.buy()
        elif fast_ma < slow_ma and self.position:
            self.sell()

    def calculate_ma(self, price, period):
        """计算移动平均线"""
        # 简化实现
        return price

    def buy(self):
        """买入"""
        self.position = "long"
        print("买入信号")

    def sell(self):
        """卖出"""
        self.position = None
        print("卖出信号")
'''

# 发送验证请求
response = requests.post(
    f"{BASE_URL}/validate-code",
    headers=headers,
    json={
        "code": correct_code,
        "language": "python"
    }
)

result = response.json()
data = result["data"]

print("=" * 50)
print("代码验证结果")
print("=" * 50)
print(f"验证状态: {'✅ 通过' if data['valid'] else '❌ 失败'}")

if data['errors']:
    print(f"\n错误 ({len(data['errors'])}):")
    for error in data['errors']:
        print(f"  - {error}")

if data['warnings']:
    print(f"\n警告 ({len(data['warnings'])}):")
    for warning in data['warnings']:
        print(f"  - {warning}")

if data['suggestions']:
    print(f"\n建议 ({len(data['suggestions'])}):")
    for suggestion in data['suggestions']:
        print(f"  - {suggestion}")

# 预期输出：
# ==================================================
# 代码验证结果
# ==================================================
# 验证状态: ✅ 通过
#
# 警告 (1):
#   - 警告: 未检测到策略基类继承
#
# 建议 (1):
#   - 建议: 添加代码注释以提高可读性
```

### 验证失败场景

以下示例展示验证包含语法错误的代码：

```python
import requests

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# 包含语法错误的代码
incorrect_code = '''
class BrokenStrategy
    def __init__(self)
        self.value = 10
        if self.value > 5
            print("大于5")

    def on_bar(self, bar)
        pass
'''

# 发送验证请求
response = requests.post(
    f"{BASE_URL}/validate-code",
    headers=headers,
    json={
        "code": incorrect_code,
        "language": "python"
    }
)

result = response.json()
data = result["data"]

print("=" * 50)
print("代码验证结果")
print("=" * 50)
print(f"验证状态: {'✅ 通过' if data['valid'] else '❌ 失败'}")

if data['errors']:
    print(f"\n错误 ({len(data['errors'])}):")
    for error in data['errors']:
        print(f"  - {error}")

# 预期输出：
# ==================================================
# 代码验证结果
# ==================================================
# 验证状态: ❌ 失败
#
# 错误 (3):
#   - 语法错误: 第2行 - 缺少冒号
#   - 语法错误: 第3行 - 缺少冒号
#   - 语法错误: 第5行 - 缺少冒号
```

### 批量验证代码

验证多个代码片段：

```python
import requests
from typing import List, Dict

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def batch_validate(codes: List[Dict[str, str]]) -> List[Dict]:
    """批量验证代码

    Args:
        codes: 代码列表，每项包含 name 和 code

    Returns:
        验证结果列表
    """
    results = []

    for item in codes:
        print(f"\n验证: {item['name']}...")

        response = requests.post(
            f"{BASE_URL}/validate-code",
            headers=headers,
            json={
                "code": item["code"],
                "language": "python"
            }
        )

        result = response.json()
        data = result["data"]

        results.append({
            "name": item["name"],
            "valid": data["valid"],
            "errors": data["errors"],
            "warnings": data["warnings"]
        })

        status = "✅" if data["valid"] else "❌"
        print(f"{status} {item['name']}")

    return results

# 待验证的代码列表
codes_to_validate = [
    {
        "name": "简单策略",
        "code": "class SimpleStrategy:\n    pass"
    },
    {
        "name": "完整策略",
        "code": """
class CompleteStrategy:
    def __init__(self):
        self.period = 20

    def on_bar(self, bar):
        pass
"""
    },
    {
        "name": "错误策略",
        "code": "class ErrorStrategy\n    def __init__(self)"
    }
]

# 执行批量验证
results = batch_validate(codes_to_validate)

# 输出汇总
print("\n" + "=" * 50)
print("批量验证汇总")
print("=" * 50)

valid_count = sum(1 for r in results if r["valid"])
invalid_count = len(results) - valid_count

print(f"总计: {len(results)}")
print(f"通过: {valid_count}")
print(f"失败: {invalid_count}")

if invalid_count > 0:
    print("\n失败的代码:")
    for r in results:
        if not r["valid"]:
            print(f"  - {r['name']}: {r['errors'][0] if r['errors'] else '未知错误'}")
```

---

## 历史记录使用示例

### 创建历史记录

策略生成后会自动创建历史记录，以下是手动创建历史记录的示例：

```python
import requests
from datetime import datetime

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def create_history_record(requirement: str, code: str, model_id: str = "gpt-4"):
    """创建策略历史记录

    通过生成策略 API 自动生成历史记录
    """
    response = requests.post(
        f"{BASE_URL}/generate-sync",
        headers=headers,
        json={
            "requirement": requirement,
            "model_id": model_id,
            "temperature": 0.7
        }
    )

    result = response.json()

    if result["code"] == 0:
        print("✅ 策略生成成功，历史记录已创建")
        print(f"请求ID: {result['data']['request_id']}")
        print(f"使用模型: {result['data']['model_used']}")
        print(f"Token使用: {result['data']['tokens_used']}")
        print(f"生成耗时: {result['data']['elapsed_time']:.2f}秒")
        return result["data"]
    else:
        print(f"❌ 生成失败: {result['message']}")
        return None

# 创建历史记录示例
requirement = "创建一个RSI策略，当RSI低于30时买入，高于70时卖出"
result = create_history_record(requirement, "")

if result:
    print("\n生成的代码:")
    print("-" * 50)
    print(result["code"][:500] + "..." if len(result["code"]) > 500 else result["code"])
```

### 查询历史记录

#### 获取历史记录列表

```python
import requests
from typing import Optional

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def get_history_list(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    model_id: Optional[str] = None
):
    """获取策略历史记录列表

    Args:
        page: 页码，从1开始
        page_size: 每页数量
        status: 筛选状态 (success/failed/pending)
        model_id: 筛选模型ID
    """
    params = {
        "page": page,
        "page_size": page_size
    }

    if status:
        params["status"] = status
    if model_id:
        params["model_id"] = model_id

    response = requests.get(
        f"{BASE_URL}/history",
        headers=headers,
        params=params
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]
        pagination = data["pagination"]

        print("=" * 60)
        print("策略历史记录")
        print("=" * 60)
        print(f"总记录数: {pagination['total']}")
        print(f"当前页: {pagination['page']}/{pagination['total_pages']}")
        print(f"每页: {pagination['page_size']} 条")
        print("-" * 60)

        for i, item in enumerate(data["list"], 1):
            print(f"\n[{i}] ID: {item['id']}")
            print(f"    需求: {item['requirement'][:60]}...")
            print(f"    模型: {item['model_id']}")
            print(f"    状态: {item['status']}")
            print(f"    创建时间: {item['created_at']}")

            if item['tokens_used']:
                print(f"    Token: {item['tokens_used']['total_tokens']}")

        return data
    else:
        print(f"❌ 获取失败: {result['message']}")
        return None

# 获取所有历史记录
history = get_history_list(page=1, page_size=10)

# 获取成功的记录
print("\n" + "=" * 60)
print("成功的记录")
print("=" * 60)
success_history = get_history_list(status="success", page_size=5)

# 获取使用 gpt-4 的记录
print("\n" + "=" * 60)
print("GPT-4 生成的记录")
print("=" * 60)
gpt4_history = get_history_list(model_id="gpt-4", page_size=5)
```

#### 获取单条历史记录详情

```python
import requests

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def get_history_detail(history_id: str):
    """获取单条历史记录详情"""
    response = requests.get(
        f"{BASE_URL}/history/{history_id}",
        headers=headers
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]

        print("=" * 60)
        print("历史记录详情")
        print("=" * 60)
        print(f"ID: {data['id']}")
        print(f"用户ID: {data['user_id']}")
        print(f"状态: {data['status']}")
        print(f"模型: {data['model_id']}")
        print(f"创建时间: {data['created_at']}")
        print(f"更新时间: {data['updated_at']}")
        print("-" * 60)
        print("需求描述:")
        print(data['requirement'])
        print("-" * 60)

        if data['explanation']:
            print("策略说明:")
            print(data['explanation'])
            print("-" * 60)

        if data['tokens_used']:
            print("Token 使用:")
            print(f"  Prompt: {data['tokens_used']['prompt_tokens']}")
            print(f"  Completion: {data['tokens_used']['completion_tokens']}")
            print(f"  Total: {data['tokens_used']['total_tokens']}")
            print("-" * 60)

        print("生成的代码:")
        print(data['code'])

        return data
    elif response.status_code == 404:
        print(f"❌ 历史记录不存在: {history_id}")
        return None
    elif response.status_code == 403:
        print(f"❌ 无权访问该记录: {history_id}")
        return None
    else:
        print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        return None

# 使用示例（需要先获取一个有效的 history_id）
# history_detail = get_history_detail("hist_1234567890")
```

### 删除历史记录

```python
import requests

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def delete_history(history_id: str):
    """删除历史记录"""
    response = requests.delete(
        f"{BASE_URL}/history/{history_id}",
        headers=headers
    )

    if response.status_code == 200:
        result = response.json()
        if result["code"] == 0:
            print(f"✅ 历史记录已删除: {history_id}")
            return True
    elif response.status_code == 404:
        print(f"❌ 历史记录不存在: {history_id}")
    elif response.status_code == 403:
        print(f"❌ 无权删除该记录: {history_id}")
    else:
        print(f"❌ 删除失败: {response.text}")

    return False

def batch_delete_histories(history_ids: list):
    """批量删除历史记录"""
    print(f"批量删除 {len(history_ids)} 条历史记录...")

    success_count = 0
    failed_count = 0

    for history_id in history_ids:
        if delete_history(history_id):
            success_count += 1
        else:
            failed_count += 1

    print("\n" + "=" * 50)
    print("批量删除结果")
    print("=" * 50)
    print(f"成功: {success_count}")
    print(f"失败: {failed_count}")
    print(f"总计: {len(history_ids)}")

    return success_count, failed_count

# 使用示例
# delete_history("hist_1234567890")
# batch_delete_histories(["hist_1", "hist_2", "hist_3"])
```

### 重新生成策略

```python
import requests

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def regenerate_from_history(history_id: str):
    """基于历史记录重新生成策略

    Args:
        history_id: 历史记录ID

    Returns:
        新生成的策略数据
    """
    print(f"基于历史记录重新生成: {history_id}")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/history/{history_id}/regenerate",
        headers=headers
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]

        print("✅ 重新生成成功!")
        print(f"使用模型: {data['model_used']}")
        print(f"请求ID: {data['request_id']}")

        if data['tokens_used']:
            print(f"Token使用: {data['tokens_used']}")

        if data['elapsed_time']:
            print(f"生成耗时: {data['elapsed_time']:.2f}秒")

        print("\n策略说明:")
        print(data['explanation'])

        print("\n生成的代码:")
        print("-" * 60)
        print(data['code'])

        return data
    elif response.status_code == 404:
        print(f"❌ 历史记录不存在: {history_id}")
    elif response.status_code == 403:
        print(f"❌ 无权访问该记录: {history_id}")
    else:
        print(f"❌ 重新生成失败: {result.get('message', '未知错误')}")

    return None

# 使用示例（需要先获取一个有效的 history_id）
# new_strategy = regenerate_from_history("hist_1234567890")
```

---

## 模板库使用示例

### 获取模板列表

```python
import requests
from typing import Optional

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def get_templates(category: Optional[str] = None, tag: Optional[str] = None):
    """获取策略模板列表

    Args:
        category: 按分类筛选
        tag: 按标签筛选
    """
    params = {}
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag

    response = requests.get(
        f"{BASE_URL}/templates",
        headers=headers,
        params=params
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]
        templates = data["list"]

        print("=" * 60)
        print(f"策略模板列表 (共 {data['total']} 个)")
        print("=" * 60)

        for i, tpl in enumerate(templates, 1):
            print(f"\n[{i}] {tpl['name']}")
            print(f"    ID: {tpl['id']}")
            print(f"    分类: {tpl['category']}")
            print(f"    描述: {tpl['description']}")
            print(f"    标签: {', '.join(tpl['tags'])}")
            print(f"    变量:")
            for var in tpl['variables']:
                required = "必填" if var.get('required') else "可选"
                default = f", 默认: {var.get('default')}" if 'default' in var else ""
                print(f"      - {var['name']} ({var['type']}, {required}{default})")

        return templates
    else:
        print(f"❌ 获取失败: {result['message']}")
        return []

# 获取所有模板
all_templates = get_templates()

# 按分类筛选
print("\n" + "=" * 60)
print("趋势跟踪策略模板")
print("=" * 60)
trend_templates = get_templates(category="trend_following")

# 按标签筛选
print("\n" + "=" * 60)
print("包含'均线'标签的模板")
print("=" * 60)
ma_templates = get_templates(tag="均线")
```

### 获取模板详情

```python
import requests

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def get_template_detail(template_id: str):
    """获取单个模板详情"""
    response = requests.get(
        f"{BASE_URL}/templates/{template_id}",
        headers=headers
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]

        print("=" * 60)
        print(f"模板详情: {data['name']}")
        print("=" * 60)
        print(f"ID: {data['id']}")
        print(f"分类: {data['category']}")
        print(f"描述: {data['description']}")
        print(f"标签: {', '.join(data['tags'])}")
        print(f"创建时间: {data['created_at']}")
        print("-" * 60)
        print("变量定义:")
        for var in data['variables']:
            print(f"  - {var['name']}")
            print(f"    类型: {var['type']}")
            print(f"    必填: {var.get('required', False)}")
            if 'default' in var:
                print(f"    默认值: {var['default']}")
        print("-" * 60)
        print("代码模板:")
        print(data['code_template'])

        return data
    elif response.status_code == 404:
        print(f"❌ 模板不存在: {template_id}")
        return None
    else:
        print(f"❌ 获取失败: {result.get('message', '未知错误')}")
        return None

# 使用示例
# template = get_template_detail("tpl_001")
```

### 基于模板生成

```python
import requests
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def generate_from_template(
    template_id: str,
    variables: Dict[str, Any],
    additional_requirement: Optional[str] = None,
    model_id: Optional[str] = None,
    temperature: Optional[float] = None
):
    """基于模板生成策略

    Args:
        template_id: 模板ID
        variables: 模板变量值
        additional_requirement: 额外需求描述
        model_id: 使用的模型ID
        temperature: 温度参数
    """
    payload = {
        "template_id": template_id,
        "variables": variables
    }

    if additional_requirement:
        payload["additional_requirement"] = additional_requirement
    if model_id:
        payload["model_id"] = model_id
    if temperature is not None:
        payload["temperature"] = temperature

    print("基于模板生成策略...")
    print(f"模板ID: {template_id}")
    print(f"变量: {variables}")

    response = requests.post(
        f"{BASE_URL}/generate-from-template",
        headers=headers,
        json=payload
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]

        print("\n" + "=" * 60)
        print("✅ 基于模板生成成功!")
        print("=" * 60)
        print(f"说明: {data['explanation']}")
        print(f"模型: {data['model_used']}")
        print(f"请求ID: {data['request_id']}")
        print("-" * 60)
        print("生成的代码:")
        print(data['code'])

        return data
    else:
        print(f"❌ 生成失败: {result['message']}")
        return None

# 示例1: 使用双均线模板
print("=" * 60)
print("示例1: 双均线策略")
print("=" * 60)

result1 = generate_from_template(
    template_id="tpl_001",
    variables={
        "strategy_name": "MyDualMAStrategy",
        "fast_period": 10,
        "slow_period": 20
    },
    additional_requirement="添加止损逻辑，当亏损超过5%时平仓"
)

# 示例2: 使用RSI模板
print("\n" + "=" * 60)
print("示例2: RSI策略")
print("=" * 60)

result2 = generate_from_template(
    template_id="tpl_002",
    variables={
        "strategy_name": "MyRSIStrategy",
        "rsi_period": 14,
        "overbought": 70,
        "oversold": 30
    }
)

# 示例3: 使用AI优化模板代码
print("\n" + "=" * 60)
print("示例3: AI优化模板")
print("=" * 60)

result3 = generate_from_template(
    template_id="tpl_001",
    variables={
        "strategy_name": "OptimizedMAStrategy",
        "fast_period": 5,
        "slow_period": 30
    },
    additional_requirement="""
    请优化以下方面：
    1. 添加仓位管理，根据ATR动态调整仓位
    2. 添加趋势过滤，只在趋势明确时交易
    3. 优化入场时机，使用更精细的信号确认
    """,
    model_id="gpt-4",
    temperature=0.5
)
```

---

## 性能统计查询示例

```python
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def get_performance_stats(days: int = 30):
    """获取性能统计

    Args:
        days: 统计天数，默认30天
    """
    response = requests.get(
        f"{BASE_URL}/stats",
        headers=headers,
        params={"days": days}
    )

    result = response.json()

    if result["code"] == 0:
        data = result["data"]

        print("=" * 60)
        print(f"📊 性能统计 (最近 {days} 天)")
        print("=" * 60)
        print(f"统计周期: {data['period_start']} ~ {data['period_end']}")
        print("-" * 60)

        # 总体统计
        print("总体统计:")
        print(f"  总生成次数: {data['total_generations']}")
        print(f"  成功次数: {data['successful_generations']}")
        print(f"  失败次数: {data['failed_generations']}")
        print(f"  成功率: {data['success_rate']:.2f}%")
        print(f"  平均生成时间: {data['average_generation_time']:.2f}秒")
        print(f"  总Token使用量: {data['total_tokens_used']:,}")

        # 模型使用统计
        if data['model_usage_stats']:
            print("\n模型使用统计:")
            for model, count in data['model_usage_stats'].items():
                percentage = (count / data['total_generations'] * 100) if data['total_generations'] > 0 else 0
                print(f"  - {model}: {count} 次 ({percentage:.1f}%)")

        # 每日统计
        if data['daily_stats']:
            print("\n每日统计:")
            print(f"  {'日期':<12} {'生成次数':>8} {'成功':>8} {'失败':>8} {'成功率':>8}")
            print("  " + "-" * 52)

            for day in data['daily_stats']:
                success_rate = (day['success'] / day['count'] * 100) if day['count'] > 0 else 0
                failed = day['count'] - day['success']
                print(f"  {day['date']:<12} {day['count']:>8} {day['success']:>8} {failed:>8} {success_rate:>7.1f}%")

        return data
    else:
        print(f"❌ 获取失败: {result['message']}")
        return None

def compare_stats(days_list: list):
    """对比不同时间段的统计"""
    print("=" * 60)
    print("📊 多时间段对比")
    print("=" * 60)

    results = []
    for days in days_list:
        response = requests.get(
            f"{BASE_URL}/stats",
            headers=headers,
            params={"days": days}
        )

        result = response.json()
        if result["code"] == 0:
            results.append((days, result["data"]))

    # 输出对比表格
    print(f"{'时间段':<10} {'总次数':>8} {'成功':>8} {'成功率':>8} {'平均耗时':>10}")
    print("-" * 60)

    for days, data in results:
        print(f"{days}天{'':<6} {data['total_generations']:>8} "
              f"{data['successful_generations']:>8} {data['success_rate']:>7.2f}% "
              f"{data['average_generation_time']:>9.2f}s")

    return results

# 获取最近30天的统计
stats = get_performance_stats(days=30)

# 获取最近7天的统计
print("\n")
weekly_stats = get_performance_stats(days=7)

# 对比不同时间段
print("\n")
compare_stats([7, 14, 30, 90])
```

---

## 完整端到端流程示例

以下是一个完整的端到端使用流程，展示了从策略生成到验证、保存历史记录、使用模板和查看统计的完整过程：

```python
import requests
import time
from typing import Optional

class StrategyGeneratorClient:
    """策略生成器客户端"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def generate_strategy(
        self,
        requirement: str,
        model_id: Optional[str] = None,
        temperature: float = 0.7
    ) -> Optional[dict]:
        """生成策略"""
        print(f"\n🤖 正在生成策略...")
        print(f"需求: {requirement[:80]}...")

        response = requests.post(
            f"{self.base_url}/generate-sync",
            headers=self.headers,
            json={
                "requirement": requirement,
                "model_id": model_id,
                "temperature": temperature
            },
            timeout=120
        )

        result = response.json()

        if result["code"] == 0:
            data = result["data"]
            print(f"✅ 生成成功!")
            print(f"   模型: {data['model_used']}")
            print(f"   Token: {data['tokens_used']['total_tokens'] if data['tokens_used'] else 'N/A'}")
            print(f"   耗时: {data['elapsed_time']:.2f}秒")
            return data
        else:
            print(f"❌ 生成失败: {result['message']}")
            return None

    def validate_code(self, code: str) -> bool:
        """验证代码"""
        print(f"\n🔍 正在验证代码...")

        response = requests.post(
            f"{self.base_url}/validate-code",
            headers=self.headers,
            json={"code": code, "language": "python"}
        )

        result = response.json()
        data = result["data"]

        if data["valid"]:
            print("✅ 代码验证通过")
            if data["warnings"]:
                print(f"   警告: {len(data['warnings'])} 个")
            return True
        else:
            print(f"❌ 验证失败")
            print(f"   错误: {data['errors']}")
            return False

    def get_templates(self) -> list:
        """获取模板列表"""
        print(f"\n📚 获取模板列表...")

        response = requests.get(
            f"{self.base_url}/templates",
            headers=self.headers
        )

        result = response.json()

        if result["code"] == 0:
            templates = result["data"]["list"]
            print(f"✅ 找到 {len(templates)} 个模板")
            return templates
        else:
            print(f"❌ 获取失败: {result['message']}")
            return []

    def generate_from_template(
        self,
        template_id: str,
        variables: dict,
        additional_requirement: Optional[str] = None
    ) -> Optional[dict]:
        """基于模板生成"""
        print(f"\n🎨 基于模板生成策略...")
        print(f"模板: {template_id}")

        response = requests.post(
            f"{self.base_url}/generate-from-template",
            headers=self.headers,
            json={
                "template_id": template_id,
                "variables": variables,
                "additional_requirement": additional_requirement
            }
        )

        result = response.json()

        if result["code"] == 0:
            print("✅ 基于模板生成成功!")
            return result["data"]
        else:
            print(f"❌ 生成失败: {result['message']}")
            return None

    def get_history(self, page: int = 1, page_size: int = 10) -> list:
        """获取历史记录"""
        print(f"\n📜 获取历史记录...")

        response = requests.get(
            f"{self.base_url}/history",
            headers=self.headers,
            params={"page": page, "page_size": page_size}
        )

        result = response.json()

        if result["code"] == 0:
            history = result["data"]["list"]
            total = result["data"]["pagination"]["total"]
            print(f"✅ 找到 {total} 条历史记录")
            return history
        else:
            print(f"❌ 获取失败: {result['message']}")
            return []

    def get_stats(self, days: int = 30) -> Optional[dict]:
        """获取性能统计"""
        print(f"\n📊 获取性能统计 (最近 {days} 天)...")

        response = requests.get(
            f"{self.base_url}/stats",
            headers=self.headers,
            params={"days": days}
        )

        result = response.json()

        if result["code"] == 0:
            data = result["data"]
            print("✅ 统计信息:")
            print(f"   总生成: {data['total_generations']}")
            print(f"   成功率: {data['success_rate']:.2f}%")
            print(f"   平均耗时: {data['average_generation_time']:.2f}秒")
            return data
        else:
            print(f"❌ 获取失败: {result['message']}")
            return None


def main():
    """完整的端到端流程示例"""

    # 配置
    BASE_URL = "http://localhost:8000/api/ai-models/strategy"
    TOKEN = "your_jwt_token_here"

    # 创建客户端
    client = StrategyGeneratorClient(BASE_URL, TOKEN)

    print("=" * 70)
    print("🚀 策略生成 API 端到端使用示例")
    print("=" * 70)

    # 步骤1: 生成策略
    print("\n" + "=" * 70)
    print("步骤 1: 生成策略")
    print("=" * 70)

    requirement = """
    创建一个双均线策略，具体要求：
    1. 使用 10 日和 30 日移动平均线
    2. 当短期均线上穿长期均线时买入
    3. 当短期均线下穿长期均线时卖出
    4. 添加基本的仓位管理
    """

    strategy = client.generate_strategy(requirement, temperature=0.7)

    if not strategy:
        print("❌ 策略生成失败，退出流程")
        return

    # 步骤2: 验证代码
    print("\n" + "=" * 70)
    print("步骤 2: 验证生成的代码")
    print("=" * 70)

    is_valid = client.validate_code(strategy["code"])

    if not is_valid:
        print("⚠️ 代码验证未通过，但仍继续流程")

    # 步骤3: 查看模板库
    print("\n" + "=" * 70)
    print("步骤 3: 查看模板库")
    print("=" * 70)

    templates = client.get_templates()

    if templates:
        print("\n可用模板:")
        for i, tpl in enumerate(templates[:3], 1):
            print(f"  {i}. {tpl['name']} - {tpl['description']}")

    # 步骤4: 基于模板生成另一个策略
    print("\n" + "=" * 70)
    print("步骤 4: 基于模板生成策略")
    print("=" * 70)

    if templates:
        template_strategy = client.generate_from_template(
            template_id=templates[0]["id"],
            variables={
                "strategy_name": "TemplateMAStrategy",
                "fast_period": 5,
                "slow_period": 20
            },
            additional_requirement="添加止损逻辑，亏损超过3%时平仓"
        )

    # 步骤5: 查看历史记录
    print("\n" + "=" * 70)
    print("步骤 5: 查看历史记录")
    print("=" * 70)

    history = client.get_history(page=1, page_size=5)

    if history:
        print("\n最近的历史记录:")
        for i, item in enumerate(history[:3], 1):
            print(f"  {i}. {item['requirement'][:50]}... ({item['status']})")

    # 步骤6: 查看性能统计
    print("\n" + "=" * 70)
    print("步骤 6: 查看性能统计")
    print("=" * 70)

    stats = client.get_stats(days=30)

    # 总结
    print("\n" + "=" * 70)
    print("✅ 流程完成!")
    print("=" * 70)
    print("\n已完成的操作:")
    print("  1. ✅ 生成了自定义策略")
    print("  2. ✅ 验证了代码")
    print("  3. ✅ 查看了模板库")
    print("  4. ✅ 基于模板生成了策略")
    print("  5. ✅ 查看了历史记录")
    print("  6. ✅ 查看了性能统计")

    if strategy:
        print("\n生成的策略代码预览:")
        print("-" * 70)
        code_preview = strategy["code"][:500]
        print(code_preview)
        if len(strategy["code"]) > 500:
            print("... (代码已截断)")


if __name__ == "__main__":
    main()
```

---

## 错误处理示例

```python
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

BASE_URL = "http://localhost:8000/api/ai-models/strategy"
TOKEN = "your_jwt_token_here"

def safe_api_call(func):
    """API调用装饰器，统一处理错误"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Timeout:
            print("❌ 请求超时，请稍后重试")
        except ConnectionError:
            print("❌ 连接失败，请检查网络或服务器状态")
        except RequestException as e:
            print(f"❌ 请求错误: {e}")
        except Exception as e:
            print(f"❌ 未知错误: {e}")
        return None
    return wrapper

@safe_api_call
def generate_with_error_handling(requirement: str):
    """带错误处理的策略生成"""
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"{BASE_URL}/generate-sync",
        headers=headers,
        json={
            "requirement": requirement,
            "temperature": 0.7
        },
        timeout=60
    )

    # 处理 HTTP 错误状态码
    if response.status_code == 401:
        print("❌ 认证失败: Token 无效或已过期")
        return None
    elif response.status_code == 400:
        error_detail = response.json().get("detail", {})
        print(f"❌ 请求错误: {error_detail.get('message', '参数错误')}")
        return None
    elif response.status_code == 500:
        print("❌ 服务器错误，请稍后重试")
        return None

    result = response.json()

    # 处理业务错误
    if result.get("code") != 0:
        error_code = result.get("data", {}).get("error_code")
        message = result.get("message", "未知错误")

        error_handlers = {
            "api_authentication_error": lambda: print("❌ API 认证失败，请检查 API 密钥配置"),
            "api_rate_limit_error": lambda: print("❌ 请求过于频繁，请稍后重试"),
            "api_connection_error": lambda: print("❌ API 连接失败，请检查网络"),
            "response_parse_error": lambda: print("❌ 响应解析失败，请重试"),
            "strategy_generation_error": lambda: print("❌ 策略生成失败，请优化需求描述"),
        }

        handler = error_handlers.get(error_code)
        if handler:
            handler()
        else:
            print(f"❌ {message}")

        return None

    return result["data"]

# 使用示例
# result = generate_with_error_handling("创建一个双均线策略")
```

---

*文档版本: 1.0.0*  
*最后更新: 2026-03-08*  
*作者: QuantCell Team*
