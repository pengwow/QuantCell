import { useState, useEffect, useRef } from 'react';
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
  Upload,
  Descriptions,
  Segmented,
  Tooltip,
  App,
  Drawer,
  Alert,
} from 'antd';
import {
  PlayCircleOutlined,
  SaveOutlined,
  CodeOutlined,
  EyeOutlined,
  ReloadOutlined,
  RobotOutlined,
  CloseCircleOutlined,
  EditOutlined,
  CheckOutlined,
  UploadOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import MonacoEditor, { type OnMount } from '@monaco-editor/react';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import {
  QC_EDITOR_BG,
  QC_EDITOR_BORDER,
  QC_EDITOR_FONT_FAMILY,
  QC_EDITOR_FONT_SIZE,
  QC_EDITOR_LINE_HEIGHT,
  QC_EDITOR_RADIUS,
  QC_THEME_NAME,
  registerQuantcellTheme,
} from '../../monaco/quantcellTheme';
import QcEditorStatusBar from '../../monaco/QcEditorStatusBar';
import StrategyVersionPanel from './StrategyVersionPanel';
import EditorPlanTab from './EditorPlanTab';
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
    options?: string[];
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

/** 按代码特征推断策略类型：RL 框架与 on_bar 框架不兼容，必须归类。
 * AI 采纳代码与上传本地文件两条路径共用，保证判定口径一致。 */
function inferStrategyType(code: string): 'rule' | 'rl' {
  return code.includes('TradingEnv') || code.includes('stable_baselines3') || code.includes('model.predict')
    ? 'rl'
    : 'rule';
}

/** 新建策略时的默认代码 — 对齐 QuantCell BaseStrategy 框架。
 * 展示 ctx.closes / ctx.get_feature / ActionType 枚举的正确用法。
 * 用户后续可从后端模板列表选择其他真实模板替代。
 */
const DEFAULT_NEW_STRATEGY_CODE = `# -*- coding: utf-8 -*-
"""Simple SMA crossover strategy — demonstrates QuantCell BaseStrategy usage.

Buy when the fast MA crosses above the slow MA, close on cross down.
Parameters are injected via StrategyConfig.params.
"""

from __future__ import annotations
from typing import Any

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext


class NewStrategy(BaseStrategy):
    """SMA crossover strategy — correct BaseStrategy usage."""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period: int = config.params.get("fast_period", 10)
        self.slow_period: int = config.params.get("slow_period", 20)
        self.position_size: float = config.params.get("position_size", 0.1)

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
        closes = ctx.closes if ctx else []
        closes.append(bar["close"])

        # Factor access example — injected by the runtime adapter
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
  // 已保存基线：版本历史恢复前判断编辑器是否有未保存改动
  const [savedCode, setSavedCode] = useState<string>('');
  const [versionsDrawerOpen, setVersionsDrawerOpen] = useState(false);
  // 编辑器状态栏光标位置（Ln/Col 必须来自真实光标，不写死）
  const [cursor, setCursor] = useState<{ line: number; column: number }>({ line: 1, column: 1 });

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
  const [templates, setTemplates] = useState<Array<{
    id: string;
    name: string;
    category: string;
    description?: string;
    tags?: string[];
    code_template?: string;
    /** 模板参数元数据（后端 AST 解析，select 类型带 options） */
    variables?: Array<{ name: string; type?: string; default?: unknown; description?: string; required?: boolean; options?: string[] }>;
  }>>([]);
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
  // 策略类型只在创建时选择（模板选择器内选择），编辑器里不再切换；已有策略类型随 strategy_type 字段走
  const [createStrategyType, setCreateStrategyType] = useState<'rule' | 'rl'>('rule');

  // 数据来源状态：'database' 表示来自数据库，'parsed' 表示来自策略解析
  const [dataSource, setDataSource] = useState<'database' | 'parsed'>('database');

  // D4:从集成工作台跳入带来的待预填 ensemble_id;一次性,模板确认时消费
  const prefillEnsembleIdRef = useRef('');

  const navigate = useNavigate();
  const params = useParams<{ strategyName?: string }>();
  const location = useLocation();
  const { t } = useTranslation();
  const { isGuest } = useGuestRestriction();
  const { message: appMessage, modal } = App.useApp();

  // 使用 AI 生成的代码创建策略
  const handleCreateStrategyWithCode = (generatedCode: string, strategyName?: string) => {
    const name = strategyName || 'ai_generated_strategy';
    const newStrategy: Strategy = {
      name: name,
      file_name: `${name}.py`,
      file_path: '',
      description: t('ai_generated_strategy'),
      version: '1.0.0',
      params: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: generatedCode,
    };

    // 设置策略类型（按代码特征推断，与上传文件路径共用同一判定）
    newStrategy.strategy_type = inferStrategyType(generatedCode);

    setSelectedStrategy(newStrategy);
    setCode(generatedCode);
    appMessage.success(t('ai_loaded_to_editor'));
  };

  // 编辑器挂载：注册光标追踪，驱动下方 mono 状态栏
  const handleEditorMount: OnMount = (editor) => {
    const pos = editor.getPosition();
    if (pos) setCursor({ line: pos.lineNumber, column: pos.column });
    editor.onDidChangeCursorPosition((e) => {
      setCursor({ line: e.position.lineNumber, column: e.position.column });
    });
  };

  // 设置页面标题
  useEffect(() => {
    setPageTitle(params.strategyName || t('strategy_editor'));
  }, [params.strategyName, t]);

  // 组件挂载时，如果有策略名称参数，加载对应策略
  useEffect(() => {
    if (params.strategyName) {
      loadStrategyByName(params.strategyName);
    } else {
      // 检查是否有从其他页面传递过来的生成代码 / 集成预填
      const state = location.state as {
        generatedCode?: string;
        generatedStrategyName?: string;
        prefillEnsembleId?: string;
      } | null;

      if (state?.generatedCode) {
        // 使用 AI 生成的代码创建策略
        handleCreateStrategyWithCode(state.generatedCode, state.generatedStrategyName);
        // 清除 state，避免刷新页面时重复使用
        navigate(location.pathname, { replace: true });
      } else if (state?.prefillEnsembleId) {
        // D4:集成工作台→建策略。预选 RL 类型(集成仅 RL 策略可用),
        // 用户确认模板时把 prefillEnsembleIdRef 写进 ensemble_id 参数默认值
        prefillEnsembleIdRef.current = state.prefillEnsembleId;
        handleCreateStrategy('rl');
        appMessage.success(t('se_msg_ensemble_prefill', { id: state.prefillEnsembleId }));
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
      setSavedCode(response.code);

      // 版本历史「载入编辑器」跳转进来（?restore=<快照 id>）：只把快照写进缓冲区。
      // savedCode 保持磁盘当前内容 → dirty 为真，点「保存」才落盘并生成新快照。
      const restoreId = new URLSearchParams(location.search).get('restore');
      if (restoreId) {
        try {
          const snapshot = await strategyApi.getStrategyVersion(strategyName, Number(restoreId));
          setCode(snapshot.code);
          const label = snapshot.version ? `v${snapshot.version}` : snapshot.code_hash.slice(0, 8);
          appMessage.info(t('sm_ver_loaded_to_editor', { label }));
        } catch (error) {
          console.error('Failed to load strategy version:', error);
          appMessage.error(t('sm_ver_detail_failed'));
        }
        navigate(location.pathname, { replace: true });
      }
    } catch (error) {
      console.error('Failed to load strategy:', error);
      appMessage.error(t('load_strategy_failed'));
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
    console.log('[parseStrategy] start parsing, force:', force);
    if (!selectedStrategy) {
      console.log('[parseStrategy] no strategy selected, return early');
      return;
    }

    const codeHash = generateCodeHash(code);
    console.log('[parseStrategy] codeHash:', codeHash);
    console.log('[parseStrategy] cache state:', parseCache.has(codeHash), 'cache size:', parseCache.size);

    // 如果不是强制解析，检查缓存
    if (!force && parseCache.has(codeHash)) {
      const cached = parseCache.get(codeHash);
      console.log('[parseStrategy] found cached data:', cached);
      // 只有当缓存数据有效时才使用缓存
      if (isCacheValid(cached)) {
        console.log('[parseStrategy] cache valid, using cached result');
        setParsedStrategy(cached);
        setDataSource('parsed');
        setParseError(null);
        return;
      }
      console.log('[parseStrategy] cache invalid, calling backend parse API');
    }

    console.log('[parseStrategy] calling backend parse API');
    setIsParsing(true);
    setParseError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await Promise.race([
        strategyApi.parseStrategy(selectedStrategy.name, code) as Promise<Strategy>,
        new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error(t('se_msg_request_timeout'))), 30000);
        })
      ]);

      setParsedStrategy(response);
      parseCache.set(codeHash, response);
      setDataSource('parsed');
      setParseError(null);
      appMessage.success(t('parse_success'));
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : t('se_msg_parse_failed');
      setParseError(errorMsg);
      appMessage.error(t('parse_failed', { message: errorMsg }));
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
      console.log('[shouldParseStrategy] stored data exists, skip parsing');
      return false;
    }

    // 如果没有解析过，需要解析
    if (!parsedStrategy) {
      console.log('[shouldParseStrategy] never parsed, need parsing');
      return true;
    }

    // 检查当前解析结果是否对应当前代码
    const codeHash = generateCodeHash(code);
    const cached = parseCache.get(codeHash);
    
    // 如果缓存中没有对应当前代码的解析结果，需要重新解析
    if (!cached) {
      console.log('[shouldParseStrategy] no parse result for current code, need reparsing');
      return true;
    }

    // 如果缓存数据无效（params为空），需要重新解析
    if (!cached.params || cached.params.length === 0) {
      console.log('[shouldParseStrategy] cache invalid (empty params), need reparsing');
      return true;
    }

    console.log('[shouldParseStrategy] no reparsing needed');
    return false;
  };

  // 处理标签页切换
  const handleTabChange = (key: string) => {
    console.log('[handleTabChange] switch to tab:', key);
    setActiveTabKey(key);
    if (key === 'preview') {
      console.log('[handleTabChange] switch to preview, check if parsing needed');
      // 只有在需要时才调用解析接口
      const needParse = shouldParseStrategy();
      console.log('[handleTabChange] need parsing:', needParse);
      if (needParse) {
        parseStrategy();
      } else {
        // 如果不需要解析（使用存储数据），确保数据来源设置为数据库
        setDataSource('database');
      }
    }
  };

  // 预览页数据来源切换（demo edSeg 对位，antd Segmented 受控值 = dataSource）。
  // 原逻辑是「点击当前项则反向切换」；Segmented 语义是「点另一项才触发」，按目标值分流：
  //  - 切回 database：直接切（与原 toggle 卸载 parse 侧一致）
  //  - 切到 parsed：已有解析结果直接切；没有则弹确认先解析（原逻辑一致）
  const handleSourceSegment = (value: string | number) => {
    const next = value as 'database' | 'parsed';
    if (next === dataSource) return;

    if (next === 'database') {
      setDataSource('database');
      appMessage.info(t('switch_to_db'));
      return;
    }

    if (parsedStrategy) {
      setDataSource('parsed');
      appMessage.info(t('switch_to_parsed'));
    } else {
      modal.confirm({
        title: t('no_parse_data'),
        content: t('parse_now_confirm'),
        okText: t('parse_now'),
        cancelText: t('cancel'),
        onOk: () => {
          parseStrategy(true);
        },
      });
    }
  };

  // 返回策略管理页面
  const handleBack = () => {
    navigate('/strategy-management');
  };

  // 规则策略模板直接用 DEFAULT_NEW_STRATEGY_CODE（未维护单独构建函数）
  // RL 示例模板（TradingEnv + stable-baselines3）
  const buildRlTemplate = () => `# -*- coding: utf-8 -*-
"""RL strategy template — loads a trained PPO model, on_bar inference outputs Action.

Deps: stable-baselines3, numpy, axon_quant.rl.
The exported model path after training is injected via config.params["model_path"].
"""

from __future__ import annotations
from typing import Any

import numpy as np
from stable_baselines3 import PPO

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext


class NewStrategy(BaseStrategy):
    """RL strategy template: loads a PPO model, on_bar infers target position."""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.model_path: str = config.params.get("model_path", "")
        self.position_size: float = config.params.get("position_size", 0.1)
        self.model = PPO.load(self.model_path) if self.model_path else None

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
        if not self.model:
            return Action("hold", 0.0, 0.0, "new_strategy", 0)

        closes = ctx.closes if ctx else []
        closes.append(bar["close"])

        if len(closes) < 50:
            return Action("hold", 0.0, 0.0, "new_strategy", 0)

        state = np.array(closes[-50:], dtype=np.float32)
        action, _ = self.model.predict(state, deterministic=True)
        target = float(action) * self.position_size

        if target > 0:
            return Action("buy", 0.8, target, "new_strategy", 0)
        elif target < 0:
            return Action("sell", 0.8, abs(target), "new_strategy", 0)

        return Action("hold", 0.8, 0.0, "new_strategy", 0)
`;

  // 当前策略类型：已有策略跟 strategy_type 字段走，未选中时默认规则策略；仅用于 AI 生成的提示后缀
  const strategyType: 'rule' | 'rl' = selectedStrategy?.strategy_type === 'rl' ? 'rl' : 'rule';

  // 创建新策略 —— 弹出模板选择器
  const handleCreateStrategy = async (preferType?: 'rule' | 'rl') => {
    // 每次新建都回到默认的规则策略类型，避免上次的 RL 选择串到新会话;
    // D4 场景可指定 preferType='rl' 预选
    setCreateStrategyType(preferType ?? 'rule');
    setTemplatePickerLoading(true);
    try {
      // 拉真实模板列表（后端 strategy/templates/ 扫描结果）
      // 后端返回 { list: [...], total: N } 分页结构，axios 拦截器已拆外层
      const res = await aiModelApi.getTemplates();
      const list = ((res as unknown as { list?: unknown[] })?.list ?? (Array.isArray(res) ? res : [])) as typeof templates;
      setTemplates(list);
    } catch {
      // 拉取失败也允许用户继续（用默认代码）
      setTemplates([]);
    } finally {
      setTemplatePickerLoading(false);
      setTemplatePickerVisible(true);
    }
  };

  // 用户在模板选择器里点选模板或直接确认创建（templateId=null）
  // RL 类型不走规则模板列表（两者框架不兼容），直接使用内置 RL 骨架
  const handlePickTemplate = (templateId: string | null) => {
    const isRl = createStrategyType === 'rl';

    let code = isRl ? buildRlTemplate() : DEFAULT_NEW_STRATEGY_CODE;
    let description = isRl
      ? t('se_field_rl_template_desc')
      : t('new_strategy_template');
    // RL 骨架依赖两个参数（与模板代码里 config.params.get 的 key 一一对应）
    let params: Strategy['params'] = isRl
      ? [
          { name: 'model_path', type: 'str', default: '', description: t('se_field_model_path_desc'), required: true },
          // 集成运行:填了 ensemble_id 则优先于 model_path(spec §4.4,二选一,后端硬校验)
          // D4:从集成工作台跳入时预填(一次性)
          { name: 'ensemble_id', type: 'str', default: prefillEnsembleIdRef.current, description: t('se_field_ensemble_id_desc'), required: false },
          { name: 'position_size', type: 'float', default: 0.1, description: t('se_field_position_size_desc'), required: false },
        ]
      : [
          { name: 'fast_period', type: 'int', default: 10, description: t('short_period'), required: false },
          { name: 'slow_period', type: 'int', default: 30, description: t('long_period'), required: false },
          { name: 'position_size', type: 'float', default: 0.1, description: t('se_field_position_size_desc'), required: false },
        ];

    if (!isRl && templateId) {
      const tpl = templates.find((t) => t.id === templateId);
      if (tpl?.code_template) {
        code = tpl.code_template;
        description = `${tpl.name} — ${tpl.description || ''}`.trim();
        // 用模板自带的参数元数据（后端 AST 解析的 variables，select 类型带 options），
        // 替代早先写死的双均线三参数 —— direction 丢失的根因就在这里
        if (tpl.variables?.length) {
          params = tpl.variables.map((v) => ({
            name: v.name,
            type: v.type || 'Any',
            default: v.default,
            description: v.description || '',
            required: !!v.required,
            ...(v.options ? { options: v.options } : {}),
          }));
        }
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
      // 类型在创建时确定并随策略保存（handleSaveStrategy 的 uploadStrategyFile 会带上它）
      strategy_type: createStrategyType,
    };

    setSelectedStrategy(newStrategy);
    setCode(code);
    setTemplatePickerVisible(false);
    // D4:ensemble_id 预填只生效一次,消费后清零,避免下一个新建策略串值
    prefillEnsembleIdRef.current = '';
  };

  // 上传本地 .py 创建策略：与模板 Select「选中即创建」对齐，选完文件直接进编辑器（未保存）。
  // 类型按代码特征推断回填 Segmented；params 留空走 AI 采纳先例，编辑器里可补。
  const handleCreateFromFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.py')) {
      appMessage.error(t('se_msg_py_only'));
      return;
    }
    // ponytail: 1MB 上限只防误传大文件；超限说明选错对象，策略脚本远小于此
    if (file.size > 1024 * 1024) {
      appMessage.error(t('se_msg_file_too_large'));
      return;
    }
    let content = '';
    try {
      content = await file.text();
    } catch {
      appMessage.error(t('se_msg_file_read_failed'));
      return;
    }
    const inferredType = inferStrategyType(content);
    setCreateStrategyType(inferredType);
    const name = file.name.replace(/\.py$/i, '');
    const newStrategy: Strategy = {
      name,
      file_name: file.name,
      file_path: '',
      description: t('se_msg_created_from_file', { name: file.name }),
      version: '1.0.0',
      params: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      code: content,
      strategy_type: inferredType,
    };
    setSelectedStrategy(newStrategy);
    setCode(content);
    setTemplatePickerVisible(false);
    appMessage.success(t(inferredType === 'rl' ? 'se_msg_created_from_file_rl' : 'se_msg_created_from_file_rule', { name }));
  };

  // 创建弹窗两处上传入口（模板下拉底部规则策略、RL 说明区链接）共用一套上传行为
  const uploadProps = {
    accept: '.py',
    maxCount: 1,
    showUploadList: false,
    // fire-and-forget：校验与读取在 handleCreateFromFile 内完成，antd 侧不发起上传
    beforeUpload: (file: File) => {
      handleCreateFromFile(file);
      return false;
    },
  };

  // 保存策略
  const handleSaveStrategy = async () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy'));
      return;
    }

    modal.confirm({
      title: t('confirm_save_strategy'),
      content: t('save_strategy_confirm'),
      okText: t('save'),
      okType: 'primary',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          setLoading(true);

          // 调用保存策略的API（带手动维护的 params + factors）
          // type coercion：Input 把 default 全转成了 string，保存前按 type 字段转回正确类型
          const coercedParams = (selectedStrategy.params || []).map((p: Strategy['params'][number]) => {
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
                case 'select':
                  // select 的值本身就是选项字符串，无需转换；显式列出防止日后加 default 分支时误伤
                  coerced = v;
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

          setSavedCode(code);
          appMessage.success(t('strategy_saved'));
        } catch (error) {
          console.error('Failed to save strategy:', error);
          appMessage.error(t('save_strategy_failed'));
        } finally {
          setLoading(false);
        }
      },
    });
  };

  // —— 参数增删改 + 行编辑态 ——
  // ponytail: 同时更新 selectedStrategy 和 parsedStrategy，避免 dataSource 切到 parsed 视图时修改白做

  const handleParamChange = (index: number, field: string, value: unknown) => {
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

  const handleFactorChange = (index: number, field: string, value: unknown) => {
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
      title: t('confirm_reparse'),
      content: t('reparse_warning'),
      okText: t('reparse'),
      okType: 'primary',
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          appMessage.loading({ content: t('reparsing'), key: 'reparse' });

          const isSaved = !!selectedStrategy.file_path;
          let info: any; // API 返回对象，字段名固定但缺接口定义

          if (isSaved) {
            // 已保存 → 后端 reparse（从磁盘读 + 写 DB）
            const res = await strategyApi.reparseStrategy(selectedStrategy.name);
            info = ((res as unknown as { data?: unknown })?.data ?? res) as any;
          } else {
            // 未保存 → 直接解析编辑器当前代码（不查 DB）
            info = await strategyApi.parseStrategy(selectedStrategy.name, code);
          }

          setSelectedStrategy({
            ...selectedStrategy,
            description: info?.description ?? selectedStrategy.description,
            version: info?.version ?? selectedStrategy.version,
            params: info?.params || [],
            factors: info?.factors || [],
          });
          appMessage.success({
            content: t('se_msg_reparse_done', { params: info?.params?.length || 0, factors: info?.factors?.length || 0 }),
            key: 'reparse',
          });
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e);
          appMessage.error({ content: `${t('reparse_failed')}: ${msg}`, key: 'reparse' });
        }
      },
    });
  };

  // 重置策略代码
  const handleResetCode = () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy'));
      return;
    }

    modal.confirm({
      title: t('confirm_reset_code'),
      content: t('reset_code_confirm'),
      okText: t('reset'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: () => {
        if (selectedStrategy) {
          setCode(selectedStrategy.code);
          appMessage.success(t('code_reset'));
        }
      },
    });
  };

  // 回测策略
  const handleBacktestStrategy = () => {
    if (!selectedStrategy) {
      appMessage.error(t('please_select_create_strategy'));
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

  // 根据编辑/创建模式确定页面标题（未选中策略时的兜底；选中后标题 = 真实策略名，demo edTitle 对位）
  const pageTitle = params.strategyName
    ? t('edit_strategy')
    : t('create_strategy');

  // §5 page-sub mono 真值副标（demo「最近保存 … · 来源 database」）：
  // 真实口径 = updated_at + 数据来源，缺词条 se_sub_last_saved 已报缺口；未选中策略时不出副标，不造假数据
  // 时间口径统一 demo（MM-DD HH:mm）；完整时间只在档案行 tooltip 里给，不新增字段
  const fmtShortTime = (value?: string | null): string => {
    if (!value) return '—';
    const d = dayjs(value);
    return d.isValid() ? d.format('MM-DD HH:mm') : '—';
  };
  const fmtFullTime = (value?: string | null): string => {
    if (!value) return '';
    const d = dayjs(value);
    return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : '';
  };

  const editorSubtitle = !selectedStrategy
    ? undefined
    : [
        `${t('updated_at')} ${fmtShortTime(selectedStrategy.updated_at)}`,
        t(dataSource === 'database' ? 'source_db' : 'source_parse'),
      ].join(' · ');

  // §6.1 页头动作钮：30px 带字（demo page-actions）；主色钮 550 字重
  const btn30Style: React.CSSProperties = { height: 30, padding: '0 12px', fontSize: 12 };
  const btn30PrimaryStyle: React.CSSProperties = { ...btn30Style, fontWeight: 550 };

  return (
    <PageContainer
      title={selectedStrategy?.name || pageTitle}
      subtitle={editorSubtitle}
      onBack={handleBack}
      titleExtra={
        /* 版本 chip（demo #edVer）：真实 version，与标题同一基线（§5 titleExtra 槽） */
        selectedStrategy ? (
          <span className="qc-ed-title-extra">
            {selectedStrategy.version ? (
              <span className="qc-chip info qc-mono">{`v${selectedStrategy.version}`}</span>
            ) : null}
            {/* 载入历史快照 / 手改代码后与磁盘内容不一致：提示未保存，保存后才落盘并生成快照 */}
            {code !== savedCode ? <span className="qc-chip warn">{t('se_unsaved')}</span> : null}
          </span>
        ) : undefined
      }
      actions={
        <>
          <Tooltip title={t('reset')}>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleResetCode}
              loading={loading}
              style={btn30Style}
              aria-label={t('reset')}
            >
              {t('reset')}
            </Button>
          </Tooltip>
          <Tooltip title={t('se_action_goto_backtest')}>
            <Button
              icon={<PlayCircleOutlined />}
              onClick={handleBacktestStrategy}
              loading={loading}
              style={btn30Style}
              aria-label={t('se_action_goto_backtest')}
            >
              {t('se_action_goto_backtest')}
            </Button>
          </Tooltip>
          <Tooltip title={t('sm_ver_editor_entry')}>
            <Button
              icon={<HistoryOutlined />}
              onClick={() => setVersionsDrawerOpen(true)}
              disabled={!selectedStrategy}
              style={btn30Style}
              aria-label={t('sm_ver_editor_entry')}
            >
              {t('sm_ver_editor_entry')}
            </Button>
          </Tooltip>
          {/* 访客时 Tooltip 显示保存限制提示，正常显示按钮名 */}
          <Tooltip title={isGuest ? t('guest_save_restricted') : t('save')}>
            <Button
              icon={<SaveOutlined />}
              onClick={handleSaveStrategy}
              loading={loading}
              disabled={isGuest}
              style={btn30Style}
              aria-label={t('save')}
            >
              {t('save')}
            </Button>
          </Tooltip>
          {/* AI 助手入口：单击直接打开对话框，模式选择（生成/优化）移到对话框内部；demo 中为唯一主色钮 */}
          <Tooltip title={t('ai_generate_strategy')}>
            <Button
              type="primary"
              icon={<RobotOutlined />}
              onClick={() => setAiModalVisible(true)}
              style={btn30PrimaryStyle}
              aria-label={t('ai_generate_strategy')}
            >
              {t('ai_generate_strategy')}
            </Button>
          </Tooltip>
        </>
      }
    >
      {/* 主内容区域：demo 结构 = 页签直接落页，编辑器面板自带 §6.16 chrome，预览为 qc-card */}
      <Spin spinning={editorLoading} description={t('loading')}>
        <Tabs
          activeKey={activeTabKey}
          onChange={handleTabChange}
          items={[
              {
                key: 'editor',
                label: <><CodeOutlined /> {t('editor')}</>,
                children: (
                  <div
                    className="w-full"
                    style={{
                      minHeight: '600px',
                      // 编辑器 chrome 恒深色（design-spec §6.16），不随 light/dark 主题
                      background: QC_EDITOR_BG,
                      border: QC_EDITOR_BORDER,
                      borderRadius: QC_EDITOR_RADIUS,
                      overflow: 'hidden',
                    }}
                  >
                    <MonacoEditor
                      height="600px"
                      language="python"
                      value={code}
                      onChange={(value) => setCode(value || '')}
                      beforeMount={registerQuantcellTheme}
                      onMount={handleEditorMount}
                      options={{
                        fontSize: QC_EDITOR_FONT_SIZE,
                        lineHeight: QC_EDITOR_LINE_HEIGHT,
                        fontFamily: QC_EDITOR_FONT_FAMILY,
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
                      theme={QC_THEME_NAME}
                    />
                    {/* 状态栏：x/y 跟随真实光标（onDidChangeCursorPosition） */}
                    <QcEditorStatusBar line={cursor.line} column={cursor.column} />
                  </div>
                )
              },
              {
                key: 'preview',
                label: <><EyeOutlined /> {t('preview')}</>,
                children: (
                  <Card
                    className="qc-card"
                    title={t('strategy_information')}
                    extra={
                      <div className="flex items-center gap-2">
                        {/* 数据来源 seg（demo edSeg）：枚举原文 mono，悬浮说明沿用原 Tooltip；切换走 handleSourceSegment */}
                        <Tooltip title={dataSource === 'database' ? t('data_from_db') : t('data_from_parse')}>
                          <Segmented
                            value={dataSource}
                            onChange={handleSourceSegment}
                            options={[
                              { value: 'database', label: <span className="qc-mono">database</span> },
                              { value: 'parsed', label: <span className="qc-mono">parse</span> },
                            ]}
                          />
                        </Tooltip>
                        {/* 重新解析（§6.1 mini-btn） */}
                        <button type="button" className="qc-mini-btn" onClick={handleReparseStrategy}>
                          <ReloadOutlined />
                          {t('reparse')}
                        </button>
                      </div>
                    }
                  >
                    <Spin spinning={isParsing} description={t('se_msg_parsing')}>
                      {parseError ? (
                        /* 解析失败：§6.1 danger tint（error 42% 边 + 7% 底），不吃 Tailwind 红阶 */
                        <div
                          className="p-6 text-center rounded-[10px]"
                          style={{
                            border: '1px solid color-mix(in srgb, var(--qc-error) 42%, transparent)',
                            background: 'color-mix(in srgb, var(--qc-error) 7%, transparent)',
                          }}
                        >
                          <CloseCircleOutlined className="text-[28px] mb-4" style={{ color: 'var(--qc-error)' }} />
                          <p className="mb-4" style={{ color: 'var(--qc-error)' }}>{parseError}</p>
                          <Button
                            type="primary"
                            icon={<ReloadOutlined />}
                            onClick={() => parseStrategy(true)}
                          >
                            {t('retry')}
                          </Button>
                        </div>
                      ) : (
                        <>
                          {/* 数据来源提示 */}
                          <div
                            className="mb-4 p-3 rounded text-xs"
                            style={{
                              background: 'var(--qc-surface-muted)',
                              color: 'var(--qc-text-secondary)',
                            }}
                          >
                            {dataSource === 'database' ? (
                              <span>{t('db_data_hint')}</span>
                            ) : (
                              <span>{t('parse_data_hint')}</span>
                            )}
                          </div>

                          {/* 策略档案（demo kvtab）：名称 / 描述 / 版本 点击编辑；创建 / 更新为只读真值 */}
                          <Descriptions size="small" column={1} className="mb-2">
                            <Descriptions.Item label={t('name')}>
                              <div className="min-h-[32px] flex items-center">
                                {isEditingName ? (
                                  <Input
                                    value={tempName}
                                    onChange={handleTempNameChange}
                                    onKeyPress={(e) => e.key === 'Enter' && handleSaveName()}
                                    onBlur={handleSaveName}
                                    onFocus={(e) => e.target.select()}
                                    autoFocus
                                    className="w-full max-w-xs"
                                  />
                                ) : (
                                  <span
                                    onClick={handleStartEditName}
                                    className="cursor-pointer hover:text-[var(--qc-primary)] transition-colors inline-flex items-center gap-1.5"
                                    title={t('click_to_edit')}
                                  >
                                    <span className="qc-mono">{selectedStrategy?.name || '—'}</span>
                                    <EditOutlined style={{ color: 'var(--qc-text-quaternary)', fontSize: 11 }} />
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('version')}>
                              <div className="min-h-[32px] flex items-center">
                                {isEditingVersion ? (
                                  <Input
                                    value={tempVersion}
                                    onChange={handleTempVersionChange}
                                    onPressEnter={handleSaveVersion}
                                    onBlur={handleSaveVersion}
                                    onFocus={(e) => e.target.select()}
                                    autoFocus
                                    className="w-full max-w-[120px]"
                                  />
                                ) : (
                                  <span
                                    onClick={handleStartEditVersion}
                                    className="cursor-pointer hover:text-[var(--qc-primary)] transition-colors inline-flex items-center gap-1.5"
                                    title={t('click_to_edit')}
                                  >
                                    <span className="qc-mono">{dataSource === 'database'
                                      ? (selectedStrategy?.version || '')
                                      : (parsedStrategy?.version || selectedStrategy?.version || '')}</span>
                                    <EditOutlined style={{ color: 'var(--qc-text-quaternary)', fontSize: 11 }} />
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('description')}>
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
                                    className="cursor-pointer hover:text-[var(--qc-primary)] transition-colors whitespace-pre-wrap inline-flex items-start gap-1.5"
                                    title={t('click_to_edit')}
                                  >
                                    {dataSource === 'database'
                                      ? (selectedStrategy?.description || t('no_description'))
                                      : (parsedStrategy?.description || selectedStrategy?.description || t('no_description'))}
                                  </span>
                                )}
                              </div>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('created_at')}>
                              <span className="qc-mono" title={fmtFullTime(selectedStrategy?.created_at)}>
                                {fmtShortTime(selectedStrategy?.created_at)}
                              </span>
                            </Descriptions.Item>
                            <Descriptions.Item label={t('updated_at')}>
                              <span className="qc-mono" title={fmtFullTime(selectedStrategy?.updated_at)}>
                                {fmtShortTime(selectedStrategy?.updated_at)}
                              </span>
                            </Descriptions.Item>
                          </Descriptions>

                          {/* —— 参数配置（demo kvtab 行，§6.2 徽章标注钮标元数据；行内点击进入编辑） —— */}
                          <div className="flex items-center justify-between mt-4 mb-2">
                            <span className="qc-card-sub">{t('parameter_list')}</span>
                            <button
                              type="button"
                              className="qc-mini-btn pri"
                              onClick={handleAddParam}
                              disabled={!selectedStrategy}
                            >
                              + {t('add_parameter')}
                            </button>
                          </div>
                          {(() => {
                            const params = dataSource === 'database'
                              ? (selectedStrategy?.params || [])
                              : (parsedStrategy?.params || selectedStrategy?.params || []);

                            return params.length > 0 ? (
                              <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
                                {params.map((param: Strategy['params'][number], index: number) => {
                                  const editing = editingParamRows.has(index);

                                  if (editing) {
                                    return (
                                      <div key={index} className="flex gap-2 items-start flex-wrap">
                                        <Input
                                          size="small"
                                          value={param.name}
                                          placeholder={t('param_name')}
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
                                            { value: 'select', label: 'select' },
                                            { value: 'Any', label: 'Any' },
                                          ]}
                                        />
                                        {param.type === 'select' && !!param.options?.length ? (
                                          <Select
                                            size="small"
                                            value={param.default === undefined || param.default === null ? undefined : String(param.default)}
                                            placeholder={t('default_value')}
                                            onChange={(v) => handleParamChange(index, 'default', v)}
                                            style={{ width: 140 }}
                                            options={(param.options || []).map((opt: string) => ({ value: opt, label: opt }))}
                                          />
                                        ) : (
                                          <Input
                                            size="small"
                                            value={param.default === undefined || param.default === null ? '' : String(param.default)}
                                            placeholder={t('default_value')}
                                            onChange={(e) => handleParamChange(index, 'default', e.target.value)}
                                            style={{ width: 140 }}
                                          />
                                        )}
                                        <Input
                                          size="small"
                                          value={param.description || ''}
                                          placeholder={t('description')}
                                          onChange={(e) => handleParamChange(index, 'description', e.target.value)}
                                          style={{ flex: 1, minWidth: 160 }}
                                        />
                                        <button
                                          type="button"
                                          className="qc-mini-btn pri qc-icon-only"
                                          aria-label={t('se_action_done')}
                                          title={t('se_action_done')}
                                          onClick={() => toggleParamEdit(index)}
                                        >
                                          <CheckOutlined />
                                        </button>
                                        <button
                                          type="button"
                                          className="qc-mini-btn qc-icon-only danger"
                                          aria-label={t('delete')}
                                          title={t('delete')}
                                          onClick={() => handleRemoveParam(index)}
                                        >
                                          <CloseCircleOutlined />
                                        </button>
                                      </div>
                                    );
                                  }

                                  // 只读态
                                  return (
                                    <div
                                      key={index}
                                      className="flex gap-2 items-center py-1 px-2 rounded transition-colors cursor-pointer group hover:bg-[var(--qc-surface-muted)]"
                                      onClick={() => toggleParamEdit(index)}
                                      title={t('click_to_edit')}
                                    >
                                      <span className="qc-chip quiet qc-mono">{param.name}</span>
                                      <span className="qc-chip info qc-mono">{param.type || 'Any'}</span>
                                      {param.default !== undefined && param.default !== null && param.default !== '' && (
                                        <span className="qc-chip ok qc-mono">= {String(param.default)}</span>
                                      )}
                                      {param.type === 'select' && !!param.options?.length && (
                                        <span className="qc-chip warn qc-mono">∈ {param.options.join(' / ')}</span>
                                      )}
                                      {param.description && (
                                        <span className="text-xs flex-1 truncate" style={{ color: 'var(--qc-text-tertiary)' }}>
                                        {param.description}
                                      </span>
                                      )}
                                      <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity qc-row-actions">
                                        <button
                                          type="button"
                                          className="qc-mini-btn qc-icon-only"
                                          aria-label={t('se_action_edit')}
                                          title={t('se_action_edit')}
                                          onClick={(e) => { e.stopPropagation(); toggleParamEdit(index); }}
                                        >
                                          <EditOutlined />
                                        </button>
                                        <button
                                          type="button"
                                          className="qc-mini-btn qc-icon-only danger"
                                          aria-label={t('delete')}
                                          title={t('delete')}
                                          onClick={(e) => { e.stopPropagation(); handleRemoveParam(index); }}
                                        >
                                          <CloseCircleOutlined />
                                        </button>
                                      </span>
                                    </div>
                                  );
                                })}
                              </Space>
                            ) : (
                              <div
                                className="p-4 text-center text-xs"
                                style={{ color: 'var(--qc-text-quaternary)' }}
                              >
                                {t('no_parameters')}
                              </div>
                            );
                          })()}

                          {/* —— 依赖因子（demo ichip 行：名称 chip + 类型 + 库说明；增删改逻辑保留） —— */}
                          <div className="flex items-center justify-between mt-4 mb-2">
                            <span className="qc-card-sub">{t('factor_list')}</span>
                            <button
                              type="button"
                              className="qc-mini-btn pri"
                              onClick={handleAddFactor}
                              disabled={!selectedStrategy}
                            >
                              + {t('add_factor')}
                            </button>
                          </div>
                          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
                            {(selectedStrategy?.factors && selectedStrategy.factors.length > 0) ? (
                              selectedStrategy.factors.map((factor: NonNullable<Strategy['factors']>[number], index: number) => {
                                const editing = editingFactorRows.has(index);

                                if (editing) {
                                  const catalog = factorCatalog.get(factor.name);
                                  return (
                                    <div key={index} className="flex gap-2 items-start flex-wrap">
                                      <Input
                                        size="small"
                                        value={factor.name}
                                        placeholder={t('factor_name')}
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
                                        placeholder={catalog?.description || t('description')}
                                        onChange={(e) => handleFactorChange(index, 'description', e.target.value)}
                                        style={{ flex: 1, minWidth: 160 }}
                                      />
                                      <button
                                        type="button"
                                        className="qc-mini-btn pri qc-icon-only"
                                        aria-label={t('se_action_done')}
                                        title={t('se_action_done')}
                                        onClick={() => toggleFactorEdit(index)}
                                      >
                                        <CheckOutlined />
                                      </button>
                                      <button
                                        type="button"
                                        className="qc-mini-btn qc-icon-only danger"
                                        aria-label={t('delete')}
                                        title={t('delete')}
                                        onClick={() => handleRemoveFactor(index)}
                                      >
                                        <CloseCircleOutlined />
                                      </button>
                                    </div>
                                  );
                                }

                                // 只读态：名称 chip（点击编辑）+ 类型 chip + 因子库 label/描述
                                const factorCatalogEntry = factorCatalog.get(factor.name);
                                const factorLabel = factorCatalogEntry?.label;
                                const factorDesc = factor.description || factorCatalogEntry?.description || '';
                                const factorParts = [factorLabel, factorDesc].filter(Boolean);
                                return (
                                  <div
                                    key={index}
                                    className="flex gap-2 items-center py-1 px-2 rounded transition-colors cursor-pointer group hover:bg-[var(--qc-surface-muted)]"
                                    onClick={() => toggleFactorEdit(index)}
                                    title={t('click_to_edit')}
                                  >
                                    <span className="qc-chip info qc-mono">{factor.name}</span>
                                    <span className="qc-chip quiet qc-mono">{factor.type || 'factor'}</span>
                                    {factorParts.length > 0 && (
                                      <span className="text-xs flex-1 truncate" style={{ color: 'var(--qc-text-tertiary)' }}>
                                        {factorParts.join(' — ')}
                                      </span>
                                    )}
                                    <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity qc-row-actions">
                                      <button
                                        type="button"
                                        className="qc-mini-btn qc-icon-only"
                                        aria-label={t('se_action_edit')}
                                        title={t('se_action_edit')}
                                        onClick={(e) => { e.stopPropagation(); toggleFactorEdit(index); }}
                                      >
                                        <EditOutlined />
                                      </button>
                                      <button
                                        type="button"
                                        className="qc-mini-btn qc-icon-only danger"
                                        aria-label={t('delete')}
                                        title={t('delete')}
                                        onClick={(e) => { e.stopPropagation(); handleRemoveFactor(index); }}
                                      >
                                        <CloseCircleOutlined />
                                      </button>
                                    </span>
                                  </div>
                                );
                              })
                            ) : (
                              <div
                                className="p-4 text-center text-xs"
                                style={{ color: 'var(--qc-text-quaternary)' }}
                              >
                                {t('no_factors')}
                              </div>
                            )}
                          </Space>
                        </>
                      )}
                    </Spin>
                  </Card>
                )
              },
              {
                key: 'pricePlan',
                label: t('pricePlan.editor_tab_label'),
                children:
                  selectedStrategy && selectedStrategy.strategy_type !== 'rl' ? (
                    <EditorPlanTab strategyName={selectedStrategy.name} />
                  ) : (
                    // RL 策略无 on_bar 计划语义，info 提示占位
                    <Alert type="info" message={t('pricePlan.editor_rl_unsupported')} />
                  ),
              }
            ]}
          />
      </Spin>

      {/* AI生成策略弹窗 - 使用 AIChatModal 组件 */}
      <AIChatModal
        open={aiModalVisible}
        onClose={() => setAiModalVisible(false)}
        title={t('ai_generate_strategy')}
        welcomeTitle={t('ai_welcome')}
        // 快捷建议取代原 welcomeDescription（"例如：……"纯文本），点击直接发送
        promptSuggestions={[
          t('se_prompt_ma_cross'),
          t('se_prompt_rsi'),
          t('se_prompt_bollinger'),
          t('se_prompt_atr'),
        ]}
        inputPlaceholder={t('ai_input_placeholder')}
        // 传入编辑器当前代码，对话框内部据此显示「优化当前代码」模式
        currentCode={code}
        // 策略类型后缀拼接进请求发后端，不在气泡里显示；流式链路收敛到 AIChatModal 内部
        requirementSuffix={
          strategyType === 'rl'
            ? t('se_req_sfx_rl')
            : t('se_req_sfx_rule')
        }
        onAcceptCode={(code: string) => {
          setCode(code);
          appMessage.success(t('ai_adopted'));
          setAiModalVisible(false);
        }}
        onRejectCode={() => {
          appMessage.info(t('ai_rejected'));
        }}
      />

      {/* 模板选择器 —— 新建策略时弹出：先选类型（创建后不再切换）；规则策略可选真实模板，RL 用内置骨架 */}
      {/* 弹窗走 §6.11 qc-modal chrome；页面无 antd Form，qc-form 不适用 */}
      <Modal
        className="qc-modal"
        title={t('create_strategy')}
        open={templatePickerVisible}
        onCancel={() => handlePickTemplate(null)}
        footer={null}
        width={560}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
          <div>
            <div style={{ marginBottom: 8, color: 'var(--qc-text-secondary)' }}>{t('se_sec_type_hint')}</div>
            <Segmented
              block
              value={createStrategyType}
              onChange={(value) => setCreateStrategyType(value as 'rule' | 'rl')}
              options={[
                { value: 'rule', label: t('se_opt_rule_strategy') },
                { value: 'rl', label: t('se_opt_rl_strategy') },
              ]}
            />
          </div>
          {createStrategyType === 'rule' ? (
            <>
              <div style={{ color: 'var(--qc-text-secondary)' }}>
                {t('se_sec_template_hint')}
              </div>
              <Select
                style={{ width: '100%' }}
                placeholder={templatePickerLoading ? t('loading') : t('se_ph_pick_template')}
                loading={templatePickerLoading}
                disabled={templatePickerLoading}
                options={templates.map((t) => ({
                  value: t.id,
                  label: (
                    <span>
                      <strong>{t.name}</strong>
                      <span style={{ color: 'var(--qc-text-tertiary)', marginLeft: 8 }}>
                        [{t.category}]
                      </span>
                      {t.tags?.length ? (
                        <span style={{ color: 'var(--qc-text-quaternary)', marginLeft: 8 }}>· {t.tags.join('/')}</span>
                      ) : null}
                    </span>
                  ),
                }))}
                onChange={(id) => id && handlePickTemplate(id)}
                // 下拉底部常驻本地上传入口：与 BacktestConfig「下拉底部创建策略」同一交互语言，
                // 避免弹窗里上传大块与 Select 并列造成双主路径误导
                popupRender={(menu) => (
                  <>
                    {menu}
                    {/* strategy-template-upload-row：global.css 里把 Upload 中间层撑满整行，保证整行可点击 */}
                    <div className="strategy-template-upload-row" style={{ padding: 4, borderTop: '1px solid var(--qc-border-subtle)' }}>
                      <Upload {...uploadProps}>
                        {/* mousedown 不 preventDefault 会让 Select 收起、click 丢失（antd 官方要求） */}
                        <Button
                          type="text"
                          block
                          size="small"
                          icon={<UploadOutlined />}
                          onMouseDown={(e) => e.preventDefault()}
                        >
                          {t('se_action_upload_py')}
                        </Button>
                      </Upload>
                    </div>
                  </>
                )}
              />
            </>
          ) : (
            <div style={{ color: 'var(--qc-text-secondary)' }}>
              {t('se_sec_rl_skeleton')}
              {' '}{t('se_sec_rl_upload_prefix')}<Upload {...uploadProps}><a>{t('se_action_upload_py_strategy')}</a></Upload>{t('se_sec_auto_detect')}
            </div>
          )}
          <div style={{ textAlign: 'right' }}>
            <button
              type="button"
              className="qc-mini-btn"
              onClick={() => handlePickTemplate(null)}
            >
              {createStrategyType === 'rl' ? t('se_action_create_rl') : t('se_action_skip_blank')}
            </button>
          </div>
        </Space>
      </Modal>
      <Drawer
        title={t('sm_ver_editor_title')}
        open={versionsDrawerOpen}
        onClose={() => setVersionsDrawerOpen(false)}
        size={920}
        destroyOnHidden
      >
        {selectedStrategy && (
          <StrategyVersionPanel
            strategyName={selectedStrategy.name}
            variant="drawer"
            className="sm-ver-drawer"
            dirty={code !== savedCode}
            onLoadToEditor={(snapshotCode, version) => {
              // 只写缓冲区：savedCode 不动，页头「未保存」与保存按钮高亮由 dirty 驱动
              setCode(snapshotCode);
              setVersionsDrawerOpen(false);
              const label = version.version ? `v${version.version}` : version.code_hash.slice(0, 8);
              appMessage.info(t('sm_ver_loaded_to_editor', { label }));
            }}
          />
        )}
      </Drawer>
    </PageContainer>
  );
};

export default StrategyEditor;
