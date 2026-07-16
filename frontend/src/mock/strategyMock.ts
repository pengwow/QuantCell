// AI 策略生成 Mock 数据

export interface MockStrategyResponse {
  code: number;
  message: string;
  data: {
    content: string;
    explanation: string;
    code: string;
    model_used: string;
  };
}

// 示例策略代码模板
const strategyTemplates: Record<string, string> = {
  双均线: `# -*- coding: utf-8 -*-
"""双均线交叉策略 — axon_quant 规则策略"""

from axon_quant import Action


class DualMA:
    """双均线交叉策略"""

    def __init__(self, fast: int = 10, slow: int = 20):
        self.fast = fast
        self.slow = slow
        self.closes: list[float] = []
        self._prev_fast_above_slow: bool | None = None

    def on_start(self) -> None:
        self.closes.clear()
        self._prev_fast_above_slow = None

    def on_bar(self, bar: dict) -> Action:
        self.closes.append(bar["close"])

        if len(self.closes) < self.slow:
            return Action("hold", 0.0, 0.0, "dual_ma", 0)

        fast_ma = sum(self.closes[-self.fast:]) / self.fast
        slow_ma = sum(self.closes[-self.slow:]) / self.slow

        fast_above_slow = fast_ma > slow_ma

        if self._prev_fast_above_slow is None:
            self._prev_fast_above_slow = fast_above_slow
            return Action("hold", 0.0, 0.0, "dual_ma", 0)

        if not self._prev_fast_above_slow and fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            return Action("buy", 0.8, 0.1, "dual_ma", 0)

        if self._prev_fast_above_slow and not fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            return Action("sell", 0.8, 0.0, "dual_ma", 0)

        self._prev_fast_above_slow = fast_above_slow
        return Action("hold", 0.0, 0.0, "dual_ma", 0)
`,

  MACD: `# -*- coding: utf-8 -*-
"""MACD 策略 — axon_quant 规则策略"""

from axon_quant import Action


class MACD:
    """MACD 金叉死叉策略"""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.closes: list[float] = []
        self._ema_fast = 0.0
        self._ema_slow = 0.0
        self._macd_values: list[float] = []
        self._prev_macd = 0.0
        self._prev_signal = 0.0
        self._position_side = "flat"

    def on_start(self) -> None:
        self.closes.clear()
        self._macd_values.clear()

    def on_bar(self, bar: dict) -> Action:
        self.closes.append(bar["close"])

        if len(self.closes) < self.slow:
            return Action("hold", 0.0, 0.0, "macd", 0)

        mult_f = 2 / (self.fast + 1)
        mult_s = 2 / (self.slow + 1)

        if self._ema_fast == 0:
            self._ema_fast = sum(self.closes[:self.fast]) / self.fast
            self._ema_slow = sum(self.closes[:self.slow]) / self.slow
        else:
            self._ema_fast = (bar["close"] - self._ema_fast) * mult_f + self._ema_fast
            self._ema_slow = (bar["close"] - self._ema_slow) * mult_s + self._ema_slow

        macd = self._ema_fast - self._ema_slow
        self._macd_values.append(macd)

        sig = sum(self._macd_values[-self.signal:]) / min(len(self._macd_values), self.signal)

        if self._prev_macd != 0 and self._prev_signal != 0:
            if self._prev_macd <= self._prev_signal and macd > sig and self._position_side == "flat":
                self._position_side = "long"
                self._prev_macd = macd
                self._prev_signal = sig
                return Action("buy", 0.8, 0.1, "macd", 0)
            if self._prev_macd >= self._prev_signal and macd < sig and self._position_side == "long":
                self._position_side = "flat"
                self._prev_macd = macd
                self._prev_signal = sig
                return Action("sell", 0.8, 0.0, "macd", 0)

        self._prev_macd = macd
        self._prev_signal = sig
        return Action("hold", 0.0, 0.0, "macd", 0)
`,

  默认: `# -*- coding: utf-8 -*-
"""AI 生成的策略 — axon_quant 规则策略"""

from axon_quant import Action


class AIStrategy:
    """AI 生成的策略"""

    def __init__(self):
        self.closes: list[float] = []

    def on_start(self) -> None:
        self.closes.clear()

    def on_bar(self, bar: dict) -> Action:
        self.closes.append(bar["close"])

        if len(self.closes) < 2:
            return Action("hold", 0.0, 0.0, "ai_strategy", 0)

        prev = self.closes[-2]
        curr = bar["close"]

        if curr > prev:
            return Action("buy", 0.6, 0.1, "ai_strategy", 0)
        elif curr < prev:
            return Action("sell", 0.6, 0.0, "ai_strategy", 0)

        return Action("hold", 0.0, 0.0, "ai_strategy", 0)
`,

  RL: `# -*- coding: utf-8 -*-
"""RL 策略 — 基于 axon_quant TradingEnv + Stable-Baselines3

训练: python scripts/rl_cli.py train --symbol BTCUSDT --algorithm ppo --timesteps 30000
回测: python scripts/rl_cli.py backtest --model data/rl_models/xxx.zip --symbol BTCUSDT
"""

from pathlib import Path
from axon_quant import Action

MODELS_DIR = Path(__file__).parent.parent / "data" / "rl_models"


class RLStrategy:
    """RL PPO 策略 — 自动加载最新模型"""

    def __init__(self, model_path: str = None):
        self.model = None
        self.model_path = model_path
        self._position = 0.0
        self._returns: list[float] = []
        self._last_close: float = 0.0

    def on_start(self) -> None:
        from stable_baselines3 import PPO

        path = self.model_path
        if not path:
            zips = sorted(MODELS_DIR.glob("*.zip"), key=lambda f: f.stat().st_mtime)
            if zips:
                path = str(zips[-1])

        if path and Path(path).exists():
            self.model = PPO.load(path)
            print(f"[RL] 加载模型: {path}")

    def on_bar(self, bar: dict) -> Action:
        if self.model is None:
            return Action("hold", 0.0, 0.0, "rl", 0)

        import numpy as np

        close = bar["close"]
        ret = 0.0
        if self._last_close > 0:
            ret = (close - self._last_close) / self._last_close
        self._last_close = close
        self._returns.append(ret)
        if len(self._returns) > 50:
            self._returns.pop(0)

        pos = 1.0 if self._position > 0 else (-1.0 if self._position < 0 else 0.0)
        vol = np.std(self._returns[-20:]) if len(self._returns) > 1 else 0.0
        sma = np.mean(self._returns[-10:]) if len(self._returns) >= 10 else 0.0
        rsi = 50.0
        if len(self._returns) > 14:
            g = np.array(self._returns[-14:])
            up = np.mean(g[g > 0]) if np.any(g > 0) else 0
            dn = -np.mean(g[g < 0]) if np.any(g < 0) else 0
            rsi = 100 - 100 / (1 + up / dn) if dn > 0 else (100 if up > 0 else 50)

        obs = np.array([pos, vol, sma, sma, sma, (rsi - 50) / 50, 0, 0, 0, 0, vol, ret], dtype=np.float32)
        a, _ = self.model.predict(obs, deterministic=True)
        a = int(a)

        if a == 1 and self._position <= 0:
            self._position = 0.1
            return Action("buy", 0.8, 0.1, "rl", 0)
        elif a == 2 and self._position >= 0:
            self._position = -0.1
            return Action("sell", 0.8, 0.1, "rl", 0)
        elif a == 3 and self._position > 0:
            self._position = 0.0
            return Action("sell", 0.9, 0.1, "rl", 0)
        elif a == 4 and self._position < 0:
            self._position = 0.0
            return Action("buy", 0.9, 0.1, "rl", 0)

        return Action("hold", 0.0, 0.0, "rl", 0)

    def on_stop(self) -> None:
        pass
`,
};

