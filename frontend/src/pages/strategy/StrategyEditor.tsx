import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  Spin,
  Tabs,
  Modal,
  Input,
  Select,
  Descriptions,
  Tooltip,
  Tag,
  App,
} from 'antd';
import {
  PlayCircleOutlined,
  SaveOutlined,
  CodeOutlined,
  EyeOutlined,
  ReloadOutlined,
  BackwardOutlined,
  RobotOutlined,
  CloseCircleOutlined,
  EditOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import MonacoEditor from '@monaco-editor/react';
import { useTranslation } from 'react-i18next';
import { useResponsive } from '../../hooks/useResponsive';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { strategyApi, aiModelApi } from '../../api';
import { factorApi, type FactorDetail } from '../../api/factor';
import { setPageTitle } from '@/utils/pageTitle';
import PageContainer from '@/components/PageContainer';
// AI 聊天弹窗组件
import AIChatModal from '@/components/AIChatModal';



interface Strategy {
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  strategy_type?: 'rule' | 'rl';
  params: Array<{
    name: string;
    type: string;
    default: unknown;
    description: string;
    required: boolean;
  }>;
  factors?: Array<{
    name: string;
    type?: string;
    description?: string;
    default?: unknown;
  }>;
  created_at: string;
  updated_at: string;
  code: string;
}

/** 新建策略时的默认代码 — 对齐 QuantCell BaseStrategy 框架。
 * 展示 ctx.closes / ctx.get_feature / ActionType 枚举的正确用法。
 * 用户后续可从后端模板列表选择其他真实模板替代。
 */
const DEFAULT_NEW_STRATEGY_CODE = `# -*- coding: utf-8 -*-
"""简单 SMA 交叉策略示例 — 展示 QuantCell BaseStrategy 框架用法。

当短期均线上穿长期均线时买入，下穿时平仓。
参数通过 StrategyConfig.params 注入。
"""

from __future__ import annotations
from typing import Any

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class NewStrategy(BaseStrategy):
    """SMA 交叉策略 — 展示 BaseStrategy 正确用法。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period: int = config.params.get("fast_period", 10)
        self.slow_period: int = config.params.get("slow_period", 20)
        self.position_size: float = config.params.get("position_size", 0.1)

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
        closes = ctx.closes if ctx else []
        closes.append(bar["close"])

        # 因子调用示例 —— 运行时适配器会注入
        rsi = ctx.get_feature("rsi", 50.0) if ctx else 50.0

        if len(closes) < self.slow_period:
            return Action("hold", 0.0, 0.0, "new_strategy", 0)

        fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(closes[-self.slow_period:]) / self.slow_period

        if fast_ma > slow_ma:
            return Action("buy", 0.8, self.position_size, "new_strategy", 0)
        elif fast_ma < slow_ma:
            return Action("reduce_long", 0.8, 0.0, "new_strategy", 0)

        return Action("hold", 0.0, 0.0, "new_strategy", 0)
`;

/**
 * 策略编辑器组件
 * 功能：提供策略代码编辑、执行和结果预览功能
 */
const StrategyEditor = () => {
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [editorLoading, setEditorLoading] = useState<boolean>(false);
  const [code, setCode] = useState<string>('');

  const [activeTabKey, setActiveTabKey] = useState<string>('editor');
  const [isParsing, setIsParsing] = useState<boolean>(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsedStrategy, setParsedStrategy] = useState<Strategy | null>(null);
  const parseCache = new Map<string, Strategy>();

  // 策略名称编辑状态
  const [isEditingName, setIsEditingName] = useState<boolean>(false);
  const [tempName, setTempName] = useState<string>('');

  // 模板选择器状态
  const [templatePickerVisible, setTemplatePickerVisible] = useState(false);
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; category: string; description?: string; tags?: string[]; code_template?: string }>>([]);
  const [templatePickerLoading, setTemplatePickerLoading] = useState(false);

  // 策略版本编辑状态
  const [isEditingVersion, setIsEditingVersion] = useState<boolean>(false);
  const [tempVersion, setTempVersion] = useState<string>('');

  // 策略描述编辑状态
  const [isEditingDescription, setIsEditingDescription] = useState<boolean>(false);
  const [tempDescription, setTempDescription] = useState<string>('');

  // 行级编辑追踪：哪些行处于编辑态（新增行默认进入编辑态）
  const [editingParamRows, setEditingParamRows] = useState<Set<number>>(new Set());
  const [editingFactorRows, setEditingFactorRows] = useState<Set<number>>(new Set());

  // 因子库缓存：name → FactorDetail（用于显示因子的真实 label/描述）
  const [factorCatalog, setFactorCatalog] = useState<Map<string, FactorDetail>>(new Map());
  const [factorCatalogLoaded, setFactorCatalogLoaded] = useState(false);

  // 挂载时拉一次因子库（只拉一次，跨策略切换复用）
  useEffect(() => {
    if (factorCatalogLoaded) return;
    factorApi.listDetail().then((r) => {
      const m = new Map<string, FactorDetail>();
      for (const f of r.factors) m.set(f.name, f);
      setFactorCatalog(m);
      setFactorCatalogLoaded(true);
    }).catch(() => setFactorCatalogLoaded(true));
  }, [factorCatalogLoaded]);

  // AI生成策略状态
  const [aiModalVisible, setAiModalVisible] = useState<boolean>(false);
  const [aiStrategyType, setAiStrategyType] = useState<'rule' | 'rl'>('rule');

  // 数据来源状态：'database' 表示来自数据库，'parsed' 表示来自策略解析
  const [dataSource, setDataSource] = useState<'database' | 'parsed'>('database');

  const navigate = useNavigate();
  const params = useParams<{ strategyName?: string }>();
  const location = useLocation();
  const { t } = useTranslation();
  const { isMobile } = useResponsive();
  const { isGuest } = useGuestRestriction();
  const { message: appMessage, modal } = App.useApp();

  // 使用 AI 生成的代码创建策略
  const handleCreateStrategyWithCode = (generatedCode: string, strategyName?: string) => {
    const name = strategyName || 'ai_generated_strategy';
    const isRL = generatedCode.includes('TradingEnv') || generatedCode.includes('stable_baselines3') || generatedCode.includes('model.predict');
    const newStrategy: Strategy = {
      name: name,
      file_name: `${name}.py`,
      file_path: '',
      description: t('ai_generated_strategy') || 'AI 生成的策略',
      version: '1.0.0',
      params: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: generatedCode,
    };

    // 设置策略类型（根据代码特征判断 RL 策略或规则策略）
    newStrategy.strategy_type = isRL ? 'rl' : 'rule';

    setSelectedStrategy(newStrategy);
    setCode(generatedCode);
    appMessage.success(t('ai_loaded_to_editor') || 'AI 生成策略已加载到编辑器');
  };

  // 设置页面标题
  useEffect(() => {
    setPageTitle(params.strategyName || t('strategy_editor') || '策略编辑器');
  }, [params.strategyName, t]);

  // 组件挂载时，如果有策略名称参数，加载对应策略
  useEffect(() => {
    if (params.strategyName) {
      loadStrategyByName(params.strategyName);
    } else {
      // 检查是否有从其他页面传递过来的生成代码
      const state = location.state as {
        generatedCode?: string;
        generatedStrategyName?: string;
      } | null;

      if (state?.generatedCode) {
        // 使用 AI 生成的代码创建策略
        handleCreateStrategyWithCode(state.generatedCode, state.generatedStrategyName);
        // 清除 state，避免刷新页面时重复使用
        navigate(location.pathname, { replace: true });
      } else {
        // 创建新策略
        handleCreateStrategy();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [params.strategyName]);

  // 根据名称加载策略
  const loadStrategyByName = async (strategyName: string) => {
    try {
      setEditorLoading(true);
      const response = await strategyApi.getStrategyDetail(strategyName) as Strategy;
      setSelectedStrategy(response);
      setCode(response.code);
    } catch (error) {
      console.error(t('load_strategy_error', { message: error }) || '加载策略失败:', error);
      appMessage.error(t('load_strategy_failed') || '加载策略失败');
    } finally {
      setEditorLoading(false);
    }
  };

  // 检查缓存数据是否有效（params不为空列表）
  const isCacheValid = (cached: Strategy | undefined): cached is Strategy => {
    if (!cached) return false;
    // 如果params为空列表，认为缓存无效，需要重新解析
    if (!cached.params || cached.params.length === 0) return false;
    return true;
  };

  // 生成代码的哈希值（支持Unicode字符）
  const generateCodeHash = (code: string): string => {
    // 使用简单的字符串哈希算法，支持Unicode
    let hash = 0;
    for (let i = 0; i < code.length; i++) {
      const char = code.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // 转换为32位整数
    }
    return hash.toString(16);
  };

  // 解析策略
  // force: 是否强制重新解析，忽略缓存
  const parseStrategy = async (force = false) => {
    console.log('[parseStrategy] 开始解析策略, force:', force);
    if (!selectedStrategy) {
      console.log('[parseStrategy] 没有选中策略，直接返回');
      return;
    }

    const codeHash = generateCodeHash(code);
    console.log('[parseStrategy] codeHash:', codeHash);
    console.log('[parseStrategy] 缓存状态:', parseCache.has(codeHash), '缓存大小:', parseCache.size);

    // 如果不是强制解析，检查缓存
    if (!force && parseCache.has(codeHash)) {
      const cached = parseCache.get(codeHash);
      console.log('[parseStrategy] 找到缓存数据:', cached);
      // 只有当缓存数据有效时才使用缓存
      if (isCacheValid(cached)) {
        console.log('[parseStrategy] 缓存数据有效，使用缓存');
        setParsedStrategy(cached);
        setDataSource('parsed');
        setParseError(null);
        return;
      }
      console.log('[parseStrategy] 缓存数据无效，继续调用接口');
    }

    console.log('[parseStrategy] 调用后端接口解析策略');
    setIsParsing(true);
    setParseError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await Promise.race([
        strategyApi.parseStrategy(selectedStrategy.name, code) as Promise<Strategy>,
        new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('请求超时')), 30000);
        })
      ]);

      setParsedStrategy(response);
      parseCache.set(codeHash, response);
      setDataSource('parsed');
      setParseError(null);
      appMessage.success(t('parse_success') || '策略解析成功');
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : t('parse_failed') || '解析策略失败';
      setParseError(errorMsg);
      appMessage.error(t('parse_failed', { message: errorMsg }) || `策略解析失败: ${errorMsg}`);
    } finally {
      clearTimeout(timeoutId);
      setIsParsing(false);
    }
  };

  // 检查是否需要解析策略
  // 当代码发生变化或解析结果为空时，需要重新解析
  const shouldParseStrategy = (): boolean => {
    // 如果后台已有存储数据（selectedStrategy存在且有参数），直接使用存储数据，不再解析
    if (selectedStrategy && selectedStrategy.params && selectedStrategy.params.length > 0) {
      console.log('[shouldParseStrategy] 后台已有存储数据，直接使用，不需要解析');
      return false;
    }

    // 如果没有解析过，需要解析
    if (!parsedStrategy) {
      console.log('[shouldParseStrategy] 没有解析过，需要解析');
      return true;
    }

    // 检查当前解析结果是否对应当前代码
    const codeHash = generateCodeHash(code);
    const cached = parseCache.get(codeHash);
    
    // 如果缓存中没有对应当前代码的解析结果，需要重新解析
    if (!cached) {
      console.log('[shouldParseStrategy] 缓存中没有对应当前代码的解析结果，需要重新解析');
      return true;
    }

    // 如果缓存数据无效（params为空），需要重新解析
    if (!cached.params || cached.params.length === 0) {
      console.log('[shouldParseStrategy] 缓存数据无效（params为空），需要重新解析');
      return true;
    }

    console.log('[shouldParseStrategy] 不需要重新解析');
    return false;
  };

  // 处理标签页切换
  const handleTabChange = (key: string) => {
    console.log('[handleTabChange] 切换到标签页:', key);
    setActiveTabKey(key);
    if (key === 'preview') {
      console.log('[handleTabChange] 切换到preview，检查是否需要解析');
      // 只有在需要时才调用解析接口
      const needParse = shouldParseStrategy();
      console.log('[handleTabChange] 是否需要解析:', needParse);
      if (needParse) {
        parseStrategy();
      } else {
        // 如果不需要解析（使用存储数据），确保数据来源设置为数据库
        setDataSource('database');
      }
    }
  };

  // 切换数据来源
  const handleSwitchDataSource = () => {
    if (dataSource === 'database') {
      // 切换到解析数据
      if (parsedStrategy) {
        setDataSource('parsed');
        appMessage.info(t('switch_to_parsed') || '已切换到策略解析数据');
      } else {
        // 如果没有解析数据，提示用户先解析
        modal.confirm({
          title: t('no_parse_data') || '无解析数据',
          content: t('parse_now_confirm') || '当前没有策略解析数据，是否立即解析？',
          okText: t('parse_now') || '立即解析',
          cancelText: t('cancel') || '取消',
          onOk: () => {
            parseStrategy(true);
          },
        });
      }
    } else {
      // 切换到数据库数据
      setDataSource('database');
      appMessage.info(t('switch_to_db') || '已切换到数据库存储数据');
    }
  };

  // 返回策略管理页面
  const handleBack = () => {
    navigate('/strategy-management');
  };

  // 规则策略示例模板（on_bar → Action，双均线交叉）
  const buildRuleTemplate = () => `# -*- coding: utf-8 -*-
"""
简单SMA交叉策略

使用统一策略接口的规则策略模板：每个新K线触发 on_bar，
根据双均线交叉信号决定买入/卖出/持有。
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


class NewStrategyConfig(StrategyConfig):
    """双均线交叉策略配置"""

    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        trade_size: Decimal = Decimal("0.1"),
        fast_period: int = 10,
        slow_period: int = 30,
        log_level: str = "INFO",
    ):
        super().__init__(instrument_ids, bar_types, trade_size, log_level)
        self.fast_period = fast_period
        self.slow_period = slow_period


class NewStrategy(StrategyBase):
    """简单SMA交叉策略：快线上穿慢线买入，下穿卖出。"""

    def __init__(self, config: NewStrategyConfig) -> None:
        super().__init__(config)
        self._config = config
        self.prices: Dict[InstrumentId, List[float]] = {}
        for instrument_id in config.instrument_ids:
            self.prices[instrument_id] = []

    def on_start(self) -> None:
        self.log_info(
            f"SMA交叉策略启动 - 快周期: {self._config.fast_period}, "
            f"慢周期: {self._config.slow_period}"
        )

    def on_bar(self, bar: Bar) -> None:
        instrument_id = bar.instrument_id
        self.prices[instrument_id].append(bar.close)
        closes = self.prices[instrument_id]

        fast = self._config.fast_period
        slow = self._config.slow_period
        if len(closes) < slow:
            return

        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow
        prev_fast = sum(closes[-fast - 1:-1]) / fast
        prev_slow = sum(closes[-slow - 1:-1]) / slow

        if prev_fast <= prev_slow and fast_ma > slow_ma:
            self.log_info(f"[{instrument_id}] 金叉信号，买入")
            self.buy(instrument_id, self._config.trade_size)
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            self.log_info(f"[{instrument_id}] 死叉信号，卖出")
            self.sell(instrument_id, self._config.trade_size)

    def on_stop(self) -> None:
        self.log_info("SMA交叉策略停止")
`;

  // RL示例模板（TradingEnv + stable-baselines3）
  const buildRlTemplate = () => `# -*- coding: utf-8 -*-
"""
RL策略模板（强化学习）

基于 robot 环境 TradingEnv 训练 PPO 智能体，然后在 on_bar 中
通过 model.predict 推理输出目标仓位与置信度。
备注: TradingEnv 与 stable-baselines3 需安装 axon_quant / 扩展依赖。
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from stable_baselines3 import PPO

from axon_quant.rl import TradingEnv
from strategy.core import StrategyBase, StrategyConfig, Bar, InstrumentId


class RlStrategyConfig(StrategyConfig):
    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        trade_size: float = 0.1,
        log_level: str = "INFO",
        model_path: str = "",
    ):
        super().__init__(instrument_ids, bar_types, trade_size, log_level)
        self.model_path = model_path


class NewStrategy(StrategyBase):
    """RL策略模板：加载已训练 PPO 模型，在 on_bar 中推理决策。"""

    def __init__(self, config: RlStrategyConfig) -> None:
        super().__init__(config)
        self._config = config
        self.model = PPO.load(config.model_path) if config.model_path else None
        self.obs_buffer: Dict[InstrumentId, List[float]] = {}

    def _train(self, market_data: List[Dict[str, Any]]) -> None:
        """训练入口：构建 TradingEnv 后训练并保存模型。"""
        env = TradingEnv(config={}, action_space="discrete", market_data=market_data, reward="sharpe")
        model = PPO("MlpPolicy", env, verbose=1)
        model.learn(total_timesteps=10_000)
        model.save("rl_model.zip")

    def on_bar(self, bar: Bar) -> None:
        if not self.model:
            self.log_info("未加载 RL 模型，跳过推理")
            return
        state = np.array([bar.close, bar.volume], dtype=np.float32)
        action, _ = self.model.predict(state, deterministic=True)
        target = float(action) * self._config.trade_size
        self.log_debug(f"[{bar.instrument_id}] action={action}, 目标仓位={target:.2f}")
`;

  // 切换策略类型：确认后同步替换编辑器内容为对应类型的示例模板
  const handleStrategyTypeChange = (type: 'rule' | 'rl') => {
    if (type === aiStrategyType) return;
    const typeLabel = type === 'rl' ? 'RL策略' : '规则策略';
    modal.confirm({
      title: '切换策略类型',
      content: `切换到「${typeLabel}」后，编辑器内容将替换为对应的示例模板。当前未保存的代码会被覆盖，是否继续？`,
      okText: '切换',
      cancelText: t('cancel') || '取消',
      onOk: () => {
        setAiStrategyType(type);
        setCode(type === 'rl' ? buildRlTemplate() : buildRuleTemplate());
      },
    });
  };

  // 创建新策略 —— 弹出模板选择器
  const handleCreateStrategy = async () => {
    setTemplatePickerLoading(true);
    try {
      // 拉真实模板列表（后端 strategy/templates/ 扫描结果）
      const list = await aiModelApi.getTemplates();
      setTemplates(list as any);
    } catch {
      // 拉取失败也允许用户继续（用默认代码）
      setTemplates([]);
    } finally {
      setTemplatePickerLoading(false);
      setTemplatePickerVisible(true);
    }
  };

  // 用户在模板选择器里点选模板或跳过
  const handlePickTemplate = (templateId: string | null) => {
    let code = DEFAULT_NEW_STRATEGY_CODE;
    let description = t('new_strategy_template') || '新策略 - 基于 BaseStrategy 新框架';
    let params = [
      { name: 'fast_period', type: 'int', default: 10, description: t('short_period') || '短期均线周期', required: false },
      { name: 'slow_period', type: 'int', default: 30, description: t('long_period') || '长期均线周期', required: false },
      { name: 'position_size', type: 'float', default: 0.1, description: '目标仓位比例 (0.0-1.0)', required: false },
    ];

    if (templateId) {
      const tpl = templates.find((t) => t.id === templateId);
      if (tpl?.code_template) {
        code = tpl.code_template;
        description = `${tpl.name} — ${tpl.description || ''}`.trim();
        // 模板自带的参数解析后续迭代（variables 字段暂未自动推断）
      }
    }

    const newStrategy: Strategy = {
      name: templateId ? templateId : 'new_strategy',
      file_name: `${templateId || 'new_strategy'}.py`,
      file_path: '',
      description,
      version: '1.0.0',
      params,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code,
    };

    setSelectedStrategy(newStrategy);
    setCode(code);
    setTemplatePickerVisible(false);
  };

  // 保存策略
  const handleSaveStrategy = async () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy') || '请先选择或创建策略');
      return;
    }

    modal.confirm({
      title: t('confirm_save_strategy') || '确认保存策略',
      content: t('save_strategy_confirm') || '您确定要保存当前策略吗？',
      okText: t('save') || '保存',
      okType: 'primary',
      cancelText: t('cancel') || '取消',
      onOk: async () => {
        try {
          setLoading(true);

          // 调用保存策略的API（带手动维护的 params + factors）
          // type coercion：Input 把 default 全转成了 string，保存前按 type 字段转回正确类型
          const coercedParams = (selectedStrategy.params || []).map((p: any) => {
            const v = p.default;
            let coerced: any = v;
            if (v !== null && v !== undefined && v !== '' && typeof v === 'string') {
              switch (p.type) {
                case 'int':
                  coerced = Number.isInteger(Number(v)) ? Number(v) : v;
                  break;
                case 'float':
                  coerced = Number(v);
                  break;
                case 'bool':
                  coerced = v.toLowerCase() === 'true';
                  break;
                case 'str':
                  coerced = v;
                  break;
              }
            }
            return { ...p, default: coerced };
          });

          await strategyApi.uploadStrategyFile({
            strategy_name: selectedStrategy.name,
            file_content: code,
            version: selectedStrategy.version,
            description: selectedStrategy.description,
            params: coercedParams,
            factors: selectedStrategy.factors || [],
            strategy_type: selectedStrategy.strategy_type || 'rule',
          });

          appMessage.success(t('strategy_saved') || '策略保存成功');
        } catch (error) {
          console.error(t('save_strategy_failed') || '保存策略失败:', error);
          appMessage.error(t('save_strategy_failed') || '保存策略失败');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // —— 参数增删改 + 行编辑态 ——
  // ponytail: 同时更新 selectedStrategy 和 parsedStrategy，避免 dataSource 切到 parsed 视图时修改白做

  const handleParamChange = (index: number, field: string, value: any) => {
    if (!selectedStrategy) return;
    const params = [...selectedStrategy.params];
    params[index] = { ...params[index], [field]: value };
    setSelectedStrategy({ ...selectedStrategy, params });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, params });
  };

  const handleAddParam = () => {
    if (!selectedStrategy) return;
    const params = [
      ...(selectedStrategy.params || []),
      { name: 'new_param', type: 'Any', default: null, description: '', required: false },
    ];
    setSelectedStrategy({ ...selectedStrategy, params });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, params });
    // 新增行自动进入编辑态
    setEditingParamRows(new Set([...editingParamRows, params.length - 1]));
  };

  const handleRemoveParam = (index: number) => {
    if (!selectedStrategy) return;
    const params = (selectedStrategy.params || []).filter((_, i) => i !== index);
    setSelectedStrategy({ ...selectedStrategy, params });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, params });
    // 同步编辑态：删掉当前 index，后面的 -1
    setEditingParamRows(new Set([...editingParamRows].filter(i => i !== index).map(i => (i > index ? i - 1 : i))));
  };

  const toggleParamEdit = (index: number) => {
    const next = new Set(editingParamRows);
    if (next.has(index)) next.delete(index); else next.add(index);
    setEditingParamRows(next);
  };

  // —— 因子增删改 + 行编辑态 ——

  const handleFactorChange = (index: number, field: string, value: any) => {
    if (!selectedStrategy) return;
    const factors = [...(selectedStrategy.factors || [])];
    factors[index] = { ...factors[index], [field]: value };
    setSelectedStrategy({ ...selectedStrategy, factors });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, factors });
  };

  const handleAddFactor = () => {
    if (!selectedStrategy) return;
    const factors = [
      ...(selectedStrategy.factors || []),
      { name: '', type: 'factor', description: '' },
    ];
    setSelectedStrategy({ ...selectedStrategy, factors });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, factors });
    // 新增行自动进入编辑态
    setEditingFactorRows(new Set([...editingFactorRows, factors.length - 1]));
  };

  const handleRemoveFactor = (index: number) => {
    if (!selectedStrategy) return;
    const factors = (selectedStrategy.factors || []).filter((_, i) => i !== index);
    setSelectedStrategy({ ...selectedStrategy, factors });
    if (parsedStrategy) setParsedStrategy({ ...parsedStrategy, factors });
    setEditingFactorRows(new Set([...editingFactorRows].filter(i => i !== index).map(i => (i > index ? i - 1 : i))));
  };

  const toggleFactorEdit = (index: number) => {
    const next = new Set(editingFactorRows);
    if (next.has(index)) next.delete(index); else next.add(index);
    setEditingFactorRows(next);
  };

  // —— 重新解析（AST 扫源码，覆盖 DB 里的 params + factors，同步更新策略信息）——

  const handleReparseStrategy = async () => {
    if (!selectedStrategy) return;
    modal.confirm({
      title: t('confirm_reparse') || '确认重新解析',
      content: t('reparse_warning') || '将从策略源码 AST 提取参数、因子和描述信息，覆盖数据库中的当前版本。确定要继续吗？',
      okText: t('reparse') || '重新解析',
      okType: 'primary',
      cancelText: t('cancel') || '取消',
      onOk: async () => {
        try {
          appMessage.loading({ content: t('reparsing') || '重新解析中...', key: 'reparse' });
          const res = await strategyApi.reparseStrategy(selectedStrategy.name);
          const info: any = (res as any)?.data ?? res;
          // 完整同步后端返回的策略信息（含 description / version / params / factors 等）
          setSelectedStrategy({
            ...selectedStrategy,
            description: info?.description ?? selectedStrategy.description,
            version: info?.version ?? selectedStrategy.version,
            params: info?.params || [],
            factors: info?.factors || [],
          });
          // 强制切回 database 视图（后端已经写了 DB）
          setDataSource('database');
          appMessage.success({
            content: t('reparse_done') || `重新解析完成：参数 ${info?.params?.length || 0} 个，因子 ${info?.factors?.length || 0} 个`,
            key: 'reparse',
          });
        } catch (e: any) {
          appMessage.error({ content: `${t('reparse_failed') || '重新解析失败'}: ${e?.message || e}`, key: 'reparse' });
        }
      },
    });
  };

  // 重置策略代码
  const handleResetCode = () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy') || '请先选择或创建策略');
      return;
    }

    modal.confirm({
      title: t('confirm_reset_code') || '确认重置策略代码',
      content: t('reset_code_confirm') || '您确定要重置当前策略代码吗？所有未保存的更改将丢失。',
      okText: t('reset') || '重置',
      okType: 'danger',
      cancelText: t('cancel') || '取消',
      onOk: () => {
        if (selectedStrategy) {
          setCode(selectedStrategy.code);
          appMessage.success(t('code_reset') || '策略代码已重置');
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy') || '请先选择或创建策略');
      return;
    }

    navigate('/backtest/config', { state: { strategy: selectedStrategy, showConfig: true } });
  };

  // 开始编辑策略名称
  const handleStartEditName = () => {
    if (selectedStrategy) {
      setTempName(selectedStrategy.name);
      setIsEditingName(true);
    }
  };

  // 保存策略名称
  const handleSaveName = () => {
    if (selectedStrategy && tempName.trim()) {
      setSelectedStrategy(prev => prev ? { ...prev, name: tempName.trim() } : null);
      setIsEditingName(false);
    }
  };

  // 处理临时名称变化
  const handleTempNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempName(e.target.value);
  };

  // 开始编辑策略版本
  const handleStartEditVersion = () => {
    if (selectedStrategy) {
      setTempVersion(selectedStrategy.version);
      setIsEditingVersion(true);
    }
  };

  // 保存策略版本
  const handleSaveVersion = () => {
    const trimmedVersion = tempVersion.trim();
    if (!trimmedVersion) return;

    // 同时更新 parsedStrategy 和 selectedStrategy
    if (parsedStrategy) {
      setParsedStrategy({
        ...parsedStrategy,
        version: trimmedVersion
      });
    }
    if (selectedStrategy) {
      setSelectedStrategy({
        ...selectedStrategy,
        version: trimmedVersion
      });
    }
    setIsEditingVersion(false);
  };

  // 处理临时版本变化
  const handleTempVersionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempVersion(e.target.value);
  };

  // 开始编辑策略描述
  const handleStartEditDescription = () => {
    if (selectedStrategy) {
      setTempDescription(selectedStrategy.description);
      setIsEditingDescription(true);
    }
  };

  // 保存策略描述
  const handleSaveDescription = () => {
    // 同时更新 parsedStrategy 和 selectedStrategy
    if (parsedStrategy) {
      setParsedStrategy({
        ...parsedStrategy,
        description: tempDescription
      });
    }
    if (selectedStrategy) {
      setSelectedStrategy({
        ...selectedStrategy,
        description: tempDescription
      });
    }
    setIsEditingDescription(false);
  };

  // 处理临时描述变化
  const handleTempDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTempDescription(e.target.value);
  };

  // 根据编辑/创建模式确定页面标题
  const pageTitle = params.strategyName
    ? t('edit_strategy') || '编辑策略'
    : t('create_strategy') || '创建策略';

  return (
    <PageContainer title={pageTitle}>
      {/* 页面头部 */}
      <div className="flex flex-wrap justify-between items-center gap-4 mb-4">
        <div className="flex items-center flex-grow min-w-0">
          <Button
            type="default"
            icon={<BackwardOutlined />}
            onClick={handleBack}
            className="mr-4"
          >
            {t('back') || '返回'}
          </Button>
          {isEditingName ? (
            <div className="relative flex-grow min-w-0">
              <Input
                type="text"
                value={tempName}
                onChange={handleTempNameChange}
                onKeyPress={(e) => e.key === 'Enter' && handleSaveName()}
                onBlur={handleSaveName}
                autoFocus
                className="text-xl font-medium border-blue-500 rounded w-full max-w-xs"
              />
            </div>
          ) : (
            <h2
              className="text-xl font-medium m-0 cursor-pointer truncate"
              style={{
                maxWidth: isMobile ? '100%' : 'calc(100% - 100px)',
                whiteSpace: isMobile ? 'normal' : 'nowrap',
              }}
              onClick={handleStartEditName}
            >
              {selectedStrategy ? selectedStrategy.name : t('strategy_editor') || '策略编辑器'}
            </h2>
          )}
        </div>

        {/* 操作按钮组 */}
        <Space
          wrap
          className={isMobile ? 'w-full justify-start' : ''}
        >
          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={handleResetCode}
            loading={loading}
          >
            {t('reset') || '重置'}
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleBacktestStrategy}
            loading={loading}
          >
            {t('backtest') || '回测'}
          </Button>
          <Tooltip title={isGuest ? (t('guest_save_restricted') || '访客用户无法保存策略，请使用普通用户账号登录') : ''}>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSaveStrategy}
              loading={loading}
              disabled={isGuest}
            >
              {t('save') || '保存'}
            </Button>
          </Tooltip>
          <Select
            value={aiStrategyType}
            onChange={handleStrategyTypeChange}
            size="small"
            style={{ width: 100 }}
            options={[
              { value: 'rule', label: '规则策略' },
              { value: 'rl', label: 'RL 策略' },
            ]}
          />
          <Button
            type="default"
            icon={<RobotOutlined />}
            onClick={() => setAiModalVisible(true)}
          >
            {t('ai_generate') || 'AI生成'}
          </Button>
        </Space>
      </div>

      {/* 主内容区域 */}
      <Card>
        <Spin spinning={editorLoading} description={t('loading') || '加载中...'}>
          <Tabs
            activeKey={activeTabKey}
            onChange={handleTabChange}
            tabBarStyle={{ marginBottom: 0 }}
            items={[
              {
                key: 'editor',
                label: <><CodeOutlined /> {t('editor') || '编辑器'}</>,
                children: (
                  <div className="w-full" style={{ minHeight: '600px' }}>
                    <MonacoEditor
                      height="600px"
                      language="python"
                      value={code}
                      onChange={(value) => setCode(value || '')}
                      options={{
                        fontSize: 14,
                        minimap: { enabled: true },
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        tabSize: 4,
                        insertSpaces: true,
                        formatOnType: true,
                        formatOnPaste: true,
                        lineNumbers: "on",
                        scrollbar: { vertical: 'auto', horizontal: 'auto' },
                        wordWrap: 'on',
                      }}
                      theme="vs-dark"
                    />
                  </div>
                )
              },
              {
                key: 'preview',
                label: <><EyeOutlined /> {t('preview') || '预览'}</>,
                children: (
                  <div className="p-5">
                    <Spin spinning={isParsing} description="解析策略中...">
                      {parseError ? (
                        <div className="p-6 text-center border border-red-300 rounded-lg bg-red-50 dark:bg-red-900/20">
                          <CloseCircleOutlined className="text-4xl text-red-500 mb-4" />
                          <p className="text-red-600 dark:text-red-400 mb-4">{parseError}</p>
                          <Button
                            type="primary"
                            icon={<ReloadOutlined />}
                            onClick={() => parseStrategy(true)}
                          >
                            {t('retry') || '重试'}
                          </Button>
                        </div>
                      ) : (
                        <>
                          {/* 策略信息头部：标题、数据来源标签、操作按钮 */}
                          <div className="flex justify-between items-center mb-4">
                            <h3 className="mb-0">{t('strategy_information') || '策略信息'}</h3>
                            <Space>
                              {/* 数据来源标签 */}
                              <Tooltip title={dataSource === 'database' ? (t('data_from_db') || '当前显示数据来自数据库存储') : (t('data_from_parse') || '当前显示数据来自策略代码解析')}>
                                <Tag
                                  color={dataSource === 'database' ? 'blue' : 'green'}
                                  className="cursor-pointer"
                                  onClick={handleSwitchDataSource}
                                >
                                  {dataSource === 'database' ? (t('source_db') || '来源: 数据库') : (t('source_parse') || '来源: 策略解析')}
                                </Tag>
                              </Tooltip>
                              {/* 重新解析按钮 */}
                              <Button
                                icon={<ReloadOutlined />}
                                onClick={handleReparseStrategy}
                                size="small"
                              >
                                {t('reparse') || '重新解析'}
                              </Button>
                            </Space>
                          </div>

                          {/* 数据来源提示 */}
                          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded text-sm text-gray-600 dark:text-gray-400">
                            {dataSource === 'database' ? (
                              <span>{t('db_data_hint') || '当前显示的是数据库存储的策略信息。如需查看最新代码中的信息，请点击"重新解析"。'}</span>
                            ) : (
                              <span>{t('parse_data_hint') || '当前显示的是从代码解析的策略信息。如需恢复数据库中的信息，请点击来源标签切换。'}</span>
                            )}
                          </div>

                          <Descriptions bordered column={1} className="mb-5">
                            <Descriptions.Item label={t('version') || '版本'}>
                              <div className="min-h-[32px] flex items-center">
                                {isEditingVersion ? (
                                  <Input
                                    value={tempVersion}
                                    onChange={handleTempVersionChange}
                                    onPressEnter={handleSaveVersion}
                                    onBlur={handleSaveVersion}
                                    onFocus={(e) => e.target.select()}
                                    autoFocus
                                    className="w-full"
                                  />
                                ) : (
                                  <span
                                    onClick={handleStartEditVersion}
                                    className="cursor-pointer hover:text-blue-500 transition-colors block w-full py-1"
                                    title={t('click_to_edit') || '点击编辑'}
                                  >
                                    {dataSource === 'database'
                                      ? (selectedStrategy?.version || '')
                                      : (parsedStrategy?.version || selectedStrategy?.version || '')}
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('description') || '描述'}>
                              <div className="min-h-[120px]">
                                {isEditingDescription ? (
                                  <Input.TextArea
                                    value={tempDescription}
                                    onChange={handleTempDescriptionChange}
                                    onBlur={handleSaveDescription}
                                    onPressEnter={handleSaveDescription}
                                    onFocus={(e) => e.target.select()}
                                    autoFocus
                                    rows={5}
                                    className="w-full"
                                  />
                                ) : (
                                  <span
                                    onClick={handleStartEditDescription}
                                    className="cursor-pointer hover:text-blue-500 transition-colors whitespace-pre-wrap block w-full py-1"
                                    title={t('click_to_edit') || '点击编辑描述'}
                                  >
                                    {dataSource === 'database'
                                      ? (selectedStrategy?.description || t('no_description') || '暂无描述')
                                      : (parsedStrategy?.description || selectedStrategy?.description || t('no_description') || '暂无描述')}
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('created_at') || '创建时间'}>
                              {selectedStrategy ? new Date(selectedStrategy.created_at).toLocaleString() : ''}
                            </Descriptions.Item>
                            <Descriptions.Item label={t('updated_at') || '更新时间'}>
                              {selectedStrategy ? new Date(selectedStrategy.updated_at).toLocaleString() : ''}
                            </Descriptions.Item>
                          </Descriptions>

                          {/* —— 参数列表（可增删改） —— */}
                          <h3 className="mt-5 mb-3 flex items-center justify-between">
                            <span>{t('parameter_list') || '参数列表'}</span>
                            <Button
                              size="small"
                              type="primary"
                              onClick={handleAddParam}
                              disabled={!selectedStrategy}
                            >
                                + {t('add_parameter') || '添加参数'}
                              </Button>
                          </h3>
                          {(() => {
                            const params = dataSource === 'database'
                              ? (selectedStrategy?.params || [])
                              : (parsedStrategy?.params || selectedStrategy?.params || []);

                            return params.length > 0 ? (
                              <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
                                {params.map((param: any, index: number) => {
                                  const editing = editingParamRows.has(index);

                                  if (editing) {
                                    return (
                                      <div key={index} className="flex gap-2 items-start flex-wrap">
                                        <Input
                                          size="small"
                                          value={param.name}
                                          placeholder={t('param_name') || '名称'}
                                          onChange={(e) => handleParamChange(index, 'name', e.target.value)}
                                          style={{ width: 140 }}
                                        />
                                        <Select
                                          size="small"
                                          value={param.type || 'Any'}
                                          onChange={(v) => handleParamChange(index, 'type', v)}
                                          style={{ width: 100 }}
                                          options={[
                                            { value: 'int', label: 'int' },
                                            { value: 'float', label: 'float' },
                                            { value: 'str', label: 'str' },
                                            { value: 'bool', label: 'bool' },
                                            { value: 'Any', label: 'Any' },
                                          ]}
                                        />
                                        <Input
                                          size="small"
                                          value={param.default === undefined || param.default === null ? '' : String(param.default)}
                                          placeholder={t('default_value') || '默认值'}
                                          onChange={(e) => handleParamChange(index, 'default', e.target.value)}
                                          style={{ width: 140 }}
                                        />
                                        <Input
                                          size="small"
                                          value={param.description || ''}
                                          placeholder={t('description') || '描述'}
                                          onChange={(e) => handleParamChange(index, 'description', e.target.value)}
                                          style={{ flex: 1, minWidth: 160 }}
                                        />
                                        <Button
                                          size="small"
                                          type="primary"
                                          icon={<CheckOutlined />}
                                          onClick={() => toggleParamEdit(index)}
                                          title="完成"
                                        />
                                        <Button
                                          size="small"
                                          danger
                                          icon={<CloseCircleOutlined />}
                                          onClick={() => handleRemoveParam(index)}
                                          title={t('delete') || '删除'}
                                        />
                                      </div>
                                    );
                                  }

                                  // 只读态
                                  return (
                                    <div
                                      key={index}
                                      className="flex gap-2 items-center py-1 px-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer group"
                                      onClick={() => toggleParamEdit(index)}
                                      title="点击编辑"
                                    >
                                      <Tag color="blue" className="mb-0">{param.name}</Tag>
                                      <Tag color="purple" className="mb-0">{param.type || 'Any'}</Tag>
                                      {param.default !== undefined && param.default !== null && param.default !== '' && (
                                        <Tag color="geekblue" className="mb-0">= {String(param.default)}</Tag>
                                      )}
                                      {param.description && (
                                        <span className="text-gray-500 text-sm flex-1 truncate">{param.description}</span>
                                      )}
                                      <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Button
                                          size="small"
                                          type="text"
                                          icon={<EditOutlined />}
                                          onClick={(e) => { e.stopPropagation(); toggleParamEdit(index); }}
                                          title="编辑"
                                        />
                                        <Button
                                          size="small"
                                          type="text"
                                          danger
                                          icon={<CloseCircleOutlined />}
                                          onClick={(e) => { e.stopPropagation(); handleRemoveParam(index); }}
                                          title={t('delete') || '删除'}
                                        />
                                      </span>
                                    </div>
                                  );
                                })}
                              </Space>
                            ) : (
                              <div className="p-4 text-center text-gray-400 text-sm">
                                {t('no_parameters') || '暂无参数'}
                              </div>
                            );
                          })()}

                          {/* —— 因子列表（可增删改） —— */}
                          <h3 className="mt-5 mb-3 flex items-center justify-between">
                            <span>{t('factor_list') || '因子列表'}</span>
                            <Button
                              size="small"
                              type="primary"
                              onClick={handleAddFactor}
                              disabled={!selectedStrategy}
                            >
                              + {t('add_factor') || '添加因子'}
                            </Button>
                          </h3>
                          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
                            {(selectedStrategy?.factors && selectedStrategy.factors.length > 0) ? (
                              selectedStrategy.factors.map((factor: any, index: number) => {
                                const editing = editingFactorRows.has(index);

                                if (editing) {
                                  const catalog = factorCatalog.get(factor.name);
                                  return (
                                    <div key={index} className="flex gap-2 items-start flex-wrap">
                                      <Input
                                        size="small"
                                        value={factor.name}
                                        placeholder={t('factor_name') || '因子名'}
                                        onChange={(e) => handleFactorChange(index, 'name', e.target.value)}
                                        style={{ width: 160 }}
                                      />
                                      <Select
                                        size="small"
                                        value={factor.type || 'factor'}
                                        onChange={(v) => handleFactorChange(index, 'type', v)}
                                        style={{ width: 110 }}
                                        options={[
                                          { value: 'factor', label: 'factor' },
                                          { value: 'config_ref', label: 'config_ref' },
                                          { value: 'factor_param', label: 'factor_param' },
                                        ]}
                                      />
                                      <Input
                                        size="small"
                                        value={factor.description || catalog?.description || ''}
                                        placeholder={catalog?.description || t('description') || '描述'}
                                        onChange={(e) => handleFactorChange(index, 'description', e.target.value)}
                                        style={{ flex: 1, minWidth: 160 }}
                                      />
                                      <Button
                                        size="small"
                                        type="primary"
                                        icon={<CheckOutlined />}
                                        onClick={() => toggleFactorEdit(index)}
                                        title="完成"
                                      />
                                      <Button
                                        size="small"
                                        danger
                                        icon={<CloseCircleOutlined />}
                                        onClick={() => handleRemoveFactor(index)}
                                        title={t('delete') || '删除'}
                                      />
                                    </div>
                                  );
                                }

                                // 只读态
                                const typeColor: Record<string, string> = {
                                  factor: 'green',
                                  config_ref: 'orange',
                                  factor_param: 'cyan',
                                };
                                return (
                                  <div
                                    key={index}
                                    className="flex gap-2 items-center py-1 px-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer group"
                                    onClick={() => toggleFactorEdit(index)}
                                    title="点击编辑"
                                  >
                                    <Tag color="blue" className="mb-0">{factor.name}</Tag>
                                    <Tag color={typeColor[factor.type] || 'default'} className="mb-0">{factor.type || 'factor'}</Tag>
                                    {(() => {
                                      // 只读态同时展示因子库 label（中文名）和 description（表达式/说明），不显示"（因子库）"标记
                                      const catalog = factorCatalog.get(factor.name);
                                      const label = catalog?.label;
                                      const desc = factor.description || catalog?.description || '';
                                      const parts = [label, desc].filter(Boolean);
                                      return parts.length > 0 ? (
                                        <span className="text-gray-500 text-sm flex-1 truncate">
                                          {parts.join(' — ')}
                                        </span>
                                      ) : null;
                                    })()}
                                    <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                                      <Button
                                        size="small"
                                        type="text"
                                        icon={<EditOutlined />}
                                        onClick={(e) => { e.stopPropagation(); toggleFactorEdit(index); }}
                                        title="编辑"
                                      />
                                      <Button
                                        size="small"
                                        type="text"
                                        danger
                                        icon={<CloseCircleOutlined />}
                                        onClick={(e) => { e.stopPropagation(); handleRemoveFactor(index); }}
                                        title={t('delete') || '删除'}
                                      />
                                    </span>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-4 text-center text-gray-400 text-sm">
                                {t('no_factors') || '暂无因子（重新解析可从策略源码自动提取）'}
                              </div>
                            )}
                          </Space>
                        </>
                      )}
                    </Spin>
                  </div>
                )
              }
            ]}
          />
        </Spin>
      </Card>

      {/* AI生成策略弹窗 - 使用 AIChatModal 组件 */}
      <AIChatModal
        open={aiModalVisible}
        onClose={() => setAiModalVisible(false)}
        title={t('ai_generate_strategy') || 'AI生成策略'}
        welcomeTitle={t('ai_welcome') || '我是AI策略助手，请告诉我您需要什么策略？'}
        welcomeDescription={t('ai_example') || '例如：创建一个双均线交叉策略'}
        inputPlaceholder={t('ai_input_placeholder') || '请输入您的策略需求...'}
        onStreamGenerate={(content, modelId, modelName, onComplete, onError, onThinkingChain) => {
          // 使用优化后的流式策略生成 API
          // 思维链进度实时传输，代码内容一次性返回
          const cancelStream = aiModelApi.generateStrategyStream(
            {
              requirement: content + (aiStrategyType === 'rl' ? '\n[策略类型: RL策略，使用TradingEnv+stable-baselines3]' : '\n[策略类型: 规则策略，使用on_bar→Action]'),
              model_id: modelId || undefined,
              model_name: modelName || undefined,
            },
            // onThinkingChain - 思维链进度实时更新
            onThinkingChain,
            // onDone - 生成完成，一次性返回完整结果
            (result) => {
              // 后端在内容为空（如推理模型思维链耗尽 token 预算被截断）时本应发 error 事件，
              // 这里再兜一层：没有任何内容时按失败处理，避免误显示"策略生成成功"
              if (!result.raw_content?.trim() && !result.code?.trim()) {
                onError(new Error('模型未返回有效内容，请重试或更换模型（推理模型可能因思维链过长被截断）'));
                return;
              }
              onComplete({
                content: result.raw_content || result.code || '',
                code: result.code,
              });
            },
            // onError - 错误处理
            onError
          );

          return cancelStream;
        }}
        onAcceptCode={(code: string) => {
          setCode(code);
          appMessage.success(t('ai_adopted') || '已采纳并应用到编辑器');
          setAiModalVisible(false);
        }}
        onRejectCode={() => {
          appMessage.info(t('ai_rejected') || '已拒绝，可以继续提问');
        }}
      />

      {/* 模板选择器 —— 新建策略时弹出，列出后端 strategy/templates/ 扫描到的真实模板 */}
      <Modal
        title="选择策略模板"
        open={templatePickerVisible}
        onCancel={() => handlePickTemplate(null)}
        footer={null}
        width={560}
      >
        <div style={{ marginBottom: 12, color: '#666' }}>
          选择一个起始模板，或跳过使用空白 BaseStrategy 骨架：
        </div>
        <Select
          style={{ width: '100%' }}
          placeholder={templatePickerLoading ? '加载中...' : '选择模板（可跳过）'}
          loading={templatePickerLoading}
          disabled={templatePickerLoading}
          options={templates.map((t) => ({
            value: t.id,
            label: (
              <span>
                <strong>{t.name}</strong>
                <span style={{ color: '#888', marginLeft: 8 }}>
                  [{t.category}]
                </span>
                {t.tags?.length ? (
                  <span style={{ color: '#aaa', marginLeft: 8 }}>· {t.tags.join('/')}</span>
                ) : null}
              </span>
            ),
          }))}
          onChange={(id) => id && handlePickTemplate(id)}
        />
        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <button
            onClick={() => handlePickTemplate(null)}
            style={{
              background: 'transparent',
              border: '1px solid #d9d9d9',
              borderRadius: 6,
              padding: '4px 12px',
              cursor: 'pointer',
            }}
          >
            跳过，使用空白模板
          </button>
        </div>
      </Modal>
    </PageContainer>
  );
};

export default StrategyEditor;
