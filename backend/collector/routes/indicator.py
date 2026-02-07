"""
技术指标管理API

提供技术指标的CRUD操作、代码验证和AI生成功能
"""

import json
import os
import re
import time
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx

from ..db.database import get_db
from ..db.models import get_or_create_user

router = APIRouter(prefix="/indicators", tags=["indicators"])


# ========== 数据模型 ==========

class IndicatorBase(BaseModel):
    name: str = Field(..., description="指标名称")
    description: Optional[str] = Field(None, description="指标描述")
    code: str = Field(..., description="Python代码")


class IndicatorCreate(IndicatorBase):
    pass


class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None


class IndicatorResponse(IndicatorBase):
    id: int
    user_id: int
    is_buy: int = 0
    end_time: int = 1
    publish_to_community: int = 0
    pricing_type: str = "free"
    price: int = 0
    is_encrypted: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class IndicatorVerifyRequest(BaseModel):
    code: str = Field(..., description="要验证的Python代码")


class IndicatorVerifyResponse(BaseModel):
    valid: bool
    plots_count: int = 0
    signals_count: int = 0
    message: Optional[str] = None
    details: Optional[str] = None


class AIGenerateRequest(BaseModel):
    prompt: str = Field(..., description="AI生成提示词")
    existing_code: Optional[str] = Field(None, description="现有代码作为上下文")


# ========== 辅助函数 ==========

def _now_ts() -> int:
    return int(time.time())


def _extract_indicator_meta_from_code(code: str) -> Dict[str, str]:
    """从代码中提取指标名称和描述"""
    if not code or not isinstance(code, str):
        return {"name": "", "description": ""}

    name_match = re.search(r'^\s*my_indicator_name\s*=\s*([\'"])(.*?)\1\s*$', code, re.MULTILINE)
    desc_match = re.search(r'^\s*my_indicator_description\s*=\s*([\'"])(.*?)\1\s*$', code, re.MULTILINE)

    name = (name_match.group(2).strip() if name_match else "")[:100]
    description = (desc_match.group(2).strip() if desc_match else "")[:500]
    return {"name": name, "description": description}


def _generate_mock_df(length: int = 200) -> Dict:
    """生成模拟K线数据用于验证"""
    import numpy as np
    
    dates = [datetime.now().timestamp() * 1000 - i * 60000 for i in range(length)]
    dates.reverse()
    
    returns = np.random.normal(0, 0.002, length)
    price_path = 10000 * np.exp(np.cumsum(returns))
    
    close = price_path
    high = close * (1 + np.abs(np.random.normal(0, 0.001, length)))
    low = close * (1 - np.abs(np.random.normal(0, 0.001, length)))
    open_p = close * (1 + np.random.normal(0, 0.001, length))
    high = np.maximum(high, np.maximum(open_p, close))
    low = np.minimum(low, np.minimum(open_p, close))
    volume = np.abs(np.random.normal(100, 50, length)) * 1000
    
    return {
        'time': dates,
        'open': open_p.tolist(),
        'high': high.tolist(),
        'low': low.tolist(),
        'close': close.tolist(),
        'volume': volume.tolist()
    }


def _row_to_indicator(row: tuple, user_id: int) -> Dict[str, Any]:
    """将数据库行转换为指标对象"""
    return {
        "id": row[0],
        "user_id": row[1] if row[1] is not None else user_id,
        "is_buy": row[2] if row[2] is not None else 0,
        "end_time": row[3] if row[3] is not None else 1,
        "name": row[4] or "",
        "code": row[5] or "",
        "description": row[6] or "",
        "publish_to_community": row[7] if row[7] is not None else 0,
        "pricing_type": row[8] or "free",
        "price": row[9] if row[9] is not None else 0,
        "is_encrypted": 0,
        "created_at": row[11],
        "updated_at": row[12]
    }


# ========== API端点 ==========

