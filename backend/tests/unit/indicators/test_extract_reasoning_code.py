"""_extract_indicator_code_from_reasoning 兜底提取的单测

背景：GLM-5.3-Flash 等推理模型偶发把完整指标代码写在 reasoning_content、
正文为空（content=""),调用方需从思考文本中挽回代码,避免白跑一次长生成。
"""

from indicators.routes import _extract_indicator_code_from_reasoning

# 典型失败场景: 正文空,思考里有一版完整指标代码（pandas 脚本式）
REASONING_WITH_CODE = """用户想要RSI双线指标。我先写个草稿:
```python
df = df.copy()
delta = df['close'].diff()
gain = delta.clip(lower=0)
rsi = 100 - 100 / (1 + gain.rolling(14).mean() / loss.rolling(14).mean())
```
再检查一遍参数边界，看起来没问题。"""

# 多版草稿时应取最后一个代码块
REASONING_MULTI_DRAFT = """第一版:
```python
df = df.copy()
v1 = df['close'].mean()
```
改进一下，用周期参数:
```python
df = df.copy()
v2 = df['close'].rolling(20).mean()
```"""


def test_从思考文本提取指标代码():
    code = _extract_indicator_code_from_reasoning(REASONING_WITH_CODE)
    assert "df['close'].diff()" in code
    assert "看起来没问题" not in code  # 思考文本不混入


def test_多版草稿取最后一个():
    code = _extract_indicator_code_from_reasoning(REASONING_MULTI_DRAFT)
    assert "v2" in code
    assert "v1" not in code


def test_纯思考文本不误提取():
    reasoning = "先分析RSI的数学含义,再看超买超卖阈值,最后决定平滑方式。没有代码。"
    assert _extract_indicator_code_from_reasoning(reasoning) == ""


def test_空输入():
    assert _extract_indicator_code_from_reasoning("") == ""
    assert _extract_indicator_code_from_reasoning(None) == ""  # type: ignore[arg-type]
