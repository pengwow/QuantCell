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
"""
双均线交叉策略
基于用户请求自动生成
"""

from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List

from strategy.core import (
    StrategyBase,
    StrategyConfig,
    Bar,
    InstrumentId,
)


class DualMAConfig(StrategyConfig):
    """双均线策略配置"""

    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        fast_period: int = 10,
        slow_period: int = 20,
        trade_size: Decimal = Decimal("0.1"),
        log_level: str = "INFO",
    ):
        super().__init__(instrument_ids, bar_types, trade_size, log_level)
        self.fast_period = fast_period
        self.slow_period = slow_period


class DualMAStrategy(StrategyBase):
    """
    双均线交叉策略
    
    当短期均线上穿长期均线时买入，下穿时卖出
    """

    def __init__(self, config: DualMAConfig) -> None:
        super().__init__(config)
        self._config = config
        self.prices: Dict[InstrumentId, List[float]] = {}
        self.fast_ma: Dict[InstrumentId, float] = {}
        self.slow_ma: Dict[InstrumentId, float] = {}

        for instrument_id in config.instrument_ids:
            self.prices[instrument_id] = []

    def calculate_ma(self, prices: List[float], period: int) -> float:
        """计算移动平均线"""
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period

    def on_start(self) -> None:
        """策略启动"""
        self.log_info(f"双均线策略启动 - 快线周期:{self._config.fast_period}, 慢线周期:{self._config.slow_period}")

    def on_bar(self, bar: Bar) -> None:
        """K线数据处理"""
        instrument_id = bar.instrument_id
        close_price = float(bar.close)
        self.prices[instrument_id].append(close_price)

        # 保持历史数据
        max_period = max(self._config.fast_period, self._config.slow_period) + 10
        if len(self.prices[instrument_id]) > max_period:
            self.prices[instrument_id] = self.prices[instrument_id][-max_period:]

        # 计算均线
        if len(self.prices[instrument_id]) >= self._config.slow_period:
            fast_ma = self.calculate_ma(self.prices[instrument_id], self._config.fast_period)
            slow_ma = self.calculate_ma(self.prices[instrument_id], self._config.slow_period)
            
            prev_fast = self.fast_ma.get(instrument_id, 0)
            prev_slow = self.slow_ma.get(instrument_id, 0)
            
            self.fast_ma[instrument_id] = fast_ma
            self.slow_ma[instrument_id] = slow_ma

            # 均线交叉判断
            if prev_fast > 0 and prev_slow > 0:
                if prev_fast <= prev_slow and fast_ma > slow_ma:
                    # 金叉 - 买入信号
                    if self.is_flat(instrument_id):
                        self.log_info(f"[{instrument_id}] 金叉买入信号 - 快线:{fast_ma:.2f}, 慢线:{slow_ma:.2f}")
                        self.buy(instrument_id, self._config.trade_size)
                elif prev_fast >= prev_slow and fast_ma < slow_ma:
                    # 死叉 - 卖出信号
                    if self.is_long(instrument_id):
                        self.log_info(f"[{instrument_id}] 死叉卖出信号 - 快线:{fast_ma:.2f}, 慢线:{slow_ma:.2f}")
                        self.sell(instrument_id, self._config.trade_size)

    def on_stop(self) -> None:
        """策略停止"""
        self.log_info("双均线策略停止")
`,

  MACD: `# -*- coding: utf-8 -*-
"""
MACD 策略
基于用户请求自动生成
"""

from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List

from strategy.core import (
    StrategyBase,
    StrategyConfig,
    Bar,
    InstrumentId,
)


class MACDConfig(StrategyConfig):
    """MACD策略配置"""

    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        trade_size: Decimal = Decimal("0.1"),
        log_level: str = "INFO",
    ):
        super().__init__(instrument_ids, bar_types, trade_size, log_level)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period