@router.get("", response_model=List[IndicatorResponse])
async def get_indicators(request: Request, db=Depends(get_db)):
    """获取当前用户的指标列表"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT id, user_id, is_buy, end_time, name, code, description,
               publish_to_community, pricing_type, price, is_encrypted, preview_image,
               created_at, updated_at
        FROM qd_indicator_codes
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    
    return [_row_to_indicator(row, user_id) for row in rows]


@router.post("", response_model=IndicatorResponse)
async def create_indicator(
    indicator: IndicatorCreate,
    request: Request,
    db=Depends(get_db)
):
    """创建新指标"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    # 从代码中提取元数据
    meta = _extract_indicator_meta_from_code(indicator.code)
    name = indicator.name or meta["name"] or "未命名指标"
    description = indicator.description or meta["description"] or ""
    
    now = datetime.now().isoformat()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO qd_indicator_codes 
        (user_id, name, code, description, is_buy, end_time, 
         publish_to_community, pricing_type, price, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, 1, 0, 'free', 0, ?, ?)
        """,
        (user_id, name, indicator.code, description, now, now)
    )
    db.commit()
    new_id = cursor.lastrowid
    cursor.close()
    
    return {
        "id": new_id,
        "user_id": user_id,
        "is_buy": 0,
        "end_time": 1,
        "name": name,
        "code": indicator.code,
        "description": description,
        "publish_to_community": 0,
        "pricing_type": "free",
        "price": 0,
        "is_encrypted": 0,
        "created_at": now,
        "updated_at": now
    }


@router.put("/{indicator_id}", response_model=IndicatorResponse)
async def update_indicator(
    indicator_id: int,
    indicator: IndicatorUpdate,
    request: Request,
    db=Depends(get_db)
):
    """更新指标"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    # 检查指标是否存在且属于当前用户
    cursor = db.cursor()
    cursor.execute(
        "SELECT id FROM qd_indicator_codes WHERE id = ? AND user_id = ?",
        (indicator_id, user_id)
    )
    if not cursor.fetchone():
        cursor.close()
        raise HTTPException(status_code=404, detail="指标不存在或无权限")
    
    # 构建更新字段
    updates = []
    params = []
    
    if indicator.name is not None:
        updates.append("name = ?")
        params.append(indicator.name)
    if indicator.code is not None:
        updates.append("code = ?")
        params.append(indicator.code)
        # 重新提取元数据
        meta = _extract_indicator_meta_from_code(indicator.code)
        if not indicator.name and meta["name"]:
            updates.append("name = ?")
            params.append(meta["name"])
        if meta["description"]:
            updates.append("description = ?")
            params.append(meta["description"])
    if indicator.description is not None:
        updates.append("description = ?")
        params.append(indicator.description)
    
    if not updates:
        cursor.close()
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    
    now = datetime.now().isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(indicator_id)
    params.append(user_id)
    
    cursor.execute(
        f"UPDATE qd_indicator_codes SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        params
    )
    db.commit()
    cursor.close()
    
    # 返回更新后的指标
    return await get_indicator(indicator_id, request, db)


@router.get("/{indicator_id}", response_model=IndicatorResponse)
async def get_indicator(
    indicator_id: int,
    request: Request,
    db=Depends(get_db)
):
    """获取单个指标详情"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT id, user_id, is_buy, end_time, name, code, description,
               publish_to_community, pricing_type, price, is_encrypted, preview_image,
               created_at, updated_at
        FROM qd_indicator_codes
        WHERE id = ? AND user_id = ?
        """,
        (indicator_id, user_id)
    )
    row = cursor.fetchone()
    cursor.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="指标不存在或无权限")
    
    return _row_to_indicator(row, user_id)


@router.delete("/{indicator_id}")
async def delete_indicator(
    indicator_id: int,
    request: Request,
    db=Depends(get_db)
):
    """删除指标"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM qd_indicator_codes WHERE id = ? AND user_id = ?",
        (indicator_id, user_id)
    )
    db.commit()
    
    if cursor.rowcount == 0:
        cursor.close()
        raise HTTPException(status_code=404, detail="指标不存在或无权限")
    
    cursor.close()
    return {"code": 1, "msg": "删除成功"}


@router.post("/verify", response_model=IndicatorVerifyResponse)
async def verify_code(request: IndicatorVerifyRequest):
    """验证指标代码"""
    code = request.code
    
    if not code or not code.strip():
        return IndicatorVerifyResponse(valid=False, message="代码不能为空")
    
    try:
        # 尝试在安全环境中执行代码验证
        # 这里使用简化的验证逻辑
        
        # 检查必要的输出格式
        if "output" not in code and "return" not in code:
            return IndicatorVerifyResponse(
                valid=False,
                message="代码必须包含output变量或return语句"
            )
        
        # 检查是否使用了pandas/numpy
        if "import pandas" not in code and "import pd" not in code:
            return IndicatorVerifyResponse(
                valid=False,
                message="建议导入pandas库: import pandas as pd"
            )
        
        # 统计plots和signals
        plots_count = code.count('"plots"') + code.count("'plots'")
        signals_count = code.count('"signals"') + code.count("'signals'")
        
        return IndicatorVerifyResponse(
            valid=True,
            plots_count=plots_count,
            signals_count=signals_count,
            message="代码验证通过"
        )
        
    except Exception as e:
        return IndicatorVerifyResponse(
            valid=False,
            message=f"代码验证失败: {str(e)}",
            details=traceback.format_exc()
        )


@router.post("/ai-generate")
async def ai_generate(request: AIGenerateRequest):
    """AI生成指标代码（SSE流式响应）"""
    prompt = request.prompt
    existing_code = request.existing_code
    
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")
    
    async def generate_stream():
        """生成SSE流"""
        # 构建系统提示词
        system_prompt = """你是一个专业的量化交易指标开发助手。