// 模拟策略生成 API
export const mockGenerateStrategy = async (
  prompt: string,
  _modelId?: number | null,
  modelName?: string
): Promise<MockStrategyResponse> => {
  await new Promise((resolve) => setTimeout(resolve, 2000));

  let templateKey = '默认';
  const promptLower = prompt.toLowerCase();
  
  if (promptLower.includes('rl策略') || promptLower.includes('rl') || promptLower.includes('强化学习') || promptLower.includes('tradingenv')) {
    templateKey = 'RL';
  } else if (promptLower.includes('均线') || promptLower.includes('ma') || promptLower.includes('moving')) {
    templateKey = '双均线';
  } else if (promptLower.includes('macd')) {
    templateKey = 'MACD';
  }

  const code = strategyTemplates[templateKey] || strategyTemplates['默认'];

  const response: MockStrategyResponse = {
    code: 0,
    message: '策略生成成功',
    data: {
      content: generateExplanation(prompt, templateKey),
      explanation: generateExplanation(prompt, templateKey),
      code: code,
      model_used: modelName || 'gpt-4',
    },
  };

  return response;
};

function generateExplanation(_prompt: string, templateKey: string): string {
  const explanations: Record<string, string> = {
    双均线: `根据您的需求，我已经为您生成了一个双均线交叉策略。

这个策略包含：
1. 完整的 on_bar 方法，接收 bar: dict 返回 Action
2. 移动平均线计算逻辑
3. 金叉买入(buy)、死叉卖出(sell)的交易信号
4. Action 参数: ("buy"/"sell"/"hold", confidence, target_position, model_id, inference_time_us)

您可以根据实际需要调整周期参数或修改交易逻辑。`,

    MACD: `根据您的需求，我已经为您生成了一个MACD策略。

这个策略包含：
1. EMA指数移动平均线计算
2. MACD线和信号线计算
3. 金叉买入、死叉卖出的交易信号
4. Action 参数: ("buy"/"sell"/"hold", confidence, target_position, model_id, inference_time_us)

您可以根据实际需要调整MACD参数或修改交易逻辑。`,

    默认: `根据您的需求，我已经为您生成了一个基础策略框架。

这个策略包含：
1. on_bar 方法，接收 bar: dict 返回 Action
2. Action("buy"/"sell"/"hold", confidence, target_position, model_id, inference_time_us)
3. 简单的价格跟踪逻辑

您可以根据实际需要进一步修改和完善这个策略。`,

    RL: `根据您的需求，我已经为您生成了一个 RL 策略。

这个策略包含：
1. 使用 axon_quant TradingEnv + Stable-Baselines3
2. 自动加载训练好的模型（从 data/rl_models/ 目录）
3. 12维观测特征（价格/成交量/SMA/EMA/RSI/MACD/Bollinger/ATR/动量）
4. on_bar 方法返回 Action("buy"/"sell"/"hold")

训练命令: python scripts/rl_cli.py train --symbol BTCUSDT --timesteps 30000
回测命令: python scripts/rl_cli.py backtest --model data/rl_models/xxx.zip
生命周期: python scripts/rl_cli.py lifecycle --symbol BTCUSDT --check-hours 24
`,
  };

  return explanations[templateKey] || explanations['默认'];
}

export const mockGenerateStrategyStream = async (
  prompt: string,
  onThinkingStep: (step: number, total: number) => void,
  modelId?: number | null,
  modelName?: string
): Promise<MockStrategyResponse> => {
  const thinkingSteps = 4;
  for (let i = 0; i < thinkingSteps; i++) {
    await new Promise((resolve) => setTimeout(resolve, 800));
    onThinkingStep(i, thinkingSteps);
  }
  return mockGenerateStrategy(prompt, modelId, modelName);
};

export default {
  mockGenerateStrategy,
  mockGenerateStrategyStream,
};
