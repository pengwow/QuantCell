import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import {
  Card,
  Button,
  Space,
  message,
  Spin,
  Tabs,
  Modal,
  Input,
  Descriptions,
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
} from '@ant-design/icons';
import MonacoEditor from '@monaco-editor/react';
import { useTranslation } from 'react-i18next';
import { useResponsive } from '../../hooks/useResponsive';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { strategyApi, aiModelApi } from '../../api';
import { setPageTitle } from '@/router';
import PageContainer from '@/components/PageContainer';
// AI 聊天弹窗组件
import AIChatModal from '@/components/AIChatModal';



interface Strategy {
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  params: Array<{
    name: string;
    type: string;
    default: any;
    description: string;
    required: boolean;
  }>;
  created_at: string;
  updated_at: string;
  code: string;
}



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

  // 策略版本编辑状态
  const [isEditingVersion, setIsEditingVersion] = useState<boolean>(false);
  const [tempVersion, setTempVersion] = useState<string>('');

  // 策略描述编辑状态
  const [isEditingDescription, setIsEditingDescription] = useState<boolean>(false);
  const [tempDescription, setTempDescription] = useState<string>('');

  // 参数描述编辑状态
  const [editingParamIndex, setEditingParamIndex] = useState<number | null>(null);
  const [editingParamDesc, setEditingParamDesc] = useState<string>('');

  // AI生成策略状态
  const [aiModalVisible, setAiModalVisible] = useState<boolean>(false);

  const navigate = useNavigate();
  const params = useParams<{ strategyName?: string }>();
  const location = useLocation();
  const { t } = useTranslation();
  const { isMobile } = useResponsive();
  const { isGuest } = useGuestRestriction();

  // 使用 AI 生成的代码创建策略
  const handleCreateStrategyWithCode = (generatedCode: string, strategyName?: string) => {
    const name = strategyName || 'ai_generated_strategy';
    const newStrategy: Strategy = {
      name: name,
      file_name: `${name}.py`,
      file_path: '',
      description: 'AI 生成的策略',
      version: '1.0.0',
      params: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: generatedCode,
    };

    setSelectedStrategy(newStrategy);
    setCode(generatedCode);
    message.success('AI 生成策略已加载到编辑器');
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
  }, [params.strategyName]);

  // 根据名称加载策略
  const loadStrategyByName = async (strategyName: string) => {
    try {
      setEditorLoading(true);
      const response = await strategyApi.getStrategyDetail(strategyName) as Strategy;
      setSelectedStrategy(response);
      setCode(response.code);
    } catch (error) {
      console.error('加载策略失败:', error);
      message.error('加载策略失败');
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
  const parseStrategy = async (retry = false) => {
    console.log('[parseStrategy] 开始解析策略, retry:', retry);
    if (!selectedStrategy) {
      console.log('[parseStrategy] 没有选中策略，直接返回');
      return;
    }

    const codeHash = generateCodeHash(code);
    console.log('[parseStrategy] codeHash:', codeHash);
    console.log('[parseStrategy] 缓存状态:', parseCache.has(codeHash), '缓存大小:', parseCache.size);
    
    if (!retry && parseCache.has(codeHash)) {
      const cached = parseCache.get(codeHash);
      console.log('[parseStrategy] 找到缓存数据:', cached);
      // 只有当缓存数据有效时才使用缓存
      if (isCacheValid(cached)) {
        console.log('[parseStrategy] 缓存数据有效，使用缓存');
        setParsedStrategy(cached);
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
      setParseError(null);
    } catch (error: any) {
      const errorMsg = error.message || '解析策略失败';
      setParseError(errorMsg);
    } finally {
      clearTimeout(timeoutId);
      setIsParsing(false);
    }
  };

  // 检查是否需要解析策略
  // 当代码发生变化或解析结果为空时，需要重新解析
  const shouldParseStrategy = (): boolean => {
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
      }
    }
  };

  // 返回策略管理页面
  const handleBack = () => {
    navigate('/strategy-management');
  };

  // 创建新策略
  const handleCreateStrategy = () => {
    const newStrategy: Strategy = {
      name: 'new_strategy',
      file_name: 'new_strategy.py',
      file_path: '',
      description: '新策略 - SMA交叉策略模板',
      version: '1.0.0',
      params: [
        { name: 'fast_period', type: 'int', default: 10, description: '短期均线周期', required: false },
        { name: 'slow_period', type: 'int', default: 30, description: '长期均线周期', required: false },
        { name: 'trade_size', type: 'float', default: 0.1, description: '每笔交易数量', required: false },
      ],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: `# -*- coding: utf-8 -*-
"""
简单SMA交叉策略

使用统一策略接口的双均线交叉策略示例。
当短期均线上穿长期均线时买入，下穿时卖出。

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
    """
    简单SMA交叉策略配置

    支持单品种和多品种回测，统一使用列表形式传参

    Parameters
    ----------
    instrument_ids : List[InstrumentId]
        策略交易的品种ID列表
    bar_types : List[str]
        策略订阅的K线类型列表，例如 ["1-HOUR", "1-MINUTE"]
    trade_size : Decimal
        每笔交易的数量，默认 0.1
    fast_period : int
        短期均线周期，默认 10
    slow_period : int
        长期均线周期，默认 30

    """

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
    """
    简单SMA交叉策略（支持多品种）

    最简单的双均线交叉策略实现：
    - 计算短期和长期SMA
    - 短期均线上穿长期均线时买入
    - 短期均线下穿长期均线时卖出

    支持多品种，为每个品种维护独立的价格历史和SMA值。

    Parameters
    ----------
    config : NewStrategyConfig
        策略配置对象
    """

    def __init__(self, config: NewStrategyConfig) -> None:
        super().__init__(config)
        # 使用 _config 存储配置，避免与父类的 config property 冲突
        self._config = config

        # 为每个品种维护独立的数据结构
        # key: instrument_id, value: 价格历史列表
        self.prices: Dict[InstrumentId, List[float]] = {}

        # 当前SMA值
        self.fast_sma: Dict[InstrumentId, float] = {}
        self.slow_sma: Dict[InstrumentId, float] = {}

        # 上一个SMA值（用于判断交叉）
        self.prev_fast_sma: Dict[InstrumentId, float] = {}
        self.prev_slow_sma: Dict[InstrumentId, float] = {}

        # 初始化每个品种的数据结构
        for instrument_id in config.instrument_ids:
            self.prices[instrument_id] = []
            self.fast_sma[instrument_id] = 0.0
            self.slow_sma[instrument_id] = 0.0
            self.prev_fast_sma[instrument_id] = 0.0
            self.prev_slow_sma[instrument_id] = 0.0

    def on_start(self) -> None:
        """
        策略启动时调用
        """
        self.log_info(
            f"SMA交叉策略启动 - 快周期: {self._config.fast_period}, "
            f"慢周期: {self._config.slow_period}, "
            f"品种数: {len(self._config.instrument_ids)}"
        )

    def on_bar(self, bar: Bar) -> None:
        """
        K线数据处理

        Parameters
        ----------
        bar : Bar
            K线数据对象
        """
        # 获取当前K线对应的品种ID
        instrument_id = bar.instrument_id

        # 保存当前SMA值作为上一个值
        self.prev_fast_sma[instrument_id] = self.fast_sma[instrument_id]
        self.prev_slow_sma[instrument_id] = self.slow_sma[instrument_id]

        # 添加收盘价到历史
        close_price = bar.close
        self.prices[instrument_id].append(close_price)

        # 保持历史数据长度
        max_period = max(self._config.fast_period, self._config.slow_period)
        if len(self.prices[instrument_id]) > max_period * 2:
            self.prices[instrument_id] = self.prices[instrument_id][-max_period * 2:]

        # 计算SMA
        if len(self.prices[instrument_id]) >= self._config.slow_period:
            self.fast_sma[instrument_id] = (
                sum(self.prices[instrument_id][-self._config.fast_period:])
                / self._config.fast_period
            )
            self.slow_sma[instrument_id] = (
                sum(self.prices[instrument_id][-self._config.slow_period:])
                / self._config.slow_period
            )

            # 输出调试信息
            self.log_debug(
                f"[{instrument_id}] Close: {close_price:.2f}, "
                f"Fast SMA({self._config.fast_period}): {self.fast_sma[instrument_id]:.2f}, "
                f"Slow SMA({self._config.slow_period}): {self.slow_sma[instrument_id]:.2f}"
            )

            # 检查是否有足够的上一个值来判断交叉
            if (
                self.prev_fast_sma[instrument_id] > 0
                and self.prev_slow_sma[instrument_id] > 0
            ):
                # 判断金叉：短期均线上穿长期均线
                golden_cross = (
                    self.prev_fast_sma[instrument_id]
                    <= self.prev_slow_sma[instrument_id]
                    and self.fast_sma[instrument_id] > self.slow_sma[instrument_id]
                )

                # 判断死叉：短期均线下穿长期均线
                death_cross = (
                    self.prev_fast_sma[instrument_id]
                    >= self.prev_slow_sma[instrument_id]
                    and self.fast_sma[instrument_id] < self.slow_sma[instrument_id]
                )

                # 执行交易逻辑
                if golden_cross:
                    self._on_golden_cross(bar, instrument_id)
                elif death_cross:
                    self._on_death_cross(bar, instrument_id)

    def _on_golden_cross(self, bar: Bar, instrument_id: InstrumentId) -> None:
        """
        金叉信号处理

        Parameters
        ----------
        bar : Bar
            K线数据对象
        instrument_id : InstrumentId
            品种ID
        """
        self.log_info(
            f"[{instrument_id}] 金叉信号！"
            f"Fast SMA({self._config.fast_period}): {self.fast_sma[instrument_id]:.2f} "
            f"上穿 Slow SMA({self._config.slow_period}): {self.slow_sma[instrument_id]:.2f}"
        )

        # 如果当前空仓，买入该品种
        if self.is_flat(instrument_id):
            self.log_info(f"[{instrument_id}] 当前空仓，执行买入")
            self.buy(instrument_id, self._config.trade_size)
        # 如果当前空头，先平仓再买入
        elif self.is_short(instrument_id):
            self.log_info(f"[{instrument_id}] 当前空头，先平仓再买入")
            self.close_position(instrument_id)
            self.buy(instrument_id, self._config.trade_size)
        else:
            self.log_info(f"[{instrument_id}] 当前已持有多头，无需操作")

    def _on_death_cross(self, bar: Bar, instrument_id: InstrumentId) -> None:
        """
        死叉信号处理

        Parameters
        ----------
        bar : Bar
            K线数据对象
        instrument_id : InstrumentId
            品种ID
        """
        self.log_info(
            f"[{instrument_id}] 死叉信号！"
            f"Fast SMA({self._config.fast_period}): {self.fast_sma[instrument_id]:.2f} "
            f"下穿 Slow SMA({self._config.slow_period}): {self.slow_sma[instrument_id]:.2f}"
        )

        # 如果当前持有多头，卖出该品种
        if self.is_long(instrument_id):
            self.log_info(f"[{instrument_id}] 当前持有多头，执行卖出")
            self.sell(instrument_id, self._config.trade_size)
        else:
            self.log_info(f"[{instrument_id}] 当前未持有多头，无需操作")

    def on_stop(self) -> None:
        """
        策略停止时调用
        """
        self.log_info("SMA交叉策略停止")
        # 可以在这里添加统计信息输出
        self.log_info(f"共处理 {self.bars_processed} 条K线数据")
`,
    };

    setSelectedStrategy(newStrategy);
    setCode(newStrategy.code);
  };

  // 保存策略
  const handleSaveStrategy = async () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }

    Modal.confirm({
      title: '确认保存策略',
      content: '您确定要保存当前策略吗？',
      okText: '保存',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        try {
          setLoading(true);

          // 调用保存策略的API
          await strategyApi.uploadStrategyFile({
            strategy_name: selectedStrategy.name,
            file_content: code,
            version: selectedStrategy.version,
            description: selectedStrategy.description
          });

          message.success('策略保存成功');
        } catch (error) {
          console.error('保存策略失败:', error);
          message.error('保存策略失败');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // 重置策略代码
  const handleResetCode = () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
      return;
    }

    Modal.confirm({
      title: '确认重置策略代码',
      content: '您确定要重置当前策略代码吗？所有未保存的更改将丢失。',
      okText: '重置',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        if (selectedStrategy) {
          setCode(selectedStrategy.code);
          message.success('策略代码已重置');
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = () => {
    if (!selectedStrategy) {
      message.error('请先选择或创建策略');
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
    if (selectedStrategy && tempVersion.trim()) {
      setSelectedStrategy(prev => prev ? { ...prev, version: tempVersion.trim() } : null);
      setIsEditingVersion(false);
    }
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
    if (selectedStrategy) {
      setSelectedStrategy(prev => prev ? { ...prev, description: tempDescription } : null);
      setIsEditingDescription(false);
    }
  };

  // 处理临时描述变化
  const handleTempDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTempDescription(e.target.value);
  };

  // 开始编辑参数描述
  const handleStartEditParamDescription = (index: number, currentDesc: string) => {
    setEditingParamIndex(index);
    setEditingParamDesc(currentDesc);
  };

  // 保存参数描述
  const handleSaveParamDescription = (index: number) => {
    const strategy = parsedStrategy || selectedStrategy;
    if (strategy && strategy.params) {
      const updatedParams = [...strategy.params];
      updatedParams[index] = {
        ...updatedParams[index],
        description: editingParamDesc
      };
      
      // 更新解析后的策略
      if (parsedStrategy) {
        setParsedStrategy({
          ...parsedStrategy,
          params: updatedParams
        });
      }
      // 同时更新原始策略
      if (selectedStrategy) {
        setSelectedStrategy({
          ...selectedStrategy,
          params: updatedParams
        });
      }
    }
    setEditingParamIndex(null);
    setEditingParamDesc('');
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
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={handleSaveStrategy}
            loading={loading}
            disabled={isGuest}
          >
            {t('save') || '保存'}
          </Button>
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
        <Spin spinning={editorLoading} description="加载中...">
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
                            重试
                          </Button>
                        </div>
                      ) : (
                        <>
                          <h3 className="mb-4">{t('strategy_information') || '策略信息'}</h3>
                          <Descriptions bordered column={1} className="mb-5">
                            <Descriptions.Item label={t('version') || '版本'}>
                              <div className="min-h-[32px] flex items-center">
                                {isEditingVersion ? (
                                  <Input
                                    value={tempVersion}
                                    onChange={handleTempVersionChange}
                                    onPressEnter={handleSaveVersion}
                                    onBlur={handleSaveVersion}
                                    autoFocus
                                    className="w-full"
                                  />
                                ) : (
                                  <span 
                                    onClick={handleStartEditVersion} 
                                    className="cursor-pointer hover:text-blue-500 transition-colors block w-full py-1"
                                    title={t('click_to_edit') || '点击编辑'}
                                  >
                                    {(parsedStrategy || selectedStrategy)?.version || ''}
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
                                    {(parsedStrategy || selectedStrategy)?.description || t('no_description') || '暂无描述'}
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('created_at') || '创建时间'}>
                              {(parsedStrategy || selectedStrategy) ? new Date((parsedStrategy || selectedStrategy)!.created_at).toLocaleString() : ''}
                            </Descriptions.Item>
                            <Descriptions.Item label={t('updated_at') || '更新时间'}>
                              {(parsedStrategy || selectedStrategy) ? new Date((parsedStrategy || selectedStrategy)!.updated_at).toLocaleString() : ''}
                            </Descriptions.Item>
                          </Descriptions>

                          <h3 className="mt-5 mb-4">{t('parameter_list') || '参数列表'}</h3>
                          {((parsedStrategy || selectedStrategy)?.params && (parsedStrategy || selectedStrategy)!.params.length > 0) ? (
                            <Descriptions bordered column={1}>
                              {(parsedStrategy || selectedStrategy)!.params.map((param, index) => (
                                <Descriptions.Item key={index} label={param.name}>
                                  <div className="min-h-[80px]">
                                    {editingParamIndex === index ? (
                                      <Input.TextArea
                                        value={editingParamDesc}
                                        onChange={(e) => setEditingParamDesc(e.target.value)}
                                        onBlur={() => handleSaveParamDescription(index)}
                                        onPressEnter={() => handleSaveParamDescription(index)}
                                        autoFocus
                                        rows={3}
                                        className="w-full"
                                      />
                                    ) : (
                                      <p 
                                        className="cursor-pointer hover:text-blue-500 transition-colors block w-full py-1 mb-2"
                                        onClick={() => handleStartEditParamDescription(index, param.description || '')}
                                        title={t('click_to_edit') || '点击编辑描述'}
                                      >
                                        {param.description || t('no_description') || '暂无描述'}
                                      </p>
                                    )}
                                    <small>{t('type') || '类型'}: {param.type}, {t('default_value') || '默认值'}: {JSON.stringify(param.default)}</small>
                                  </div>
                                </Descriptions.Item>
                              ))}
                            </Descriptions>
                          ) : (
                            <div className="p-5 text-center text-gray-400">
                              {t('no_parameters') || '暂无参数'}
                            </div>
                          )}
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
              requirement: content,
              model_id: modelId || undefined,
              model_name: modelName || undefined,
            },
            // onThinkingChain - 思维链进度实时更新
            onThinkingChain,
            // onDone - 生成完成，一次性返回完整结果
            (result) => {
              onComplete({
                content: result.raw_content || result.code || '策略生成成功',
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
          message.success(t('ai_adopted') || '已采纳并应用到编辑器');
          setAiModalVisible(false);
        }}
        onRejectCode={() => {
          message.info(t('ai_rejected') || '已拒绝，可以继续提问');
        }}
      />
    </PageContainer>
  );
};

export default StrategyEditor;