请根据用户描述生成Python代码，用于计算技术指标。

代码要求：
1. 必须导入pandas: import pandas as pd
2. 必须导入numpy: import numpy as np
3. 输入数据df包含列: time, open, high, low, close, volume
4. 输出必须是字典格式，包含:
   - name: 指标名称
   - plots: 绘制的线条数据列表
   - signals: 买卖信号列表

示例输出格式：
```python
import pandas as pd
import numpy as np

my_indicator_name = "示例指标"
my_indicator_description = "这是一个示例指标"

sma = df["close"].rolling(20).mean()
buy = (df["close"] > sma) & (df["close"].shift(1) <= sma.shift(1))
sell = (df["close"] < sma) & (df["close"].shift(1) >= sma.shift(1))

output = {
    "name": my_indicator_name,
    "plots": [
        {"name": "SMA20", "data": sma.tolist(), "color": "#1890ff"}
    ],
    "signals": [
        {"type": "buy", "text": "B", "data": buy.tolist(), "color": "#00E676"},
        {"type": "sell", "text": "S", "data": sell.tolist(), "color": "#FF5252"}
    ]
}
```

请只返回Python代码，不要包含解释说明。"""

        # 构建完整提示词
        full_prompt = f"{system_prompt}\n\n用户请求: {prompt}"
        if existing_code:
            full_prompt += f"\n\n现有代码（作为参考）:\n{existing_code}"
        
        # 模拟AI生成过程
        # 实际实现中应该调用OpenAI API或其他LLM服务
        yield f"data: {json.dumps({'content': '# 正在生成指标代码...'})}\n\n"
        
        # 这里简化处理，返回一个模板代码
        template_code = f'''import pandas as pd
import numpy as np

my_indicator_name = "AI生成指标"
my_indicator_description = "{prompt[:50]}"

# 计算指标
sma_short = df["close"].rolling(5).mean()
sma_long = df["close"].rolling(20).mean()

# 生成信号
buy = (sma_short > sma_long) & (sma_short.shift(1) <= sma_long.shift(1))
sell = (sma_short < sma_long) & (sma_short.shift(1) >= sma_long.shift(1))

output = {{
    "name": my_indicator_name,
    "plots": [
        {{"name": "SMA5", "data": sma_short.tolist(), "color": "#1890ff", "overlay": True}},
        {{"name": "SMA20", "data": sma_long.tolist(), "color": "#ff7a45", "overlay": True}}
    ],
    "signals": [
        {{"type": "buy", "text": "B", "data": buy.tolist(), "color": "#00E676"}},
        {{"type": "sell", "text": "S", "data": sell.tolist(), "color": "#FF5252"}}
    ]
}}'''
        
        # 模拟流式输出
        lines = template_code.split('\n')
        for line in lines:
            yield f"data: {json.dumps({'content': line + '\\n'})}\n\n"
        
        yield f"data: {json.dumps({'done': True})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/{indicator_id}/params")
async def get_indicator_params(
    indicator_id: int,
    request: Request,
    db=Depends(get_db)
):
    """获取指标参数列表"""
    user = get_or_create_user(db, request)
    user_id = user["id"]
    
    cursor = db.cursor()
    cursor.execute(
        "SELECT code FROM qd_indicator_codes WHERE id = ? AND user_id = ?",
        (indicator_id, user_id)
    )
    row = cursor.fetchone()
    cursor.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="指标不存在或无权限")
    
    code = row[0] or ""
    
    # 从代码中提取参数定义
    # 支持格式: # param: name, type, default, description
    params = []
    param_pattern = r'^\s*#\s*param:\s*(\w+)\s*,\s*(\w+)\s*,\s*([^,]+)\s*,\s*(.+)$'
    
    for match in re.finditer(param_pattern, code, re.MULTILINE):
        params.append({
            "name": match.group(1).strip(),
            "type": match.group(2).strip(),
            "default": match.group(3).strip(),
            "description": match.group(4).strip()
        })
    
    # 如果没有显式参数定义，尝试从代码中推断
    if not params:
        # 查找常见的参数模式如 length=14, period=20 等
        param_patterns = [
            (r'rolling\((\d+)\)', 'period', 'int'),
            (r'ewm\(span=(\d+)', 'span', 'int'),
            (r'length\s*=\s*(\d+)', 'length', 'int'),
            (r'period\s*=\s*(\d+)', 'period', 'int'),
        ]
        
        seen_params = set()
        for pattern, default_name, param_type in param_patterns:
            for match in re.finditer(pattern, code):
                default_val = match.group(1)
                param_name = f"{default_name}_{default_val}"
                if param_name not in seen_params:
                    seen_params.add(param_name)
                    params.append({
                        "name": default_name,
                        "type": param_type,
                        "default": default_val,
                        "description": f"{default_name.capitalize()} parameter"
                    })
    
    return {"code": 1, "data": params}