class MACDStrategy(StrategyBase):
    """
    MACD 策略
    
    基于 MACD 指标的金叉死叉进行交易
    """

    def __init__(self, config: MACDConfig) -> None:
        super().__init__(config)
        self._config = config
        self.prices: Dict[InstrumentId, List[float]] = {}
        self.ema_fast: Dict[InstrumentId, float] = {}
        self.ema_slow: Dict[InstrumentId, float] = {}
        self.macd: Dict[InstrumentId, float] = {}
        self.signal: Dict[InstrumentId, float] = {}

        for instrument_id in config.instrument_ids:
            self.prices[instrument_id] = []

    def calculate_ema(self, prices: List[float], period: int) -> float:
        """计算指数移动平均线"""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema

    def on_start(self) -> None:
        """策略启动"""
        self.log_info("MACD策略启动")

    def on_bar(self, bar: Bar) -> None:
        """K线数据处理"""
        instrument_id = bar.instrument_id
        close_price = float(bar.close)
        self.prices[instrument_id].append(close_price)

        # 保持历史数据
        max_period = self._config.slow_period + self._config.signal_period + 20
        if len(self.prices[instrument_id]) > max_period:
            self.prices[instrument_id] = self.prices[instrument_id][-max_period:]

        # 计算 MACD
        if len(self.prices[instrument_id]) >= self._config.slow_period:
            ema_fast = self.calculate_ema(self.prices[instrument_id], self._config.fast_period)
            ema_slow = self.calculate_ema(self.prices[instrument_id], self._config.slow_period)
            macd = ema_fast - ema_slow
            
            # 计算信号线 (MACD的EMA)
            macd_values = list(self.macd.values())[-self._config.signal_period:] + [macd]
            signal = sum(macd_values[-self._config.signal_period:]) / min(len(macd_values), self._config.signal_period)
            
            prev_macd = self.macd.get(instrument_id, 0)
            prev_signal = self.signal.get(instrument_id, 0)
            
            self.ema_fast[instrument_id] = ema_fast
            self.ema_slow[instrument_id] = ema_slow
            self.macd[instrument_id] = macd
            self.signal[instrument_id] = signal

            # MACD 交叉判断
            if prev_macd != 0 and prev_signal != 0:
                if prev_macd <= prev_signal and macd > signal:
                    # MACD 上穿信号线 - 买入
                    if self.is_flat(instrument_id):
                        self.log_info(f"[{instrument_id}] MACD金叉买入信号")
                        self.buy(instrument_id, self._config.trade_size)
                elif prev_macd >= prev_signal and macd < signal:
                    # MACD 下穿信号线 - 卖出
                    if self.is_long(instrument_id):
                        self.log_info(f"[{instrument_id}] MACD死叉卖出信号")
                        self.sell(instrument_id, self._config.trade_size)

    def on_stop(self) -> None:
        """策略停止"""
        self.log_info("MACD策略停止")
`,

  默认: `# -*- coding: utf-8 -*-
"""
AI 生成的策略
基于用户请求自动生成
"""

from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List

from strategy.core import (
    StrategyBase,
    StrategyConfig,
    Bar,
    InstrumentId,
)


class AIGeneratedConfig(StrategyConfig):
    """AI生成策略配置"""

    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        trade_size: Decimal = Decimal("0.1"),
        log_level: str = "INFO",
    ):
        super().__init__(instrument_ids, bar_types, trade_size, log_level)


class AIGeneratedStrategy(StrategyBase):
    """
    AI 生成的策略
    
    根据您的需求自动生成的策略实现
    """

    def __init__(self, config: AIGeneratedConfig) -> None:
        super().__init__(config)
        self._config = config
        self.prices: Dict[InstrumentId, List[float]] = {}

        for instrument_id in config.instrument_ids:
            self.prices[instrument_id] = []

    def on_start(self) -> None:
        """策略启动"""
        self.log_info("AI生成策略启动")

    def on_bar(self, bar: Bar) -> None:
        """K线数据处理"""
        instrument_id = bar.instrument_id
        close_price = float(bar.close)
        self.prices[instrument_id].append(close_price)

        # 保持历史数据
        if len(self.prices[instrument_id]) > 100:
            self.prices[instrument_id] = self.prices[instrument_id][-100:]

        # 简单的示例逻辑：价格高于前一期买入，低于卖出
        if len(self.prices[instrument_id]) >= 2:
            prev_price = self.prices[instrument_id][-2]
            
            if close_price > prev_price and self.is_flat(instrument_id):
                self.log_info(f"[{instrument_id}] 价格上涨，买入信号")
                self.buy(instrument_id, self._config.trade_size)
            elif close_price < prev_price and self.is_long(instrument_id):
                self.log_info(f"[{instrument_id}] 价格下跌，卖出信号")
                self.sell(instrument_id, self._config.trade_size)

    def on_stop(self) -> None:
        """策略停止"""
        self.log_info("AI生成策略停止")
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
