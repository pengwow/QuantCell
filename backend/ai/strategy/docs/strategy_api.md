# 策略生成 API 文档

## 目录

- [概述](#概述)
- [认证方式](#认证方式)
- [基础信息](#基础信息)
- [端点列表](#端点列表)
  - [流式生成策略](#1-流式生成策略)
  - [同步生成策略](#2-同步生成策略)
  - [验证策略代码](#3-验证策略代码)
  - [通用代码验证](#4-通用代码验证)
  - [获取历史记录列表](#5-获取历史记录列表)
  - [获取历史记录详情](#6-获取历史记录详情)
  - [删除历史记录](#7-删除历史记录)
  - [基于历史重新生成](#8-基于历史重新生成)
  - [获取模板列表](#9-获取模板列表)
  - [获取模板详情](#10-获取模板详情)
  - [基于模板生成](#11-基于模板生成)
  - [获取性能统计](#12-获取性能统计)
- [数据模型](#数据模型)
  - [StrategyGenerateRequest](#strategygeneraterequest)
  - [StrategyGenerateResponse](#strategygenerateresponse)
  - [StrategyValidateRequest](#strategyvalidaterequest)
  - [StrategyValidateResponse](#strategyvalidateresponse)
  - [CodeValidationRequest](#codevalidationrequest)
  - [CodeValidationResponse](#codevalidationresponse)
  - [StrategyHistoryResponse](#strategyhistoryresponse)
  - [StrategyTemplateResponse](#strategytemplateresponse)
  - [StrategyGenerateFromTemplateRequest](#strategygeneratefromtemplaterequest)
  - [PerformanceStatsResponse](#performancestatsresponse)
- [错误处理](#错误处理)
- [使用场景示例](#使用场景示例)

---

## 概述

策略生成 API 提供基于 AI 的策略代码自动生成功能，支持通过自然语言描述生成可执行的量化交易策略代码。该 API 支持两种调用方式：

1. **流式生成 (SSE)** - 实时返回生成内容，适用于需要展示生成进度的场景
2. **同步生成** - 一次性返回完整结果，适用于后台批量处理

此外，API 还提供代码验证、历史记录管理、模板库和性能统计等功能。

### 主要特性

- 🤖 基于 GPT-4 等大语言模型的智能代码生成
- 📝 支持自然语言描述策略需求
- 🔄 流式/同步两种生成模式
- ✅ 代码语法验证
- 📚 策略历史记录管理
- 🎨 策略模板库
- 📊 性能统计分析
- 🌡️ 可调的生成参数（温度、模型选择）
- 🔐 JWT 认证保护

---

## 认证方式

所有 API 端点都需要 JWT (JSON Web Token) 认证。

### 获取 Token

通过登录接口获取 JWT Token：

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{
        "username": "your_username",
        "password": "your_password"
    }'
```

### 使用 Token

在请求头中添加 `Authorization` 字段：

```
Authorization: Bearer <your_jwt_token>
```

### Token 有效期

- 默认有效期：24 小时
- Token 过期后需要重新登录获取

---

## 基础信息

| 项目 | 说明 |
|------|------|
| 基础 URL | `http://localhost:8000/api/ai-models/strategy` |
| 协议 | HTTP/HTTPS |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |

---

## 端点列表

### 1. 流式生成策略

通过 SSE (Server-Sent Events) 方式流式生成策略代码。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/generate` |
| 认证 | 需要 JWT Token |
| Content-Type | `application/json` |

#### 请求参数

**请求体 (Request Body)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `requirement` | string | ✅ | 策略需求描述，10-5000 字符 | `"创建一个双均线策略..."` |
| `model_id` | string | ❌ | 模型 ID，不传使用系统默认 | `"gpt-4"` |
| `temperature` | float | ❌ | 温度参数 0-2，越高越创造性 | `0.7` |
| `template_vars` | object | ❌ | 模板变量，替换提示词占位符 | `{"strategy_name": "MyStrategy"}` |

#### 响应格式

**Content-Type**: `text/event-stream`

SSE 事件格式：每个事件以 `data: ` 开头，以 `\n\n` 结束。

#### SSE 事件类型

**1. content - 内容片段**

```json
{
    "type": "content",
    "content": "class DualMAStrategy:",
    "request_id": "stream_123456"
}
```

**2. done - 生成完成**

```json
{
    "type": "done",
    "code": "class DualMAStrategy:\n    pass",
    "metadata": {
        "model": "gpt-4",
        "elapsed_time": 2.5,
        "chunk_count": 42
    },
    "request_id": "stream_123456"
}
```

**3. error - 生成错误**

```json
{
    "type": "error",
    "error": "API密钥无效",
    "error_code": "api_authentication_error",
    "request_id": "stream_123456"
}
```

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 流式响应开始 |
| 400 | 请求参数错误或未配置 AI 模型 |
| 401 | 未授权访问 |
| 500 | 服务器内部错误 |

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/generate" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{
        "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
        "model_id": "gpt-4",
        "temperature": 0.7,
        "template_vars": {
            "strategy_name": "DualMAStrategy",
            "symbol": "BTC/USDT",
            "timeframe": "1h"
        }
    }'
```

**JavaScript (EventSource)**

```javascript
const eventSource = new EventSource('/api/ai-models/strategy/generate', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        requirement: '创建一个双均线策略，当短期均线上穿长期均线时买入',
        temperature: 0.7
    })
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'content':
            // 追加显示生成内容
            document.getElementById('code').textContent += data.content;
            break;
        case 'done':
            // 生成完成，保存完整代码
            console.log('生成完成:', data.code);
            console.log('元数据:', data.metadata);
            eventSource.close();
            break;
        case 'error':
            // 处理错误
            console.error('生成错误:', data.error);
            eventSource.close();
            break;
    }
};

eventSource.onerror = (error) => {
    console.error('SSE连接错误:', error);
    eventSource.close();
};
```

**Python (aiohttp)**

```python
import aiohttp
import json

async def generate_strategy_stream():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:8000/api/ai-models/strategy/generate',
            headers={'Authorization': 'Bearer <token>'},
            json={
                'requirement': '创建一个双均线策略',
                'temperature': 0.7
            }
        ) as response:
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    if data['type'] == 'content':
                        print(f"收到内容: {data['content']}")
                    elif data['type'] == 'done':
                        print(f"生成完成: {data['code']}")
                        break
                    elif data['type'] == 'error':
                        print(f"错误: {data['error']}")
                        break
```

---

### 2. 同步生成策略

一次性生成完整的策略代码并返回。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/generate-sync` |
| 认证 | 需要 JWT Token |
| Content-Type | `application/json` |

#### 请求参数

与流式生成相同，参考 [StrategyGenerateRequest](#strategygeneraterequest)。

#### 响应格式

**成功响应 (200 OK)**

```json
{
    "code": 0,
    "message": "策略生成成功",
    "data": {
        "code": "class DualMAStrategy(BaseStrategy):\n    def __init__(self, config):\n        super().__init__(config)\n    ...",
        "explanation": "这是一个基于双均线的趋势跟踪策略...",
        "model_used": "gpt-4",
        "tokens_used": {
            "prompt_tokens": 500,
            "completion_tokens": 800,
            "total_tokens": 1300
        },
        "elapsed_time": 3.5,
        "request_id": "req_abc123"
    }
}
```

**失败响应**

```json
{
    "code": 1,
    "message": "API认证失败: API密钥无效或已过期",
    "data": {
        "error_code": "api_authentication_error"
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | integer | 业务状态码，0=成功，1=失败 |
| `message` | string | 状态描述 |
| `data.code` | string | 生成的策略代码 |
| `data.explanation` | string | 策略说明文档 |
| `data.model_used` | string | 实际使用的模型 ID |
| `data.tokens_used` | object | Token 使用情况 |
| `data.elapsed_time` | float | 生成耗时(秒) |
| `data.request_id` | string | 请求 ID，用于追踪 |

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 生成成功 |
| 400 | 请求参数错误或未配置 AI 模型 |
| 401 | 未授权访问 |
| 500 | 生成失败 |

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/generate-sync" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{
        "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入",
        "model_id": "gpt-4",
        "temperature": 0.7
    }'
```

**Python (requests)**

```python
import requests

def generate_strategy_sync():
    response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/generate-sync',
        headers={'Authorization': 'Bearer <token>'},
        json={
            'requirement': '创建一个双均线策略，当短期均线上穿长期均线时买入',
            'model_id': 'gpt-4',
            'temperature': 0.7
        },
        timeout=60  # 设置较长超时时间
    )

    result = response.json()

    if result['code'] == 0:
        print('生成成功!')
        print(f'代码:\n{result["data"]["code"]}')
        print(f'说明: {result["data"]["explanation"]}')
        print(f'使用模型: {result["data"]["model_used"]}')
        print(f'Token使用: {result["data"]["tokens_used"]}')
        print(f'耗时: {result["data"]["elapsed_time"]}秒')
    else:
        print(f'生成失败: {result["message"]}')
        if result.get('data', {}).get('error_code'):
            print(f'错误码: {result["data"]["error_code"]}')

    return result
```

---

### 3. 验证策略代码

对策略代码进行语法验证和基本结构检查。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/validate` |
| 认证 | 需要 JWT Token |
| Content-Type | `application/json` |

#### 请求参数

**请求体 (Request Body)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `code` | string | ✅ | 需要验证的策略代码，至少 1 个字符 | `"class MyStrategy:\n    pass"` |

#### 响应格式

**验证通过**

```json
{
    "code": 0,
    "message": "验证完成",
    "data": {
        "valid": true,
        "errors": [],
        "warnings": [
            "警告: 代码中未找到类定义",
            "警告: 未检测到策略基类继承"
        ]
    }
}
```

**验证失败**

```json
{
    "code": 0,
    "message": "验证完成",
    "data": {
        "valid": false,
        "errors": [
            "语法错误: 第5行缩进错误",
            "语法错误: 第8行缺少冒号"
        ],
        "warnings": [
            "警告: 代码中未找到类定义"
        ]
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | integer | 业务状态码，0=验证完成 |
| `message` | string | 状态描述 |
| `data.valid` | boolean | 代码是否有效 |
| `data.errors` | array | 错误列表 |
| `data.warnings` | array | 警告列表 |

#### 验证规则

1. **语法检查** - 使用 Python AST 解析器检查代码语法
2. **结构检查** - 检查是否包含类定义
3. **方法检查** - 检查是否包含必要的方法
4. **导入检查** - 检查导入语句是否合法

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/validate" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{
        "code": "class MyStrategy:\n    def __init__(self):\n        pass"
    }'
```

**Python**

```python
import requests

def validate_strategy_code(code):
    response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/validate',
        headers={'Authorization': 'Bearer <token>'},
        json={'code': code}
    )

    result = response.json()
    data = result['data']

    if data['valid']:
        print('✅ 代码验证通过')
        if data['warnings']:
            print('⚠️ 警告:')
            for warning in data['warnings']:
                print(f'  - {warning}')
    else:
        print('❌ 验证失败')
        print('错误:')
        for error in data['errors']:
            print(f'  - {error}')

    return data['valid']

# 使用示例
code = '''
from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class DualMAStrategy(BaseStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast = int(config.params.get("fast", 10))
        self.slow = int(config.params.get("slow", 20))

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])
        return Action("hold", 0.0, 0.0, self.config.name, 0)
'''

is_valid = validate_strategy_code(code)
```

---

### 4. 通用代码验证

对任意代码进行语法验证和基本结构检查，支持多种编程语言。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/validate-code` |
| 认证 | 需要 JWT Token |
| Content-Type | `application/json` |

#### 请求参数

**请求体 (Request Body)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `code` | string | ✅ | 需要验证的代码 | `"class MyStrategy:\n    pass"` |
| `language` | string | ❌ | 代码语言，默认 `python` | `"python"` |

#### 响应格式

**验证通过**

```json
{
    "code": 0,
    "message": "验证完成",
    "data": {
        "valid": true,
        "errors": [],
        "warnings": [],
        "suggestions": [
            "建议: 添加代码注释以提高可读性"
        ]
    }
}
```

**验证失败**

```json
{
    "code": 0,
    "message": "验证完成",
    "data": {
        "valid": false,
        "errors": [
            "语法错误: 第3行 - 缩进错误"
        ],
        "warnings": [
            "警告: 代码中未找到类定义"
        ],
        "suggestions": [
            "建议: 添加__init__方法进行初始化"
        ]
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | integer | 业务状态码，0=验证完成 |
| `message` | string | 状态描述 |
| `data.valid` | boolean | 代码是否有效 |
| `data.errors` | array | 错误列表 |
| `data.warnings` | array | 警告列表 |
| `data.suggestions` | array | 改进建议列表 |

#### 验证规则

1. **语法检查** - 使用 Python AST 解析器检查代码语法
2. **结构检查** - 检查是否包含类定义
3. **策略基类检查** - 检查是否继承 Strategy 基类
4. **代码建议** - 提供代码改进建议

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/validate-code" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{
        "code": "class MyStrategy:\n    def __init__(self):\n        pass",
        "language": "python"
    }'
```

**Python**

```python
import requests

def validate_code(code, language="python"):
    response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/validate-code',
        headers={'Authorization': 'Bearer <token>'},
        json={'code': code, 'language': language}
    )

    result = response.json()
    data = result['data']

    if data['valid']:
        print('✅ 代码验证通过')
    else:
        print('❌ 验证失败')
        print('错误:', data['errors'])

    if data['warnings']:
        print('⚠️ 警告:', data['warnings'])

    if data['suggestions']:
        print('💡 建议:', data['suggestions'])

    return data
```

---

### 5. 获取历史记录列表

获取当前用户的策略生成历史记录列表，支持分页和筛选。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/history` |
| 认证 | 需要 JWT Token |

#### 请求参数

**查询参数 (Query Parameters)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `page` | integer | ❌ | 页码，从1开始，默认1 | `1` |
| `page_size` | integer | ❌ | 每页数量，默认20，最大100 | `20` |
| `status` | string | ❌ | 按状态筛选：success/failed/pending | `success` |
| `model_id` | string | ❌ | 按模型ID筛选 | `gpt-4` |
| `start_date` | datetime | ❌ | 开始日期 | `2026-03-01T00:00:00` |
| `end_date` | datetime | ❌ | 结束日期 | `2026-03-08T23:59:59` |

#### 响应格式

```json
{
    "code": 0,
    "message": "获取成功",
    "data": {
        "list": [
            {
                "id": "hist_1234567890",
                "user_id": "user_123",
                "requirement": "创建一个双均线策略",
                "code": "class DualMAStrategy:\n    pass",
                "model_id": "gpt-4",
                "explanation": "这是一个双均线策略...",
                "status": "success",
                "tokens_used": {
                    "prompt_tokens": 500,
                    "completion_tokens": 800,
                    "total_tokens": 1300
                },
                "elapsed_time": 3.5,
                "created_at": "2026-03-08T10:30:00",
                "updated_at": null
            }
        ],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 100,
            "total_pages": 5
        }
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | integer | 业务状态码，0=成功 |
| `data.list` | array | 历史记录列表 |
| `data.list[].id` | string | 历史记录ID |
| `data.list[].requirement` | string | 策略需求描述 |
| `data.list[].code` | string | 生成的策略代码 |
| `data.list[].model_id` | string | 使用的模型ID |
| `data.list[].status` | string | 生成状态 |
| `data.list[].created_at` | datetime | 创建时间 |
| `data.pagination` | object | 分页信息 |

#### 请求示例

**cURL**

```bash
curl -X GET "http://localhost:8000/api/ai-models/strategy/history?page=1&page_size=20&status=success" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Python**

```python
import requests

def get_history_list(page=1, page_size=20, status=None):
    params = {
        'page': page,
        'page_size': page_size
    }
    if status:
        params['status'] = status

    response = requests.get(
        'http://localhost:8000/api/ai-models/strategy/history',
        headers={'Authorization': 'Bearer <token>'},
        params=params
    )

    result = response.json()
    if result['code'] == 0:
        print(f"获取到 {result['data']['pagination']['total']} 条记录")
        for item in result['data']['list']:
            print(f"- {item['id']}: {item['requirement'][:50]}...")

    return result['data']
```

---

### 6. 获取历史记录详情

获取单条策略历史记录的详细信息。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/history/{history_id}` |
| 认证 | 需要 JWT Token |

#### 请求参数

**路径参数 (Path Parameters)**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `history_id` | string | ✅ | 历史记录ID |

#### 响应格式

```json
{
    "code": 0,
    "message": "获取成功",
    "data": {
        "id": "hist_1234567890",
        "user_id": "user_123",
        "requirement": "创建一个双均线策略",
        "code": "class DualMAStrategy:\n    pass",
        "model_id": "gpt-4",
        "explanation": "这是一个双均线策略...",
        "status": "success",
        "tokens_used": {
            "prompt_tokens": 500,
            "completion_tokens": 800,
            "total_tokens": 1300
        },
        "elapsed_time": 3.5,
        "created_at": "2026-03-08T10:30:00",
        "updated_at": null
    }
}
```

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 获取成功 |
| 404 | 历史记录不存在 |
| 403 | 无权访问该记录 |

#### 请求示例

**cURL**

```bash
curl -X GET "http://localhost:8000/api/ai-models/strategy/history/hist_1234567890" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

---

### 7. 删除历史记录

删除指定的策略历史记录。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `DELETE` |
| 路径 | `/history/{history_id}` |
| 认证 | 需要 JWT Token |

#### 请求参数

**路径参数 (Path Parameters)**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `history_id` | string | ✅ | 历史记录ID |

#### 响应格式

```json
{
    "code": 0,
    "message": "删除成功",
    "data": {
        "id": "hist_1234567890"
    }
}
```

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 删除成功 |
| 404 | 历史记录不存在 |
| 403 | 无权删除该记录 |

#### 请求示例

**cURL**

```bash
curl -X DELETE "http://localhost:8000/api/ai-models/strategy/history/hist_1234567890" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Python**

```python
import requests

def delete_history(history_id):
    response = requests.delete(
        f'http://localhost:8000/api/ai-models/strategy/history/{history_id}',
        headers={'Authorization': 'Bearer <token>'}
    )

    result = response.json()
    if result['code'] == 0:
        print(f"✅ 历史记录 {history_id} 已删除")
    else:
        print(f"❌ 删除失败: {result['message']}")

    return result['code'] == 0
```

---

### 8. 基于历史重新生成

使用历史记录中的需求描述重新生成策略代码。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/history/{history_id}/regenerate` |
| 认证 | 需要 JWT Token |

#### 请求参数

**路径参数 (Path Parameters)**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `history_id` | string | ✅ | 历史记录ID |

#### 响应格式

```json
{
    "code": 0,
    "message": "重新生成成功",
    "data": {
        "code": "class DualMAStrategy:\n    pass",
        "explanation": "这是一个双均线策略...",
        "model_used": "gpt-4",
        "tokens_used": {
            "prompt_tokens": 500,
            "completion_tokens": 800,
            "total_tokens": 1300
        },
        "elapsed_time": 3.5,
        "request_id": "req_new_123"
    }
}
```

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 重新生成成功 |
| 404 | 历史记录不存在 |
| 403 | 无权访问该记录 |

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/history/hist_1234567890/regenerate" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Python**

```python
import requests

def regenerate_from_history(history_id):
    response = requests.post(
        f'http://localhost:8000/api/ai-models/strategy/history/{history_id}/regenerate',
        headers={'Authorization': 'Bearer <token>'}
    )

    result = response.json()
    if result['code'] == 0:
        print(f"✅ 重新生成成功")
        print(f"新代码:\n{result['data']['code']}")
    else:
        print(f"❌ 重新生成失败: {result['message']}")

    return result['data']
```

---

### 9. 获取模板列表

获取策略模板列表，支持按分类和标签筛选。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/templates` |
| 认证 | 需要 JWT Token |

#### 请求参数

**查询参数 (Query Parameters)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `category` | string | ❌ | 按分类筛选 | `trend_following` |
| `tag` | string | ❌ | 按标签筛选 | `均线` |

#### 响应格式

```json
{
    "code": 0,
    "message": "获取成功",
    "data": {
        "list": [
            {
                "id": "tpl_001",
                "name": "双均线策略模板",
                "description": "基于双均线的趋势跟踪策略模板",
                "category": "trend_following",
                "code_template": "class {{strategy_name}}(BaseStrategy):\n    def __init__(self, config):\n        super().__init__(config)\n...",
                "variables": [
                    {"name": "strategy_name", "type": "string", "required": true},
                    {"name": "fast_period", "type": "int", "default": 10},
                    {"name": "slow_period", "type": "int", "default": 20}
                ],
                "tags": ["趋势", "均线", "经典"],
                "created_at": "2026-03-01T10:00:00",
                "updated_at": null
            }
        ],
        "total": 2
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.list[].id` | string | 模板ID |
| `data.list[].name` | string | 模板名称 |
| `data.list[].description` | string | 模板描述 |
| `data.list[].category` | string | 模板分类 |
| `data.list[].code_template` | string | 代码模板 |
| `data.list[].variables` | array | 模板变量定义 |
| `data.list[].tags` | array | 标签列表 |

#### 请求示例

**cURL**

```bash
curl -X GET "http://localhost:8000/api/ai-models/strategy/templates?category=trend_following" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Python**

```python
import requests

def get_templates(category=None, tag=None):
    params = {}
    if category:
        params['category'] = category
    if tag:
        params['tag'] = tag

    response = requests.get(
        'http://localhost:8000/api/ai-models/strategy/templates',
        headers={'Authorization': 'Bearer <token>'},
        params=params
    )

    result = response.json()
    if result['code'] == 0:
        print(f"获取到 {result['data']['total']} 个模板")
        for tpl in result['data']['list']:
            print(f"- {tpl['name']}: {tpl['description']}")

    return result['data']['list']
```

---

### 10. 获取模板详情

获取单个策略模板的详细信息。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/templates/{template_id}` |
| 认证 | 需要 JWT Token |

#### 请求参数

**路径参数 (Path Parameters)**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `template_id` | string | ✅ | 模板ID |

#### 响应格式

```json
{
    "code": 0,
    "message": "获取成功",
    "data": {
        "id": "tpl_001",
        "name": "双均线策略模板",
        "description": "基于双均线的趋势跟踪策略模板",
        "category": "trend_following",
        "code_template": "class {{strategy_name}}(BaseStrategy):\n    def __init__(self, config):\n        super().__init__(config)\n...",
        "variables": [
            {"name": "strategy_name", "type": "string", "required": true},
            {"name": "fast_period", "type": "int", "default": 10}
        ],
        "tags": ["趋势", "均线"],
        "created_at": "2026-03-01T10:00:00",
        "updated_at": null
    }
}
```

#### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 获取成功 |
| 404 | 模板不存在 |

---

### 11. 基于模板生成

使用预定义的模板和变量值生成策略代码。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `POST` |
| 路径 | `/generate-from-template` |
| 认证 | 需要 JWT Token |
| Content-Type | `application/json` |

#### 请求参数

**请求体 (Request Body)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `template_id` | string | ✅ | 模板ID | `"tpl_001"` |
| `variables` | object | ✅ | 模板变量值 | `{"strategy_name": "MyStrategy"}` |
| `model_id` | string | ❌ | 模型ID | `"gpt-4"` |
| `temperature` | float | ❌ | 温度参数 | `0.7` |
| `additional_requirement` | string | ❌ | 额外需求描述 | `"添加止损逻辑"` |

#### 响应格式

```json
{
    "code": 0,
    "message": "基于模板生成成功",
    "data": {
        "code": "class MyStrategy(BaseStrategy):\n    def __init__(self, config):\n        super().__init__(config)\n...",
        "explanation": "基于模板 双均线策略模板 生成",
        "model_used": "template",
        "tokens_used": null,
        "elapsed_time": null,
        "request_id": "hist_1234567890"
    }
}
```

#### 请求示例

**cURL**

```bash
curl -X POST "http://localhost:8000/api/ai-models/strategy/generate-from-template" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
    -H "Content-Type: application/json" \
    -d '{
        "template_id": "tpl_001",
        "variables": {
            "strategy_name": "MyDualMAStrategy",
            "fast_period": 10,
            "slow_period": 20
        },
        "additional_requirement": "添加止损逻辑"
    }'
```

**Python**

```python
import requests

def generate_from_template(template_id, variables, additional_requirement=None):
    data = {
        'template_id': template_id,
        'variables': variables
    }
    if additional_requirement:
        data['additional_requirement'] = additional_requirement

    response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/generate-from-template',
        headers={'Authorization': 'Bearer <token>'},
        json=data
    )

    result = response.json()
    if result['code'] == 0:
        print(f"✅ 基于模板生成成功")
        print(f"代码:\n{result['data']['code']}")
    else:
        print(f"❌ 生成失败: {result['message']}")

    return result['data']

# 使用示例
generate_from_template(
    template_id='tpl_001',
    variables={
        'strategy_name': 'MyDualMAStrategy',
        'fast_period': 10,
        'slow_period': 20
    },
    additional_requirement='添加止损逻辑'
)
```

---

### 12. 获取性能统计

获取策略生成的性能统计数据。

#### 请求信息

| 项目 | 说明 |
|------|------|
| 方法 | `GET` |
| 路径 | `/stats` |
| 认证 | 需要 JWT Token |

#### 请求参数

**查询参数 (Query Parameters)**

| 字段 | 类型 | 必需 | 说明 | 示例 |
|------|------|------|------|------|
| `days` | integer | ❌ | 统计天数，默认30，最大365 | `30` |

#### 响应格式

```json
{
    "code": 0,
    "message": "获取成功",
    "data": {
        "total_generations": 100,
        "successful_generations": 95,
        "failed_generations": 5,
        "success_rate": 95.0,
        "average_generation_time": 3.5,
        "total_tokens_used": 50000,
        "model_usage_stats": {
            "gpt-4": 80,
            "claude-3": 20
        },
        "daily_stats": [
            {
                "date": "2026-03-07",
                "count": 10,
                "success": 9
            },
            {
                "date": "2026-03-08",
                "count": 15,
                "success": 15
            }
        ],
        "period_start": "2026-02-06T00:00:00",
        "period_end": "2026-03-08T00:00:00"
    }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.total_generations` | integer | 总生成次数 |
| `data.successful_generations` | integer | 成功生成次数 |
| `data.failed_generations` | integer | 失败生成次数 |
| `data.success_rate` | float | 成功率(%) |
| `data.average_generation_time` | float | 平均生成时间(秒) |
| `data.total_tokens_used` | integer | 总Token使用量 |
| `data.model_usage_stats` | object | 各模型使用统计 |
| `data.daily_stats` | array | 每日统计 |

#### 请求示例

**cURL**

```bash
curl -X GET "http://localhost:8000/api/ai-models/strategy/stats?days=30" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

**Python**

```python
import requests

def get_performance_stats(days=30):
    response = requests.get(
        'http://localhost:8000/api/ai-models/strategy/stats',
        headers={'Authorization': 'Bearer <token>'},
        params={'days': days}
    )

    result = response.json()
    if result['code'] == 0:
        data = result['data']
        print(f"📊 性能统计 (最近{days}天)")
        print(f"总生成次数: {data['total_generations']}")
        print(f"成功率: {data['success_rate']}%")
        print(f"平均生成时间: {data['average_generation_time']:.2f}秒")
        print(f"总Token使用量: {data['total_tokens_used']}")
        print(f"模型使用统计: {data['model_usage_stats']}")

    return result['data']
```

---

## 数据模型

### StrategyGenerateRequest

策略生成请求模型

```json
{
    "requirement": "创建一个双均线策略，当短期均线上穿长期均线时买入，下穿时卖出",
    "model_id": "gpt-4",
    "temperature": 0.7,
    "template_vars": {
        "strategy_name": "DualMAStrategy",
        "symbol": "BTC/USDT",
        "timeframe": "1h"
    }
}
```

| 字段 | 类型 | 必需 | 约束 | 说明 |
|------|------|------|------|------|
| `requirement` | string | ✅ | 10-5000 字符 | 策略需求描述 |
| `model_id` | string | ❌ | - | 模型 ID，如 "gpt-4" |
| `temperature` | float | ❌ | 0-2 | 温度参数 |
| `template_vars` | object | ❌ | - | 模板变量 |

### StrategyGenerateResponse

策略生成响应模型

```json
{
    "code": "class DualMAStrategy(BaseStrategy):\n    def __init__(self, config):\n        super().__init__(config)",
    "explanation": "这是一个基于双均线的趋势跟踪策略...",
    "model_used": "gpt-4",
    "tokens_used": {
        "prompt_tokens": 500,
        "completion_tokens": 800,
        "total_tokens": 1300
    },
    "elapsed_time": 3.5,
    "request_id": "req_abc123"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 生成的策略代码 |
| `explanation` | string | 策略说明文档 |
| `model_used` | string | 实际使用的模型 ID |
| `tokens_used` | object | Token 使用情况 |
| `elapsed_time` | float | 生成耗时(秒) |
| `request_id` | string | 请求 ID |

### StrategyValidateRequest

代码验证请求模型

```json
{
    "code": "class MyStrategy:\n    def __init__(self):\n        pass"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 需要验证的策略代码 |

### StrategyValidateResponse

代码验证响应模型

```json
{
    "valid": true,
    "errors": [],
    "warnings": ["警告: 代码中未找到类定义"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid` | boolean | 代码是否有效 |
| `errors` | array | 错误列表 |
| `warnings` | array | 警告列表 |

### CodeValidationRequest

通用代码验证请求模型

```json
{
    "code": "class MyStrategy:\n    pass",
    "language": "python"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 需要验证的代码 |
| `language` | string | ❌ | 代码语言，默认 "python" |

### CodeValidationResponse

通用代码验证响应模型

```json
{
    "valid": true,
    "errors": [],
    "warnings": ["警告: 未检测到策略基类继承"],
    "suggestions": ["建议使用类型注解"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid` | boolean | 代码是否有效 |
| `errors` | array | 错误列表 |
| `warnings` | array | 警告列表 |
| `suggestions` | array | 改进建议 |

### StrategyHistoryResponse

策略历史记录响应模型

```json
{
    "id": "hist_1234567890",
    "user_id": "user_123",
    "requirement": "创建一个双均线策略",
    "code": "class DualMAStrategy:\n    pass",
    "model_id": "gpt-4",
    "explanation": "这是一个双均线策略...",
    "status": "success",
    "tokens_used": {
        "prompt_tokens": 500,
        "completion_tokens": 800,
        "total_tokens": 1300
    },
    "elapsed_time": 3.5,
    "created_at": "2026-03-08T10:30:00",
    "updated_at": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 历史记录ID |
| `user_id` | string | 用户ID |
| `requirement` | string | 策略需求描述 |
| `code` | string | 生成的策略代码 |
| `model_id` | string | 使用的模型ID |
| `explanation` | string | 策略说明文档 |
| `status` | string | 生成状态: success/failed/pending |
| `tokens_used` | object | Token使用情况 |
| `elapsed_time` | float | 生成耗时(秒) |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

### StrategyTemplateResponse

策略模板响应模型

```json
{
    "id": "tpl_1234567890",
    "name": "双均线策略模板",
    "description": "基于双均线的趋势跟踪策略模板",
    "category": "trend_following",
    "code_template": "class {{strategy_name}}(BaseStrategy):\n    pass",
    "variables": [
        {"name": "strategy_name", "type": "string", "required": true},
        {"name": "fast_period", "type": "int", "default": 10}
    ],
    "tags": ["趋势", "均线"],
    "created_at": "2026-03-01T10:00:00",
    "updated_at": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 模板ID |
| `name` | string | 模板名称 |
| `description` | string | 模板描述 |
| `category` | string | 模板分类 |
| `code_template` | string | 代码模板 |
| `variables` | array | 模板变量定义 |
| `tags` | array | 标签列表 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

### StrategyGenerateFromTemplateRequest

基于模板生成策略请求模型

```json
{
    "template_id": "tpl_1234567890",
    "variables": {
        "strategy_name": "DualMAStrategy",
        "fast_period": 10,
        "slow_period": 20
    },
    "model_id": "gpt-4",
    "temperature": 0.7,
    "additional_requirement": "添加止损逻辑"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `template_id` | string | ✅ | 模板ID |
| `variables` | object | ✅ | 模板变量值 |
| `model_id` | string | ❌ | 模型ID |
| `temperature` | float | ❌ | 温度参数 |
| `additional_requirement` | string | ❌ | 额外需求描述 |

### PerformanceStatsResponse

性能统计响应模型

```json
{
    "total_generations": 100,
    "successful_generations": 95,
    "failed_generations": 5,
    "success_rate": 95.0,
    "average_generation_time": 3.5,
    "total_tokens_used": 50000,
    "model_usage_stats": {
        "gpt-4": 80,
        "claude-3": 20
    },
    "daily_stats": [
        {"date": "2026-03-07", "count": 10, "success": 9}
    ],
    "period_start": "2026-02-06T00:00:00",
    "period_end": "2026-03-08T00:00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_generations` | integer | 总生成次数 |
| `successful_generations` | integer | 成功生成次数 |
| `failed_generations` | integer | 失败生成次数 |
| `success_rate` | float | 成功率(%) |
| `average_generation_time` | float | 平均生成时间(秒) |
| `total_tokens_used` | integer | 总Token使用量 |
| `model_usage_stats` | object | 各模型使用统计 |
| `daily_stats` | array | 每日统计 |
| `period_start` | datetime | 统计周期开始时间 |
| `period_end` | datetime | 统计周期结束时间 |

---

## 错误处理

### HTTP 状态码

| 状态码 | 说明 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | 正常处理响应 |
| 400 | 请求错误 | 检查请求参数格式和内容 |
| 401 | 未授权 | 检查 JWT Token 是否有效或已过期 |
| 403 | 禁止访问 | 检查用户权限 |
| 404 | 未找到 | 检查 API 路径是否正确 |
| 500 | 服务器错误 | 联系管理员或稍后重试 |

### 业务错误码

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| `api_authentication_error` | API 认证失败 | 检查 AI 模型配置的 API 密钥 |
| `api_rate_limit_error` | 请求过于频繁 | 降低请求频率或稍后重试 |
| `api_connection_error` | 连接失败 | 检查网络连接和 API 主机配置 |
| `response_parse_error` | 响应解析失败 | 可能是模型返回格式异常，重试或联系管理员 |
| `strategy_generation_error` | 策略生成失败 | 检查需求描述是否清晰，或重试 |

### 错误响应示例

**400 - 未配置 AI 模型**

```json
{
    "detail": {
        "message": "未配置默认AI模型",
        "error": "请先配置AI模型并设置默认提供商"
    }
}
```

**400 - 缺少 API 密钥**

```json
{
    "detail": {
        "message": "默认AI模型未配置API密钥",
        "error": "请配置API密钥"
    }
}
```

**401 - Token 无效**

```json
{
    "detail": "未授权访问"
}
```

**业务错误**

```json
{
    "code": 1,
    "message": "API认证失败: API密钥无效或已过期",
    "data": {
        "error_code": "api_authentication_error"
    }
}
```

---

## 使用场景示例

### 场景 1：Web 界面实时生成策略

使用流式生成 API，在用户输入需求后实时展示代码生成过程。

```javascript
class StrategyGenerator {
    constructor(token) {
        this.token = token;
        this.eventSource = null;
    }

    generate(requirement, onContent, onDone, onError) {
        // 使用 fetch 发送 POST 请求获取 SSE 流
        fetch('/api/ai-models/strategy/generate', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                requirement: requirement,
                temperature: 0.7
            })
        }).then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const readStream = () => {
                reader.read().then(({ done, value }) => {
                    if (done) return;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n\n');

                    lines.forEach(line => {
                        if (line.startsWith('data: ')) {
                            const data = JSON.parse(line.slice(6));

                            switch (data.type) {
                                case 'content':
                                    onContent(data.content);
                                    break;
                                case 'done':
                                    onDone(data);
                                    break;
                                case 'error':
                                    onError(data.error);
                                    break;
                            }
                        }
                    });

                    readStream();
                });
            };

            readStream();
        });
    }
}

// 使用
const generator = new StrategyGenerator(token);
let generatedCode = '';

generator.generate(
    '创建一个双均线策略',
    (content) => {
        generatedCode += content;
        document.getElementById('code-preview').textContent = generatedCode;
    },
    (data) => {
        console.log('生成完成:', data.code);
        // 启用保存按钮
        document.getElementById('save-btn').disabled = false;
    },
    (error) => {
        console.error('生成错误:', error);
        alert('生成失败: ' + error);
    }
);
```

### 场景 2：批量生成策略

使用同步生成 API 批量处理多个策略需求。

```python
import requests
import time

def batch_generate_strategies(requirements, token):
    """批量生成策略"""
    results = []

    for i, requirement in enumerate(requirements):
        print(f"正在生成策略 {i+1}/{len(requirements)}...")

        response = requests.post(
            'http://localhost:8000/api/ai-models/strategy/generate-sync',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'requirement': requirement,
                'temperature': 0.7
            },
            timeout=60
        )

        result = response.json()
        results.append(result)

        if result['code'] == 0:
            print(f"✅ 策略 {i+1} 生成成功")
            # 保存到文件
            with open(f'strategy_{i+1}.py', 'w') as f:
                f.write(result['data']['code'])
        else:
            print(f"❌ 策略 {i+1} 生成失败: {result['message']}")

        # 避免请求过于频繁
        time.sleep(1)

    return results

# 使用
requirements = [
    "创建一个双均线策略，短期MA上穿长期MA时买入",
    "创建一个RSI策略，RSI低于30时买入，高于70时卖出",
    "创建一个布林带策略，价格触及下轨时买入，触及上轨时卖出"
]

results = batch_generate_strategies(requirements, token)
```

### 场景 3：生成并验证策略

先生成策略，然后验证代码的正确性。

```python
import requests

def generate_and_validate(requirement, token):
    """生成并验证策略"""

    # 1. 生成策略
    print("正在生成策略...")
    gen_response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/generate-sync',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'requirement': requirement,
            'temperature': 0.7
        },
        timeout=60
    )

    gen_result = gen_response.json()

    if gen_result['code'] != 0:
        print(f"生成失败: {gen_result['message']}")
        return None

    code = gen_result['data']['code']
    print("✅ 策略生成成功")
    print(f"使用模型: {gen_result['data']['model_used']}")
    print(f"Token使用: {gen_result['data']['tokens_used']}")

    # 2. 验证策略
    print("\n正在验证代码...")
    val_response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/validate',
        headers={'Authorization': f'Bearer {token}'},
        json={'code': code}
    )

    val_result = val_response.json()
    data = val_result['data']

    if data['valid']:
        print("✅ 代码验证通过")
        if data['warnings']:
            print("⚠️ 警告:")
            for warning in data['warnings']:
                print(f"  - {warning}")
    else:
        print("❌ 验证失败")
        print("错误:")
        for error in data['errors']:
            print(f"  - {error}")

    return {
        'code': code,
        'explanation': gen_result['data']['explanation'],
        'valid': data['valid'],
        'errors': data['errors'],
        'warnings': data['warnings']
    }

# 使用
result = generate_and_validate(
    '创建一个双均线策略，当短期均线上穿长期均线时买入',
    token
)

if result and result['valid']:
    print("\n生成的代码:")
    print(result['code'])
```

### 场景 4：策略优化迭代

基于已有策略进行优化改进。

```python
import requests

def optimize_strategy(existing_code, optimization_requirement, token):
    """优化现有策略"""

    # 构建优化提示
    full_requirement = f"""
现有策略代码:
```python
{existing_code}
```

优化需求:
{optimization_requirement}

请基于现有策略进行优化，保持核心逻辑的同时实现上述需求。
"""

    # 生成优化后的策略
    response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/generate-sync',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'requirement': full_requirement,
            'temperature': 0.5,  # 使用较低温度保持稳定性
            'template_vars': {
                'optimization_mode': True
            }
        },
        timeout=60
    )

    result = response.json()

    if result['code'] == 0:
        print("✅ 策略优化成功")
        print("\n优化说明:")
        print(result['data']['explanation'])

        # 验证新代码
        val_response = requests.post(
            'http://localhost:8000/api/ai-models/strategy/validate',
            headers={'Authorization': f'Bearer {token}'},
            json={'code': result['data']['code']}
        )

        val_data = val_response.json()['data']
        if val_data['valid']:
            print("✅ 优化后的代码验证通过")
        else:
            print("⚠️ 优化后的代码存在语法问题")

        return result['data']
    else:
        print(f"❌ 优化失败: {result['message']}")
        return None

# 使用示例
existing_code = '''
from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class DualMAStrategy(BaseStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast = int(config.params.get("fast", 10))
        self.slow = int(config.params.get("slow", 20))

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        # 简单实现
        return Action("hold", 0.0, 0.0, self.config.name, 0)
'''

optimization_requirement = """
1. 添加止损逻辑，亏损超过5%时平仓
2. 添加仓位管理，根据波动率调整仓位大小
3. 优化信号过滤，避免震荡市频繁交易
"""

result = optimize_strategy(existing_code, optimization_requirement, token)
```

### 场景 5：使用模板库快速生成

使用预定义模板快速生成策略。

```python
import requests

def quick_generate_from_template(token):
    """使用模板快速生成策略"""

    # 1. 获取模板列表
    print("获取模板列表...")
    tpl_response = requests.get(
        'http://localhost:8000/api/ai-models/strategy/templates',
        headers={'Authorization': f'Bearer {token}'}
    )

    templates = tpl_response.json()['data']['list']
    print(f"找到 {len(templates)} 个模板")

    # 2. 选择模板并生成
    template = templates[0]  # 选择第一个模板
    print(f"\n使用模板: {template['name']}")

    # 准备变量
    variables = {}
    for var in template['variables']:
        if var['name'] == 'strategy_name':
            variables[var['name']] = 'MyStrategy'
        elif 'default' in var:
            variables[var['name']] = var['default']
        else:
            variables[var['name']] = input(f"请输入 {var['name']}: ")

    # 3. 基于模板生成
    gen_response = requests.post(
        'http://localhost:8000/api/ai-models/strategy/generate-from-template',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'template_id': template['id'],
            'variables': variables,
            'additional_requirement': '添加风险控制逻辑'
        }
    )

    result = gen_response.json()
    if result['code'] == 0:
        print("✅ 基于模板生成成功")
        print(f"代码:\n{result['data']['code']}")
    else:
        print(f"❌ 生成失败: {result['message']}")

    return result['data']
```

### 场景 6：管理策略历史记录

查询、删除和管理策略历史记录。

```python
import requests

def manage_strategy_history(token):
    """管理策略历史记录"""

    # 1. 获取历史列表
    print("获取历史记录...")
    history_response = requests.get(
        'http://localhost:8000/api/ai-models/strategy/history?page=1&page_size=10',
        headers={'Authorization': f'Bearer {token}'}
    )

    history_data = history_response.json()['data']
    print(f"共有 {history_data['pagination']['total']} 条历史记录")

    for item in history_data['list'][:5]:
        print(f"- {item['id']}: {item['requirement'][:30]}... ({item['status']})")

    if not history_data['list']:
        return

    # 2. 获取单条详情
    history_id = history_data['list'][0]['id']
    print(f"\n获取详情: {history_id}")

    detail_response = requests.get(
        f'http://localhost:8000/api/ai-models/strategy/history/{history_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    detail = detail_response.json()['data']
    print(f"需求: {detail['requirement']}")
    print(f"模型: {detail['model_id']}")
    print(f"Token使用: {detail['tokens_used']}")

    # 3. 基于历史重新生成
    print(f"\n基于历史重新生成...")
    regen_response = requests.post(
        f'http://localhost:8000/api/ai-models/strategy/history/{history_id}/regenerate',
        headers={'Authorization': f'Bearer {token}'}
    )

    regen_result = regen_response.json()
    if regen_result['code'] == 0:
        print("✅ 重新生成成功")
    else:
        print(f"❌ 重新生成失败: {regen_result['message']}")
```

---

## 附录

### 支持的模型

| 模型 ID | 提供商 | 说明 |
|---------|--------|------|
| `gpt-4` | OpenAI | 推荐，生成质量高 |
| `gpt-4-turbo` | OpenAI | 更快的响应速度 |
| `gpt-3.5-turbo` | OpenAI | 成本较低 |
| `claude-3-opus` | Anthropic | 长文本处理能力强 |
| `claude-3-sonnet` | Anthropic | 平衡性能与成本 |

### 温度参数建议

| 场景 | 推荐温度 | 说明 |
|------|----------|------|
| 标准策略生成 | 0.7 | 平衡创造性和稳定性 |
| 保守/稳定生成 | 0.3-0.5 | 减少随机性，输出更确定 |
| 探索性生成 | 0.8-1.0 | 增加多样性，尝试不同方案 |
| 代码优化 | 0.3-0.5 | 保持代码结构稳定 |

### 模板变量

可用的模板变量取决于提示词模板，常用变量包括：

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| `strategy_name` | 策略类名 | `"DualMAStrategy"` |
| `symbol` | 交易品种 | `"BTC/USDT"` |
| `timeframe` | 时间周期 | `"1h"`, `"1d"` |
| `description` | 策略描述 | `"双均线策略"` |

### 模板分类

| 分类 | 说明 |
|------|------|
| `trend_following` | 趋势跟踪策略 |
| `oscillator` | 震荡指标策略 |
| `breakout` | 突破策略 |
| `mean_reversion` | 均值回归策略 |
| `arbitrage` | 套利策略 |

---

*文档版本: 1.1.0*  
*最后更新: 2026-03-08*  
*作者: QuantCell Team*
