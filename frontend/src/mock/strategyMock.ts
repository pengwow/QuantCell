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

from axon_quant import Action, ActionType


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
            return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)

        fast_ma = sum(self.closes[-self.fast:]) / self.fast
        slow_ma = sum(self.closes[-self.slow:]) / self.slow

        fast_above_slow = fast_ma > slow_ma

        if self._prev_fast_above_slow is None:
            self._prev_fast_above_slow = fast_above_slow
            return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)

        if not self._prev_fast_above_slow and fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            return Action(ActionType.Buy, 0.8, 0.1, "dual_ma", 0)

        if self._prev_fast_above_slow and not fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            return Action(ActionType.Sell, 0.8, 0.0, "dual_ma", 0)

        self._prev_fast_above_slow = fast_above_slow
        return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)
`,

  MACD: `# -*- coding: utf-8 -*-
"""MACD 策略 — axon_quant 规则策略"""

from axon_quant import Action, ActionType


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
            return Action(ActionType.Hold, 0.0, 0.0, "macd", 0)

        # EMA 计算
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
                return Action(ActionType.Buy, 0.8, 0.1, "macd", 0)
            if self._prev_macd >= self._prev_signal and macd < sig and self._position_side == "long":
                self._position_side = "flat"
                self._prev_macd = macd
                self._prev_signal = sig
                return Action(ActionType.Sell, 0.8, 0.0, "macd", 0)

        self._prev_macd = macd
        self._prev_signal = sig
        return Action(ActionType.Hold, 0.0, 0.0, "macd", 0)
`,

  默认: `# -*- coding: utf-8 -*-
"""AI 生成的策略 — axon_quant 规则策略"""

from axon_quant import Action, ActionType


class AIStrategy:
    """AI 生成的策略"""

    def __init__(self):
        self.closes: list[float] = []

    def on_start(self) -> None:
        self.closes.clear()

    def on_bar(self, bar: dict) -> Action:
        self.closes.append(bar["close"])

        if len(self.closes) < 2:
            return Action(ActionType.Hold, 0.0, 0.0, "ai_strategy", 0)

        prev = self.closes[-2]
        curr = bar["close"]

        if curr > prev:
            return Action(ActionType.Buy, 0.6, 0.1, "ai_strategy", 0)
        elif curr < prev:
            return Action(ActionType.Sell, 0.6, 0.0, "ai_strategy", 0)

        return Action(ActionType.Hold, 0.0, 0.0, "ai_strategy", 0)
`,
};

// 模拟策略生成 API
export const mockGenerateStrategy = async (
  prompt: string,
  _modelId?: number | null,
  modelName?: string
): Promise<MockStrategyResponse> => {
  // 模拟网络延迟
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // 根据用户输入选择合适的策略模板
  let templateKey = '默认';
  const promptLower = prompt.toLowerCase();
  
  if (promptLower.includes('均线') || promptLower.includes('ma') || promptLower.includes('moving')) {
    templateKey = '双均线';
  } else if (promptLower.includes('macd')) {
    templateKey = 'MACD';
  }

  const code = strategyTemplates[templateKey] || strategyTemplates['默认'];

  // 构建响应
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

// 生成策略说明
function generateExplanation(_prompt: string, templateKey: string): string {
  const explanations: Record<string, string> = {
    双均线: `根据您的需求，我已经为您生成了一个双均线交叉策略。

这个策略包含：
1. 完整的配置类定义，支持自定义快慢线周期
2. 移动平均线计算逻辑
3. 金叉买入、死叉卖出的交易信号判断
4. 多品种支持
5. 详细的中文注释

您可以根据实际需要调整周期参数或修改交易逻辑。`,

    MACD: `根据您的需求，我已经为您生成了一个MACD策略。

这个策略包含：
1. 完整的配置类定义，支持自定义MACD参数
2. EMA指数移动平均线计算
3. MACD线和信号线计算
4. 金叉买入、死叉卖出的交易信号判断
5. 多品种支持

您可以根据实际需要调整MACD参数或修改交易逻辑。`,

    默认: `根据您的需求，我已经为您生成了一个基础策略框架。

这个策略包含：
1. 完整的配置类定义
2. 基础的价格跟踪逻辑
3. 简单的买卖信号判断
4. 多品种支持
5. 详细的中文注释

您可以根据实际需要进一步修改和完善这个策略。`,
  };

  return explanations[templateKey] || explanations['默认'];
}

// 模拟流式响应（用于逐步显示思考过程）
export const mockGenerateStrategyStream = async (
  prompt: string,
  onThinkingStep: (step: number, total: number) => void,
  modelId?: number | null,
  modelName?: string
): Promise<MockStrategyResponse> => {
  const thinkingSteps = 4;
  
  // 模拟思考过程
  for (let i = 0; i < thinkingSteps; i++) {
    await new Promise((resolve) => setTimeout(resolve, 800));
    onThinkingStep(i, thinkingSteps);
  }

  // 返回最终结果
  return mockGenerateStrategy(prompt, modelId, modelName);
};

export default {
  mockGenerateStrategy,
  mockGenerateStrategyStream,
};
