import { QUANT_COLORS } from '@/utils/colors';
/**
 * 统一数据管理页面 - 多自选组管理优化版
 * 整合数据池、数据采集、数据质量三个核心功能模块
 * 支持多自选组管理（创建、命名、编辑、删除）
 */
import { useState, useEffect, useMemo, useRef } from 'react';
// 车道 T 设计收口：色值一律 var(--qc-*) / color-mix(in srgb, var(--qc-*) N%, transparent)。
// 保留例外：
// - 布局尺寸（width/maxHeight/position 等非间距/颜色值）不在本车道范围；
// - 自选组颜色选择器候选值（'#722ed1' 等）是**会写库的离散标识色数据**（pin 色 / 图例用），
//   非 UI 主题色 —— 这类值属于业务数据，换成主题变量会在切主题时改变已存数据；
// - 原 '#1890ff' initialValue 已对齐为 QUANT_COLORS.info（= 蓝色选项）；“青色”选项与“蓝色”同值属既有数据问题，未在本轮修改。
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import {
  Card,
  Tabs,
  Button,
  Input,
  Select,
  Space,
  Form,
  DatePicker,
  Switch,
  Divider,
  Typography,
  Row,
  Col,
  Menu,
  Dropdown,
  Modal,
  Tooltip,
  Popconfirm,
  Drawer,
  Segmented,
  Transfer,
  Spin,
  Pagination,
  Alert,
  App,
  Descriptions,
  InputNumber,
  Flex,
} from 'antd';
import {
  StarOutlined,
  StarFilled,
  DownloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  CloudDownloadOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOutlined,
  FolderOpenOutlined,
  SettingOutlined,
  ImportOutlined,
  FileSearchOutlined,
  SearchOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { MenuProps, TableProps } from 'antd';

import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import PageToolbar from '@/components/ui/PageToolbar';
import { dataApi } from '@/api/dataApi';
import type { DataPoolRecord, CryptoSymbol, TaskDetailItem, KlineQualityReport } from '@/api/dataApi';
import { archiveApi } from '@/api/archiveApi';
import { derivApi } from '@/api/derivApi';
import { wsService } from '@/services/websocketService';
import { useConfigStore } from '@/store';
import { useGlobalPageSize } from '@/hooks/useGlobalPageSize';
import { useViewType } from '@/hooks/useViewType';
import { PAGE_SIZE_OPTIONS } from '@/constants/pagination';
import type {
  Task,
  TaskStatus,
  ArchiveKind,
  MarketType,
  ArchiveMeta,
  ArchiveRow,
  DerivKind,
  DataKind,
} from '@/types/data';
import {
  ARCHIVE_KINDS,
  KLINE_ARCHIVE_KINDS,
  ARCHIVE_MARKETS,
  ARCHIVE_INTERVALS,
  DERIV_KINDS,
  DATA_KIND_LABEL,
  INTERVAL_REQUIRED_KINDS,
  FUTURES_ONLY_KINDS,
} from '@/types/data';
import { setPageTitle } from '@/utils/pageTitle';

import ArchiveWatermarkStrip from './ArchiveWatermarkStrip';

const { Text } = Typography;
const { RangePicker } = DatePicker;

// 语义色在 JS 侧统一用 var(--qc-*) 字符串：跟主题运行时切换，不再依赖 QUANT_COLORS 静态快照
// （QUANT_COLORS 仅保留给会写库的离散标识色：自选组候选色）。

// 自选列表「紫色」标识：会写库的品种离散标识色，与品牌语义无关，
// 故不映射状态/品牌 token；候选后续并入 theme 的离散身份调色板（同 chartSeries 定位）。
const WATCHLIST_COLOR_PURPLE = '#722ed1';

/**
 * 归档预览行 + 视图层注入的序号键。
 * __rk 仅用于 antd v6 的 rowKey（其函数已弃用 index 参数），是前端渲染期注入，
 * 不属于后端数据契约，因此不写进 types/data.ts 的 ArchiveRow。
 */
interface KeyedArchiveRow extends ArchiveRow {
  __rk: number;
}

// 系统配置
const SYSTEM_CONFIG = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot',
};

// 自选组接口
interface FavoriteGroup {
  id: number;
  name: string;
  description?: string;
  color: string;
  symbolIds: string[];
  isDefault?: boolean;
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
}

// 货币对数据接口
interface SymbolData {
  id: string;
  symbol: string;
  baseAsset: string;
  quoteAsset: string;
  price: number | null;
  priceChange24h: number | null;
  priceChangePercent24h: number | null;
  volume24h: number | null;
  high24h: number | null;
  low24h: number | null;
  hasData: boolean;
  lastUpdateTime?: string;
  dataQuality?: 'good' | 'warning' | 'bad' | 'unknown';
  availableIntervals: string[];
  autoUpdate: boolean;
  marketCap?: number;
  rank?: number;
}

// 市场行情点（/data/crypto/market-data 返回的单条行情）
interface MarketDataPoint {
  symbol?: string;
  price?: number;
  price_change_24h?: number;
  price_change_percent_24h?: number;
  volume_24h?: number;
  high_24h?: number;
  low_24h?: number;
  [key: string]: unknown;
}

// 排序字段
 type SortField = 'symbol' | 'price' | 'change' | 'volume' | 'marketCap' | 'rank';
 type SortOrder = 'asc' | 'desc';

/**
 * 统一数据管理页面组件
 */
const DataManagementPage = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = App.useApp();

  // 从路由状态恢复分页/筛选/视图等页面状态
  // note: viewType / pageSize 不在此恢复——二者已全局化，跟随系统配置（展示类型/每页条数）
  const restoredState = location.state as
    | {
        pageState?: {
          activeTab?: string;
          activeGroupId?: number;
          searchText?: string;
          quoteFilter?: string;
          sortField?: SortField;
          sortOrder?: SortOrder;
          selectedSymbols?: string[];
          currentPage?: number;
        };
      }
    | null;

  // 从 URL 参数读取 Tab 状态，优先从恢复的状态读取
  const tabFromUrl = searchParams.get('tab');
  // 白名单须与下方 Tabs items 的 key 对齐；'tasks' 是旧键名，归档前保留会
  // 让 ?tab=collection 这类直达链接被误判非法而回落到货币对 tab
  const validTab = ['symbols', 'collection', 'quality', 'archive'].includes(tabFromUrl ?? '')
    ? (tabFromUrl as string)
    : 'symbols';
  const [activeTab, setActiveTab] = useState(restoredState?.pageState?.activeTab || validTab);

  // ==================== 自选组管理状态 ====================
  const [favoriteGroups, setFavoriteGroups] = useState<FavoriteGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<number>(restoredState?.pageState?.activeGroupId || 0);
  const [isGroupDrawerOpen, setIsGroupDrawerOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<FavoriteGroup | null>(null);
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [groupForm] = Form.useForm();

  // ==================== 批量添加自选状态 ====================
  const [isBatchAddModalOpen, setIsBatchAddModalOpen] = useState(false);
  const [batchAddTargetGroup, setBatchAddTargetGroup] = useState<FavoriteGroup | null>(null);
  const [transferTargetKeys, setTransferTargetKeys] = useState<string[]>([]);
  const [transferSelectedKeys, setTransferSelectedKeys] = useState<string[]>([]);

  // ==================== 货币对列表状态 ====================
  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [searchText, setSearchText] = useState(restoredState?.pageState?.searchText || '');
  const [quoteFilter, setQuoteFilter] = useState<string>(restoredState?.pageState?.quoteFilter || 'all');
  // 视图类型：跟随系统设置「默认展示类型」，页面不提供切换
  const viewType = useViewType();
  const [sortField, setSortField] = useState<SortField>(restoredState?.pageState?.sortField || 'rank');
  const [sortOrder, setSortOrder] = useState<SortOrder>(restoredState?.pageState?.sortOrder || 'asc');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(restoredState?.pageState?.selectedSymbols || []);

  // 市场数据加载状态
  const [marketDataLoading, setMarketDataLoading] = useState<Record<string, boolean>>({});

  // 分页状态：currentPage 仍从路由状态恢复；pageSize 跟随全局配置（条数切换器即全站开关）
  const [currentPage, setCurrentPage] = useState(restoredState?.pageState?.currentPage || 1);
  const [pageSize, setPageSize] = useGlobalPageSize();

  // 全局条数变化（设置页/其他页面改动）实时同步并回到第一页，避免越界
  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize]);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('data_management'));
  }, [t]);

  // 页面加载时输出全局配置（用于调试）
  useEffect(() => {
    const configState = useConfigStore.getState();
    console.log('[DataManagement] page loaded, global config state:', configState);
    console.log('[DataManagement] global config details:', {
      config: configState.config,
      isLoading: configState.isLoading,
      error: configState.error,
    });
    if (configState.config) {
      console.log('[DataManagement] system config keys:', Object.keys(configState.config));
      Object.entries(configState.config).forEach(([key, value]) => {
        console.log(`[DataManagement] config ${key}:`, value);
      });
    }
  }, []);

  // 是否已经获取过市场数据的标志
  const [hasFetchedMarketData, setHasFetchedMarketData] = useState(false);

  // ==================== 数据质量状态 ====================
  const [selectedSymbolForQuality, setSelectedSymbolForQuality] = useState<string>('');
  const [selectedIntervalForQuality, setSelectedIntervalForQuality] = useState<string>('');
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityDetail, setQualityDetail] = useState<KlineQualityReport | null>(null);

  // ==================== 数据清理状态 ====================
  const [cleanForm] = Form.useForm();
  const [cleanLoading, setCleanLoading] = useState(false);
  const [cleanResult, setCleanResult] = useState<{
    deleted_count?: number;
    symbol?: string;
    interval?: string;
    clean_type?: string;
    total_before?: number;
  } | null>(null);
  const [isCleanModalOpen, setIsCleanModalOpen] = useState(false);

  // ==================== 数据采集状态 ====================
  const [collectionForm] = Form.useForm();
  // 监听采集表单中的 dataType 变化，用于动态控制 intervals / market 字段
  const collectionDataType = Form.useWatch('dataType', collectionForm) ?? 'kline';
  const [collectionTasks, setCollectionTasks] = useState<Task[]>([]);
  // 服务端分页状态（每页 20 条，与后端 page_size 对齐；页码切换重拉）
  const [tasksPage, setTasksPage] = useState(1);
  const [tasksPageSize] = useState(20);
  const [tasksTotal, setTasksTotal] = useState(0);
  const [tasksDeletingId, setTasksDeletingId] = useState<string | null>(null);
  // 任务表搜索：对已加载行做前端过滤（过滤后页码归 1，§6.6）
  const [taskSearchText, setTaskSearchText] = useState('');
  const [taskSearchPage, setTaskSearchPage] = useState(1);
  // 展开行的子任务明细缓存：key = task_id（当前任务走 WS 的 taskProgressList，不落这里）
  const [taskDetailsMap, setTaskDetailsMap] = useState<Record<string, TaskDetailItem[]>>({});
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  // 当前任务的请求参数（数据类型/市场等），当前任务卡用它在任务列表刷新前就显示正确标签
  const [currentTaskParams, setCurrentTaskParams] = useState<Record<string, unknown>>({});
  const [taskStatus, setTaskStatus] = useState<TaskStatus>('pending');
  const [taskProgress, setTaskProgress] = useState<number>(0);
  // 任务进度列表 - 支持多时间周期多货币对
  const [taskProgressList, setTaskProgressList] = useState<TaskDetailItem[]>([]);
  // 展开/收起状态
  const [isProgressExpanded, setIsProgressExpanded] = useState<boolean>(false);
  // 任务列表加载状态 & 状态筛选
  const [taskListLoading, setTaskListLoading] = useState(false);
  const [taskStatusFilter, setTaskStatusFilter] = useState<string>('all');
  // 使用 ref 存储最新的 currentTaskId，避免 WebSocket 回调中的闭包问题
  const currentTaskIdRef = useRef<string>('');
  useEffect(() => {
    currentTaskIdRef.current = currentTaskId;
  }, [currentTaskId]);

  // 行情请求的 AbortController：发起新请求前取消旧请求，避免旧请求占用连接、拖慢页面加载
  const marketDataAbortRef = useRef<AbortController | null>(null);

  // ==================== 归档浏览 Tab 状态 ====================
  // 左侧树形导航：kind 7 种 → market 3 种 → symbols
  // ==================== 归档 / 衍生 浏览状态 ====================

  // 'archive' 对应 7 种归档数据；'deriv' 对应 fundingRate/openInterest
  type ArchiveBrowserCategory = 'archive' | 'deriv';
  const [archiveBrowserCategory, setArchiveBrowserCategory] = useState<ArchiveBrowserCategory>('archive');
  const [archiveKind, setArchiveKind] = useState<ArchiveKind | DerivKind>('aggTrades');
  const [archiveMarket, setArchiveMarket] = useState<MarketType>('spot');
  const [archiveSymbol, setArchiveSymbol] = useState<string>('');
  // 树形展开状态（kind 节点）
  const [archiveExpandedKinds, setArchiveExpandedKinds] = useState<(ArchiveKind | DerivKind)[]>(['aggTrades']);
  // 当前 (kind, market) 已加载的 symbols 列表缓存：key = kind__market
  const [archiveSymbolsMap, setArchiveSymbolsMap] = useState<Record<string, string[]>>({});
  // 当前 (kind, market) 是否正在加载 symbols
  const [archiveSymbolsLoading, setArchiveSymbolsLoading] = useState(false);
  // 时间范围（毫秒元组；默认近 7 天）
  const [archiveTimeRange, setArchiveTimeRange] = useState<[number, number]>(() => {
    const end = Date.now();
    return [end - 7 * 86400_000, end];
  });
  // 选中 symbol 的元数据（_meta.json）
  const [archiveMeta, setArchiveMeta] = useState<ArchiveMeta | null>(null);
  // 表格数据 + 分页
  const [archiveRows, setArchiveRows] = useState<ArchiveRow[]>([]);
  const [archiveTotal, setArchiveTotal] = useState<number>(0);
  const [archiveTruncated, setArchiveTruncated] = useState<boolean>(false);
  const [archiveQueryLoading, setArchiveQueryLoading] = useState(false);
  const [archivePage, setArchivePage] = useState<number>(1);
  const [archivePageSize, setArchivePageSize] = useState<number>(200);
  // K 线类需要 interval 字段
  const [archiveInterval, setArchiveInterval] = useState<string>('1h');
  // 删除 loading
  const [archiveDeleting, setArchiveDeleting] = useState(false);
  // 左侧树 symbol 搜索
  const [archiveSymbolSearch, setArchiveSymbolSearch] = useState<string>('');

  // 当前激活的自选组
  const activeGroup = useMemo(() => 
    favoriteGroups.find(g => g.id === activeGroupId),
    [favoriteGroups, activeGroupId]
  );

  // 过滤和排序后的货币对
  const filteredSymbols = useMemo(() => {
    let result = [...symbols];

    // 搜索过滤
    if (searchText) {
      const lowerSearch = searchText.toLowerCase();
      result = result.filter(
        (s) =>
          s.symbol.toLowerCase().includes(lowerSearch) ||
          s.baseAsset.toLowerCase().includes(lowerSearch)
      );
    }

    // 计价货币过滤
    if (quoteFilter !== 'all') {
      result = result.filter((s) => s.quoteAsset === quoteFilter);
    }

    // 自选组过滤
    if (activeGroup) {
      result = result.filter((s) => activeGroup.symbolIds.includes(s.symbol));
    }

    // 排序
    result.sort((a, b) => {
      let aVal: number | string = '';
      let bVal: number | string = '';
      
      switch (sortField) {
        case 'symbol':
          aVal = a.symbol;
          bVal = b.symbol;
          break;
        case 'price':
          aVal = a.price || 0;
          bVal = b.price || 0;
          break;
        case 'change':
          aVal = a.priceChangePercent24h || 0;
          bVal = b.priceChangePercent24h || 0;
          break;
        case 'volume':
          aVal = a.volume24h || 0;
          bVal = b.volume24h || 0;
          break;
        case 'marketCap':
          aVal = a.marketCap || 0;
          bVal = b.marketCap || 0;
          break;
        case 'rank':
          aVal = a.rank || 999;
          bVal = b.rank || 999;
          break;
      }

      if (typeof aVal === 'string') {
        return sortOrder === 'asc' 
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return sortOrder === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return result;
  }, [symbols, searchText, quoteFilter, activeGroup, sortField, sortOrder]);

  // 初始化加载
  useEffect(() => {
    fetchSymbols();
    fetchFavoriteGroups();
    fetchCollectionTasks();
    // 组件卸载时取消未完成的行情请求
    return () => {
      marketDataAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []);



  // 当货币对列表加载完成或分页变化时，获取当前页的市场数据
  useEffect(() => {
    // 避免在加载中或没有数据时调用
    if (symbolLoading || filteredSymbols.length === 0) return;

    // 如果已经获取过市场数据，且只是分页变化，直接返回（由分页 onChange 处理）
    if (hasFetchedMarketData) return;

    // 使用防抖，延迟 300ms 执行
    const timer = setTimeout(() => {
      fetchCurrentPageMarketData(currentPage, pageSize);
      setHasFetchedMarketData(true);
    }, 300);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [symbolLoading, filteredSymbols.length, hasFetchedMarketData]);

  // 获取自选组列表
  const fetchFavoriteGroups = async () => {
    try {
      const response = await dataApi.getDataPools({ type: 'crypto' });
      console.log('getDataPools response:', response);
      
      // 处理可能的不同返回格式
      let pools: DataPoolRecord[] = [];
      if (Array.isArray(response)) {
        pools = response;
      } else if (response && Array.isArray(response.data)) {
        pools = response.data;
      } else if (response && typeof response === 'object') {
        // 尝试从各种可能的字段获取数据
        pools = response.data ?? response.pools ?? response.items ?? [];
      }
      
      console.log('pools:', pools);
      
      if (pools.length > 0) {
        // 转换后端数据格式为前端格式
        const groups: FavoriteGroup[] = await Promise.all(
          pools.map(async (pool) => {
            // 获取每个组的资产
            let symbolIds: string[] = [];
            try {
              const assetsResponse = await dataApi.getDataPoolAssets(Number(pool.id));
              console.log(`assets for pool ${pool.id}:`, assetsResponse);
              if (Array.isArray(assetsResponse)) {
                symbolIds = assetsResponse;
              } else if (assetsResponse && Array.isArray(assetsResponse.assets)) {
                symbolIds = assetsResponse.assets;
              }
            } catch (e) {
              console.error(`Failed to fetch assets for pool ${pool.id}:`, e);
            }
            
            return {
              id: Number(pool.id),
              name: pool.name,
              description: pool.description,
              color: pool.color || QUANT_COLORS.info,
              symbolIds: symbolIds,
              isDefault: pool.is_default || false,
              sortOrder: Number(pool.id),
              createdAt: pool.created_at || '',
              updatedAt: pool.updated_at || '',
            };
          })
        );
        
        console.log('groups:', groups);
        
        setFavoriteGroups(groups);
      } else {
        setFavoriteGroups([]);
      }
    } catch (error) {
      message.error(t('dm_msg_fetch_groups_failed'));
      console.error('Failed to fetch watchlist groups:', error);
      setFavoriteGroups([]);
    }
  };

  // 更新自选组资产数量（本地乐观更新）
  const updateGroupAssetCount = (groupId: number, delta: number) => {
    setFavoriteGroups(prev => prev.map(group => {
      if (group.id === groupId) {
        const newCount = group.symbolIds.length + delta;
        return {
          ...group,
          symbolIds: newCount > 0 
            ? [...group.symbolIds, ''] // 临时占位，实际数据会在刷新后更新
            : [],
        };
      }
      return group;
    }));
  };

  // WebSocket 消息监听（连接在全局 App.tsx 中管理）
  useEffect(() => {
    console.log('[DataManagement] WebSocket message listener registered');

    const handleTaskProgress = (data: unknown) => {
      // WebSocket 消息结构未在 wsService 类型中定义，这里按消费字段收窄
      const msg = data as { task_id?: string; progress?: TaskDetailItem };
      console.log('[DataManagement] task progress received:', msg, 'current task id:', currentTaskIdRef.current);
      // 使用 ref 获取最新的 currentTaskId，避免闭包问题
      if (msg.task_id === currentTaskIdRef.current) {
        const progress = msg.progress;
        console.log('[DataManagement] updating task progress:', progress?.percentage, progress?.task_key);

        // 更新任务进度列表 - 按 task_key 去重
        if (progress?.task_key) {
          setTaskProgressList(prev => {
            const newList = [...prev];
            const existingIndex = newList.findIndex(t => t.task_key === progress.task_key);
            if (existingIndex >= 0) {
              // 更新已有任务
              newList[existingIndex] = { ...progress };
            } else {
              // 添加新任务
              newList.push({ ...progress });
            }

            // 计算总体进度 = 所有子任务进度之和 / 子任务数量
            const totalProgress = newList.reduce((sum, t) => sum + (t.percentage || 0), 0);
            const overallPercentage = newList.length > 0 ? totalProgress / newList.length : 0;
            setTaskProgress(overallPercentage);

            return newList;
          });
        }
      } else {
        console.log('[DataManagement] task id mismatch, ignored:', msg.task_id, '!==', currentTaskIdRef.current);
      }
    };

    const handleTaskStatus = (data: unknown) => {
      const msg = data as { task_id?: string; status?: TaskStatus };
      console.log('[DataManagement] task status received:', msg);
      // 使用 ref 获取最新的 currentTaskId，避免闭包问题
      if (msg.task_id === currentTaskIdRef.current) {
        setTaskStatus(msg.status ?? 'pending');
        if (msg.status === 'completed' || msg.status === 'failed') {
          fetchCollectionTasks();
        }
      }
    };

    wsService.on('task:progress', handleTaskProgress);
    wsService.on('task:status', handleTaskStatus);

    return () => {
      wsService.off('task:progress', handleTaskProgress);
      wsService.off('task:status', handleTaskStatus);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []); // 移除 currentTaskId 依赖，避免重复注册

  // 获取货币对列表（第一步）
  const fetchSymbols = async () => {
    try {
      setSymbolLoading(true);
      // 重置市场数据获取标志，确保刷新后会重新获取市场数据
      setHasFetchedMarketData(false);
      
      const response = await dataApi.getCryptoSymbols({
        exchange: SYSTEM_CONFIG.exchange,
        limit: 2000,
        offset: 0,
      });

      // 处理后端返回的 ApiResponse 格式 { code, message, data: { total, symbols } }
      const responseData = (response?.data || response) as { symbols?: CryptoSymbol[]; items?: CryptoSymbol[] };
      // 后端返回的是 symbols 字段，不是 items
      const symbolList = responseData?.symbols || responseData?.items;

      if (symbolList && Array.isArray(symbolList)) {
        const symbolsData: SymbolData[] = symbolList.map((item, index) => ({
          id: String(item.id || index),
          symbol: item.symbol,
          baseAsset: item.base ?? '',
          quoteAsset: item.quote ?? '',
          price: null, // 初始为空，显示加载动画
          priceChange24h: null,
          priceChangePercent24h: null,
          volume24h: null,
          high24h: null,
          low24h: null,
          hasData: false,
          dataQuality: 'unknown',
          availableIntervals: [],
          autoUpdate: false,
          rank: index + 1,
        }));
        setSymbols(symbolsData);

        // 重置分页状态
        setCurrentPage(1);

        // 不再自动获取所有市场数据，改为只获取当前页数据
        // 在 symbolLoading 变为 false 后，useEffect 会触发获取
      } else {
        setSymbols([]);
      }
    } catch (error) {
      message.error(t('dm_msg_fetch_symbols_failed'));
      console.error('Failed to fetch symbol list:', error);
      setSymbols([]);
    } finally {
      setSymbolLoading(false);
    }
  };

  // 获取市场数据（第二步）
  const fetchMarketData = async (symbolList: string[]) => {
    if (!symbolList || symbolList.length === 0) return;

    // 取消上一次未完成的行情请求，避免旧请求占用连接、拖慢后续请求
    marketDataAbortRef.current?.abort();
    const controller = new AbortController();
    marketDataAbortRef.current = controller;

    // 设置所有symbol为加载中
    const loadingMap: Record<string, boolean> = {};
    symbolList.forEach(symbol => {
      loadingMap[symbol] = true;
    });
    setMarketDataLoading(loadingMap);

    try {
      // 分批获取，每批最多100个
      const batchSize = 100;
      const newMarketDataMap: Record<string, MarketDataPoint> = {};

      for (let i = 0; i < symbolList.length; i += batchSize) {
        const batch = symbolList.slice(i, i + batchSize);
        const response = await dataApi.getMarketData({
          symbols: batch,
          exchange: SYSTEM_CONFIG.exchange,
        }, controller.signal);

        // 处理后端返回的 ApiResponse 格式 { code, message, data: [...] }
        const rawData = Array.isArray(response) ? response : response?.data;
        const marketDataList = Array.isArray(rawData) ? rawData : [];
        if (marketDataList.length > 0) {
          marketDataList.forEach((data) => {
            newMarketDataMap[String(data.symbol)] = data as MarketDataPoint;
          });
        }
      }

      // 更新symbols数据
      setSymbols(prev => prev.map(symbol => {
        const marketData = newMarketDataMap[symbol.symbol];
        if (marketData) {
          return {
            ...symbol,
            price: marketData.price ?? null,
            priceChange24h: marketData.price_change_24h ?? null,
            priceChangePercent24h: marketData.price_change_percent_24h ?? null,
            volume24h: marketData.volume_24h ?? null,
            high24h: marketData.high_24h ?? null,
            low24h: marketData.low_24h ?? null,
            hasData: true,
            dataQuality: 'good',
          };
        }
        return symbol;
      }));
    } catch (error) {
      // 主动取消不算错误，静默处理
      if (controller.signal.aborted) return;
      message.error(t('dm_msg_fetch_market_failed'));
      console.error('Failed to fetch market data:', error);
    } finally {
      // 仅当自己仍是最新请求时才清理状态，避免误清后发起请求的加载态
      if (marketDataAbortRef.current === controller) {
        marketDataAbortRef.current = null;
        setMarketDataLoading({});
      }
    }
  };

  // 获取当前页的市场数据
  const fetchCurrentPageMarketData = async (page: number, size: number) => {
    if (!filteredSymbols || filteredSymbols.length === 0) return;

    // 计算当前页的货币对
    const startIndex = (page - 1) * size;
    const endIndex = startIndex + size;
    const currentPageSymbols = filteredSymbols.slice(startIndex, endIndex);

    // 只获取当前页的市场数据
    await fetchMarketData(currentPageSymbols.map(s => s.symbol));
  };

  // 处理分页变化（条数变化经 hook 写回全局配置，全站生效）
  const handlePageChange = (page: number, size?: number) => {
    setCurrentPage(page);
    if (size) setPageSize(size);
    // 重置标志位，允许获取新页数据
    setHasFetchedMarketData(false);
  };

  // ==================== 自选组管理方法 ====================
  
  // 创建自选组
  const handleCreateGroup = () => {
    setEditingGroup(null);
    groupForm.resetFields();
    setIsGroupModalOpen(true);
  };

  // 编辑自选组
  const handleEditGroup = (group: FavoriteGroup, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingGroup(group);
    groupForm.setFieldsValue({
      name: group.name,
      description: group.description,
      color: group.color,
    });
    setIsGroupModalOpen(true);
  };

  // 删除自选组
  const handleDeleteGroup = async (groupId: number, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const group = favoriteGroups.find(g => g.id === groupId);
    if (group?.isDefault) {
      message.warning(t('dm_msg_default_group_cannot_delete'));
      return;
    }
    try {
      // 响应拦截器已解包：非 0 code 会走 reject 抛错，走到这里即成功
      await dataApi.deleteDataPool(groupId);
      message.success(t('dm_msg_group_deleted'));
      await fetchFavoriteGroups(); // 刷新列表
      if (activeGroupId === groupId) {
        // 删除当前激活的组时，切换到第一个组
        const remainingGroups = favoriteGroups.filter(g => g.id !== groupId);
        if (remainingGroups.length > 0) {
          setActiveGroupId(remainingGroups[0].id);
        }
      }
    } catch (error) {
      message.error(t('dm_msg_group_delete_failed'));
      console.error('Failed to delete watchlist group:', error);
    }
  };

  // 保存自选组
  const handleSaveGroup = async () => {
    try {
      const values = await groupForm.validateFields();
      
      if (editingGroup) {
        // 更新现有组
        const response = await dataApi.updateDataPool(editingGroup.id, {
          name: values.name,
          description: values.description,
          color: values.color,
        });
        if (response.code === 0) {
          message.success(t('dm_msg_group_updated'));
          await fetchFavoriteGroups(); // 刷新列表
        } else {
          message.error(response.message || t('dm_msg_update_failed'));
        }
      } else {
        // 创建新组
        const response = await dataApi.createDataPool({
          name: values.name,
          type: 'crypto',
          description: values.description,
          color: values.color || QUANT_COLORS.info,
          tags: [],
        });
        // 拦截器只返回 data 字段，判断 pool_id 是否存在表示成功
        if (response && response.pool_id) {
          message.success(t('dm_msg_group_created'));
          await fetchFavoriteGroups(); // 刷新列表
        } else {
          message.error(t('dm_msg_create_failed'));
        }
      }

      setIsGroupModalOpen(false);
    } catch (error) {
      console.error('Failed to save watchlist group:', error);
      message.error(t('dm_msg_save_failed'));
    }
  };

  // 添加货币对到自选组
  const handleAddToGroup = async (symbolId: string, groupId: number) => {
    try {
      // 获取当前组的资产列表
      const group = favoriteGroups.find(g => g.id === groupId);
      if (!group) return;

      // 合并新旧货币对，去重
      const existingAssets = group.symbolIds || [];
      const newAssets = [...new Set([...existingAssets, symbolId])];

      // 发送完整的货币对列表到后端（全量更新）
      await dataApi.addDataPoolAssets(groupId, {
        assets: newAssets,
        asset_type: 'crypto',
      });
      message.success(t('dm_msg_added_to_group'));
      // 更新本地自选组数据，不等待刷新
      updateGroupAssetCount(groupId, 1);
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error(t('dm_msg_add_to_group_failed'));
      console.error('Failed to add to watchlist group:', error);
    }
  };

  // 从自选组移除
  const handleRemoveFromGroup = async (symbolId: string, groupId: number) => {
    try {
      // 获取当前组的资产列表
      const group = favoriteGroups.find(g => g.id === groupId);
      if (!group) return;

      // 过滤掉要移除的资产
      const newAssets = group.symbolIds.filter(id => id !== symbolId);

      // 使用addDataPoolAssets同步整个资产列表（后端会替换原有资产）
      // API拦截器在code===0时直接返回data，所以这里不需要检查code
      await dataApi.addDataPoolAssets(groupId, {
        assets: newAssets,
        asset_type: 'crypto',
      });
      message.success(t('dm_msg_removed_from_group'));
      // 更新本地自选组数据，不等待刷新
      updateGroupAssetCount(groupId, -1);
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error(t('dm_msg_remove_from_group_failed'));
      console.error('Failed to remove from watchlist group:', error);
    }
  };

  // ==================== 批量添加自选方法 ====================

  // 打开批量添加弹窗
  const handleOpenBatchAdd = (group: FavoriteGroup, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setBatchAddTargetGroup(group);
    setTransferTargetKeys([...group.symbolIds]);
    setTransferSelectedKeys([]);
    setIsBatchAddModalOpen(true);
  };

  // 关闭批量添加弹窗
  const handleCloseBatchAdd = () => {
    setIsBatchAddModalOpen(false);
    setBatchAddTargetGroup(null);
    setTransferTargetKeys([]);
    setTransferSelectedKeys([]);
  };

  // 确认批量添加
  const handleConfirmBatchAdd = async () => {
    if (!batchAddTargetGroup) return;

    try {
      // API拦截器在code===0时直接返回data，所以这里不需要检查code
      await dataApi.addDataPoolAssets(batchAddTargetGroup.id, {
        assets: transferTargetKeys,
        asset_type: 'crypto',
      });

      const addedCount = transferTargetKeys.filter(key => !batchAddTargetGroup.symbolIds.includes(key)).length;
      const removedCount = batchAddTargetGroup.symbolIds.filter(key => !transferTargetKeys.includes(key)).length;

      if (addedCount > 0 && removedCount > 0) {
        message.success(t('dm_msg_batch_mixed', { added: addedCount, removed: removedCount }));
      } else if (addedCount > 0) {
        message.success(t('dm_msg_batch_added', { n: addedCount }));
      } else if (removedCount > 0) {
        message.success(t('dm_msg_batch_removed', { n: removedCount }));
      } else {
        message.info(t('dm_msg_no_changes'));
      }

      // 更新本地自选组数据，不等待刷新
      const delta = addedCount - removedCount;
      if (delta !== 0) {
        updateGroupAssetCount(batchAddTargetGroup.id, delta);
      }
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error(t('dm_msg_batch_add_failed'));
      console.error('Failed to batch-add symbols:', error);
    }

    handleCloseBatchAdd();
  };

  // 穿梭框数据变化
  const handleTransferChange = (nextTargetKeys: React.Key[]) => {
    setTransferTargetKeys(nextTargetKeys.map(key => String(key)));
  };

  // 穿梭框选择变化
  const handleTransferSelectChange = (sourceSelectedKeys: React.Key[], targetSelectedKeys: React.Key[]) => {
    setTransferSelectedKeys([...sourceSelectedKeys, ...targetSelectedKeys].map(key => String(key)));
  };

  // ==================== 其他方法 ====================

  // 拉取采集任务列表（服务端分页）
  // mode: 'reset'  —— 覆盖当前页（筛选变化 / 手动刷新 / 翻页 / 首屏）
  //       'refresh-page1' —— 仅刷新 page1，与已有列表按 task_id 合并状态（5s 自动刷新用）
  const fetchCollectionTasks = async (
    opts: { mode?: 'reset' | 'refresh-page1'; page?: number; silent?: boolean } = {},
  ) => {
    const { mode = 'reset', page, silent = false } = opts;
    if (!silent) setTaskListLoading(true);
    const targetPage = page ?? 1;
    try {
      const params: Record<string, unknown> = {
        page: targetPage,
        page_size: tasksPageSize,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto',
      };
      if (taskStatusFilter !== 'all') {
        params.status = taskStatusFilter;
      }
      const response = await dataApi.getTasks(params);
      const newTasks = Array.isArray(response.tasks) ? response.tasks : [];
      const total = response.pagination?.total ?? 0;

      if (mode === 'refresh-page1') {
        // 只更新 page1 的状态，不动用户已翻到的页
        setCollectionTasks((prev) => (targetPage === 1
          ? [...newTasks, ...prev.filter((t) => !newTasks.some((n) => n.task_id === t.task_id))]
          : prev));
      } else {
        // reset：页码越界钳制（筛掉数据后 current 可能超出最大页）
        const maxPage = Math.max(1, Math.ceil(total / tasksPageSize));
        const clamped = Math.min(Math.max(1, targetPage), maxPage);
        setCollectionTasks(newTasks);
        setTasksPage(clamped);
      }

      setTasksTotal(total);

      // 自动检测并恢复正在运行的任务状态
      const runningTask = newTasks.find(
        (task) => task.status === 'running' || task.status === 'pending',
      );
      if (runningTask && runningTask.task_id && !currentTaskIdRef.current) {
        setCurrentTaskId(runningTask.task_id);
        setTaskStatus(runningTask.status as TaskStatus);
        setTaskProgress(runningTask.progress?.percentage || 0);
      }
    } catch (error) {
      console.error('Failed to fetch task list:', error);
      if (!silent) message.error(t('dm_msg_fetch_tasks_failed'));
    } finally {
      if (!silent) setTaskListLoading(false);
    }
  };

  // 删除单条任务记录
  const handleDeleteTask = async (taskId: string) => {
    setTasksDeletingId(taskId);
    try {
      await dataApi.deleteTask(taskId);
      message.success(t('dm_msg_task_deleted'));
      // 本地列表直接移除，避免重新拉整个列表
      const next = collectionTasks.filter((t) => t.task_id !== taskId);
      const remaining = Math.max(0, tasksTotal - 1);
      setCollectionTasks(next);
      setTasksTotal(remaining);
      // 页内删空时钳回上一页重新拉取
      if (next.length === 0 && remaining > 0 && !taskSearchText) {
        const maxPage = Math.max(1, Math.ceil(remaining / tasksPageSize));
        fetchCollectionTasks({ page: Math.min(tasksPage, maxPage), silent: true });
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      message.error(t('dm_msg_delete_failed', { msg }));
    } finally {
      setTasksDeletingId(null);
    }
  };

  // 自动刷新：当有运行中任务时，每 5s 仅刷新 page1 状态，不覆盖已追加的历史页
  useEffect(() => {
    const hasRunning = taskStatus === 'running' || taskStatus === 'pending'
      || collectionTasks.some((t) => t.status === 'running' || t.status === 'pending');
    if (!hasRunning) return;
    const timer = setInterval(() => fetchCollectionTasks({ mode: 'refresh-page1' }), 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [taskStatus, collectionTasks]);

  // 状态筛选变化时重置分页并重新拉取
  useEffect(() => {
    fetchCollectionTasks({ mode: 'reset' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [taskStatusFilter]);

  // 按后端 task_key 约定预生成全部子任务占位行（货币对×周期）：
  // 任务开始前就展示完整清单（占比 0%），WS 进度按 task_key 就地更新，
  // 避免"下载到哪个货币对才冒出哪一行"
  const buildProgressPlaceholders = (symbols: string[], intervals: string[]): TaskDetailItem[] =>
    (intervals.length > 0 ? intervals : ['']).flatMap((iv) =>
      symbols.map((symbol) => ({
        task_key: iv ? `${iv}:${symbol}` : symbol,
        symbol,
        interval: iv,
        percentage: 0,
      })),
    );

  // 开始数据采集
  const startCollection = async (symbol: string) => {
    try {
      const endDate = dayjs();
      const startDate = dayjs().subtract(1, 'month');

      const requestPayload = {
        symbols: [symbol],
        interval: ['15m', '1h', '1d'],
        start: startDate.format('YYYY-MM-DD'),
        end: endDate.format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 1,
        data_type: 'kline',
        market: SYSTEM_CONFIG.crypto_trading_mode,
        candle_type: SYSTEM_CONFIG.crypto_trading_mode,
      };

      const response = await dataApi.downloadCryptoData(requestPayload);

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        // 当前任务卡在列表刷新前就能显示正确的类型/市场标签
        setCurrentTaskParams(requestPayload);
        setTaskStatus('running');
        setTaskProgress(0);
        // 重置并预填充子任务明细行：开始前就展示全部 货币对×周期（0%），
        // 下载过程中 WS 按 task_key 就地更新对应行
        setTaskProgressList(buildProgressPlaceholders([symbol], ['15m', '1h', '1d']));
        // 订阅已移至全局，此处不再需要
        fetchCollectionTasks();
        message.success(t('dm_msg_collect_started', { symbol }));
      }
    } catch (error) {
      message.error(t('dm_msg_start_collection_failed'));
      console.error('Failed to start collection task:', error);
    }
  };

  // 批量采集
  const handleBatchCollection = async () => {
    try {
      const values = await collectionForm.validateFields();
      const selectedSymbols = values.symbols || [];
      // 新增：数据类型（默认 kline，与旧行为一致）
      const dataType: string = values.dataType || 'kline';
      // 新增：市场（spot/um/cm）。kline 的 candle_type 与该值保持一致
      const market: string = values.market || SYSTEM_CONFIG.crypto_trading_mode || 'spot';

      if (selectedSymbols.length === 0) {
        message.warning(t('dm_msg_select_one_symbol'));
        return;
      }

      // 仅 K 线类 & 特殊 K 线类（mark/index/premium Klines）需要 interval
      const KLINE_TYPES = new Set(['kline', 'markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines']);
      const interval = KLINE_TYPES.has(dataType)
        ? (values.intervals || ['15m'])
        : [];

      // 期货专属数据（标记/指数/溢价 K线 + fundingRate/openInterest）仅支持 um/cm（Binance 约定）
      if (FUTURES_ONLY_KINDS.includes(dataType as DataKind) && market === 'spot') {
        message.warning(t('dm_msg_futures_only', { type: DATA_KIND_LABEL[dataType as DataKind] ?? dataType }));
        return;
      }

      const requestPayload = {
        symbols: selectedSymbols,
        // data_type + market: 新统一入口的两个核心参数
        data_type: dataType,
        market,
        interval,
        start: values.dateRange?.[0]?.format('YYYY-MM-DD') || dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
        end: values.dateRange?.[1]?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: values.maxWorkers ?? 4,
        // 兼容旧字段：K 线时保留 candle_type 以便原有逻辑继续工作
        candle_type: KLINE_TYPES.has(dataType) ? market : undefined,
      };

      const response = await dataApi.downloadCryptoData(requestPayload);

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        // 当前任务卡在列表刷新前就能显示正确的类型/市场标签
        setCurrentTaskParams(requestPayload);
        setTaskStatus('running');
        setTaskProgress(0);
        // 重置并预填充子任务明细行：开始前就展示全部 货币对×周期（0%），
        // 下载过程中 WS 按 task_key 就地更新对应行
        setTaskProgressList(buildProgressPlaceholders(selectedSymbols, interval));
        fetchCollectionTasks();
        message.success(t('dm_msg_task_started', { type: dataType, market }));
      }
    } catch (error) {
      // antd validateFields reject 的 error.message 是表单 rule 文案（已翻译），
      // 需要时可在提示中带上；此处兜底提示统一走 i18n
      message.error(t('start_batch_collection_failed'));
      console.error('Failed to start batch collection:', error);
    }
  };

  // 检查数据质量
  const checkQuality = async (symbol: string, interval: string) => {
    try {
      setQualityLoading(true);
      setSelectedSymbolForQuality(symbol);
      setSelectedIntervalForQuality(interval);

      const response = await dataApi.checkKlineQuality({
        symbol,
        interval,
      });

      setQualityDetail(response);
      setActiveTab('quality');
      message.success(t('dm_msg_quality_done'));
    } catch (error) {
      message.error(t('dm_msg_quality_failed'));
      console.error('Data quality check failed:', error);
    } finally {
      setQualityLoading(false);
    }
  };

  // 打开数据清理弹窗
  const handleOpenCleanModal = () => {
    cleanForm.resetFields();
    setCleanResult(null);
    setIsCleanModalOpen(true);
  };

  // 执行数据清理
  const handleCleanData = async () => {
    try {
      const values = await cleanForm.validateFields();
      setCleanLoading(true);

      const response = await dataApi.cleanKlineData({
        symbol: values.symbol,
        interval: values.interval,
        start: values.dateRange?.[0]?.format('YYYY-MM-DD'),
        end: values.dateRange?.[1]?.format('YYYY-MM-DD'),
        clean_type: values.cleanType,
        market_type: 'crypto',
        crypto_type: 'spot',
      });

      setCleanResult(response);
      message.success(t('dm_msg_clean_done', { n: response.deleted_count || 0 }));
    } catch (error) {
      message.error(t('dm_msg_clean_failed'));
      console.error('Data cleanup failed:', error);
    } finally {
      setCleanLoading(false);
    }
  };

  // 获取质量状态标签
  // §6.2 chip 化的质量标签（原 antd Tag 改 qc-chip：ok/warn/down/quiet 四态）
  const getQualityTag = (quality?: string) => {
    switch (quality) {
      case 'good':
        return <span className="qc-chip ok">{t('dm_quality_good')}</span>;
      case 'warning':
        return <span className="qc-chip warn">{t('dm_quality_warning')}</span>;
      case 'bad':
        return <span className="qc-chip down">{t('dm_quality_bad')}</span>;
      default:
        return <span className="qc-chip quiet">{t('dm_quality_unknown')}</span>;
    }
  };

  // 获取价格变化颜色（JS 侧语义色走 var(--qc-*)，跟主题切换）
  const getPriceChangeColor = (change: number) => change >= 0 ? 'var(--qc-success)' : 'var(--qc-error)';

  // 格式化成交量
  const formatVolume = (volume: number) => {
    if (volume >= 1e9) {
      return `${(volume / 1e9).toFixed(2)}B`;
    } else if (volume >= 1e6) {
      return `${(volume / 1e6).toFixed(2)}M`;
    } else if (volume >= 1e3) {
      return `${(volume / 1e3).toFixed(2)}K`;
    }
    return volume.toFixed(2);
  };

  // 自选组下拉菜单
  const getGroupMenuItems = (symbolId: string): MenuProps['items'] => {
    return [
      {
        key: 'header',
        label: <Text type="secondary" className="text-xs">{t('dm_add_to_group_header')}</Text>,
        disabled: true,
      },
      ...favoriteGroups.map(group => ({
        key: group.id,
        label: (
          <Space>
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: group.color }} />
            <span>{group.name}</span>
            {group.symbolIds.includes(symbolId) && <CheckCircleOutlined style={{ color: 'var(--qc-success)' }} />}
          </Space>
        ),
        onClick: () => {
          if (group.symbolIds.includes(symbolId)) {
            handleRemoveFromGroup(symbolId, group.id);
          } else {
            handleAddToGroup(symbolId, group.id);
          }
        },
      })),
    ];
  };

  // ==================== 归档 / 衍生 浏览方法 ====================

  // 判断 kind 属于 archive 还是 deriv
  const isDerivKind = (kind: ArchiveKind | DerivKind): kind is DerivKind =>
    DERIV_KINDS.includes(kind as DerivKind);

  // 拉取 (kind, market) 下的 symbols 列表（带缓存）
  const fetchArchiveSymbols = async (kind: ArchiveKind | DerivKind, market: MarketType) => {
    const key = `${kind}__${market}`;
    if (archiveSymbolsMap[key]) return;
    setArchiveSymbolsLoading(true);
    try {
      const resp = isDerivKind(kind)
        ? await derivApi.listSymbols(kind, market)
        : await archiveApi.listSymbols(kind as ArchiveKind, market);
      const list = Array.isArray(resp?.symbols) ? resp.symbols : [];
      setArchiveSymbolsMap((prev) => ({ ...prev, [key]: list }));
    } catch (error) {
      console.error('Failed to fetch archive symbols:', error);
      message.error(t('dm_msg_fetch_symbols_list_failed'));
      setArchiveSymbolsMap((prev) => ({ ...prev, [key]: [] }));
    } finally {
      setArchiveSymbolsLoading(false);
    }
  };

  // 选中 (kind, market, symbol) 时拉取 meta + 拉一页数据
  const handleArchiveSelectSymbol = async (kind: ArchiveKind | DerivKind, market: MarketType, symbol: string) => {
    setArchiveKind(kind);
    setArchiveMarket(market);
    setArchiveSymbol(symbol);
    setArchivePage(1);
    setArchiveMeta(null);
    setArchiveRows([]);
    setArchiveTotal(0);
    setArchiveTruncated(false);

    let meta: ArchiveMeta | null = null;
    try {
      const resp = isDerivKind(kind)
        ? await derivApi.getMeta(kind, market, symbol)
        : await archiveApi.getMeta(kind as ArchiveKind, market, symbol);
      meta = resp?.meta ?? null;
      setArchiveMeta(meta);
    } catch (error) {
      console.error('Failed to read archive metadata:', error);
    }

    // 用 meta 里的数据实际区间对齐查询窗口：默认"近7天"等范围大概率与历史归档数据不重叠，
    // 直接查会得到 0 行（数据如 2025-07 的归档 vs 当前时间去查）。end 取当天末尾避免漏掉最后一天。
    let queryRange = archiveTimeRange;
    if (meta?.earliest_date && meta?.latest_date) {
      queryRange = [
        new Date(`${meta.earliest_date}T00:00:00`).getTime(),
        new Date(`${meta.latest_date}T23:59:59.999`).getTime(),
      ];
      setArchiveTimeRange(queryRange);
    }

    await doArchiveQuery(kind, market, symbol, queryRange, 1, archivePageSize);
  };

  // 实际拉取数据
  const doArchiveQuery = async (
    kind: ArchiveKind | DerivKind,
    market: MarketType,
    symbol: string,
    range: [number, number],
    page: number,
    size: number,
  ) => {
    if (!symbol) {
      message.warning(t('dm_msg_select_symbol_first'));
      return;
    }
    setArchiveQueryLoading(true);
    try {
      const resp = isDerivKind(kind)
        ? await derivApi.queryData(kind, market, symbol, range[0], range[1], size, (page - 1) * size)
        : await archiveApi.queryData(kind as ArchiveKind, market, symbol, range[0], range[1], size, (page - 1) * size);
      setArchiveRows(Array.isArray(resp?.rows) ? resp.rows : []);
      setArchiveTotal(resp?.total ?? 0);
      setArchiveTruncated(Boolean(resp?.truncated));
    } catch (error) {
      console.error('Failed to query archive data:', error);
      message.error(t('dm_msg_query_failed'));
    } finally {
      setArchiveQueryLoading(false);
    }
  };

  // 删除当前选中 (kind, market, symbol) 的全部数据
  const handleArchiveDelete = async () => {
    if (!archiveSymbol) return;
    setArchiveDeleting(true);
    try {
      if (isDerivKind(archiveKind as DerivKind)) {
        await derivApi.deleteData(archiveKind as DerivKind, archiveMarket, archiveSymbol);
      } else {
        await archiveApi.deleteData(archiveKind as ArchiveKind, archiveMarket, archiveSymbol);
      }
      message.success(t('dm_msg_symbol_deleted', { symbol: archiveSymbol }));
      setArchiveRows([]);
      setArchiveTotal(0);
      setArchiveMeta(null);
      setArchiveSymbol('');
      const key = `${archiveKind}__${archiveMarket}`;
      setArchiveSymbolsMap((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      await fetchArchiveSymbols(archiveKind, archiveMarket);
    } catch (error) {
      console.error('Failed to delete archive data:', error);
      message.error(t('dm_msg_data_delete_failed'));
    } finally {
      setArchiveDeleting(false);
    }
  };

  // 确保某 kind 下各 market 的 symbols 列表都已加载（已缓存的跳过）
  // 衍生数据仅支持 um/cm（spot 无意义），故只拉 2 个；archive 拉全 3 个
  const ensureKindSymbolsLoaded = (kind: ArchiveKind | DerivKind) => {
    const markets: MarketType[] = isDerivKind(kind)
      ? (['um', 'cm'] as MarketType[])
      : ARCHIVE_MARKETS;
    markets.forEach((m) => {
      if (!archiveSymbolsMap[`${kind}__${m}`]) {
        fetchArchiveSymbols(kind, m);
      }
    });
  };

  // 当展开 kind 时，加载其下的 market 子树 symbols
  const handleArchiveExpandKind = (kind: ArchiveKind | DerivKind, expanded: boolean) => {
    if (expanded) {
      setArchiveExpandedKinds((prev) => (prev.includes(kind) ? prev : [...prev, kind]));
      ensureKindSymbolsLoaded(kind);
    } else {
      setArchiveExpandedKinds((prev) => prev.filter((k) => k !== kind));
    }
  };

  // 初始 state 默认展开 aggTrades，但展开 state 本身不会触发加载，
  // 挂载时主动拉一次，否则其下 SPOT/UM/CM 会一直停留在 "..." 占位
  useEffect(() => {
    ensureKindSymbolsLoaded('aggTrades');
    // 仅在挂载时执行一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ==================== 渲染方法 ====================

  // ---- 采集任务表（demo「同步任务」卡排版：开始时间/任务/范围/状态/备注/操作） ----

  // 状态 → §6.2 chip（运行中带 pulse 圆点；等待中/取消中性）
  const renderTaskStatusChip = (status: string) => {
    switch (status) {
      case 'running':
        return <span className="qc-chip info"><span className="qc-pdot" />{t('dm_st_running')}</span>;
      case 'completed':
        return <span className="qc-chip ok">{t('dm_st_completed')}</span>;
      case 'failed':
        return <span className="qc-chip down">{t('dm_st_failed')}</span>;
      case 'canceled':
        return <span className="qc-chip warn">{t('dm_st_canceled')}</span>;
      default:
        return <span className="qc-chip quiet">{t('dm_st_pending')}</span>;
    }
  };

  // 从任务 params 提取数据类型 / 市场 / 标的范围 / 周期 / 时间窗
  const taskParamsOf = (task: Task): Record<string, unknown> =>
    (task.params ?? {}) as Record<string, unknown>;

  const taskSymListOf = (task: Task): string[] => {
    const p = taskParamsOf(task);
    return Array.isArray(p.symbols) ? p.symbols.map(String) : [];
  };

  // 范围单元格：symbols(超出 2 个折叠) · 周期 · 时间窗（mono 11px fg-3，demo c-mono c-mute 口径）
  const renderTaskScope = (task: Task) => {
    const p = taskParamsOf(task);
    const syms = taskSymListOf(task);
    const ivs = Array.isArray(p.interval) ? p.interval.map(String) : [];
    const start = typeof p.start === 'string' ? p.start : '';
    const end = typeof p.end === 'string' ? p.end : '';
    const symText = syms.length > 2
      ? `${syms[0]}…+${syms.length - 1}`
      : syms.join(', ');
    const range = start && end ? `${start.slice(5)} → ${end.slice(5)}` : '';
    const parts = [symText, ivs.join(','), range].filter(Boolean).join(' · ');
    if (!parts) return <span className="qc-cell-none qc-mono">—</span>;
    return (
      <Tooltip title={parts} placement="topLeft">
        <span className="qc-cell-id" style={{ fontSize: 11 }}>{parts}</span>
      </Tooltip>
    );
  };

  // 备注单元格：运行中 = 迷你进度条 + 已完成 x/y；失败 = 错误信息；其余弱「—」
  const renderTaskRemark = (task: Task) => {
    const progress = task.progress;
    if (task.status === 'running' && progress) {
      return (
        <span className="qc-row-chips" style={{ flexWrap: 'nowrap' }}>
          <span className="qc-prog" style={{ width: 56 }}><i style={{ width: `${Math.min(100, Math.max(0, progress.percentage || 0))}%` }} /></span>
          <span className="qc-mono" style={{ fontSize: 11, color: 'var(--qc-text-tertiary)' }}>
            {t('dm_completed_of', { done: progress.completed || 0, total: progress.total || 0 })}
          </span>
        </span>
      );
    }
    if (task.status === 'failed' && task.error_message) {
      return (
        <Tooltip title={task.error_message} placement="topLeft">
          <span className="qc-cell-down" style={{ fontSize: 12 }}>{task.error_message}</span>
        </Tooltip>
      );
    }
    return <span className="qc-cell-none">—</span>;
  };

  // 任务行全集（含未入库的当前任务兜底行）
  const allTaskRows = useMemo<Task[]>(() => {
    const hasCurrent = currentTaskId && collectionTasks.some((t) => t.task_id === currentTaskId);
    const currentRow: Task | null = hasCurrent ? null : (currentTaskId && (taskStatusFilter === 'all' || taskStatusFilter === taskStatus) ? {
      task_id: currentTaskId,
      status: taskStatus,
      task_type: 'download',
      // 使用创建任务时保存的真实请求参数，保证类型/市场标签正确
      params: currentTaskParams,
      progress: { percentage: taskProgress, total: taskProgressList.length, completed: taskProgressList.filter((x) => (x.percentage || 0) >= 100).length, failed: 0, current: '' },
      created_at: new Date().toISOString(),
    } : null);
    return currentRow ? [currentRow, ...collectionTasks] : collectionTasks;
  }, [collectionTasks, currentTaskId, currentTaskParams, taskStatus, taskStatusFilter, taskProgress, taskProgressList]);

  // 搜索命中行（对已加载行做前端过滤，§6.6）
  const searchedTasks = useMemo(() => {
    const q = taskSearchText.trim().toLowerCase();
    if (!q) return allTaskRows;
    return allTaskRows.filter((task) => {
      const p = taskParamsOf(task);
      const haystack = [
        task.task_id,
        String(p.data_type ?? ''),
        String(p.market ?? ''),
        Array.isArray(p.symbols) ? p.symbols.join(' ') : '',
        Array.isArray(p.interval) ? p.interval.join(' ') : '',
      ].join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [allTaskRows, taskSearchText]);

  const isTaskSearching = taskSearchText.trim() !== '';
  const visibleTasks = isTaskSearching ? searchedTasks : allTaskRows;

  // 任务表列定义：§6.5（时间 mono / 任务 mono / 状态 chip / 备注 / 操作 24px）
  const taskColumns: TableProps<Task>['columns'] = [
    {
      title: t('dm_col_started'),
      key: 'created_at',
      width: 100, // 「11-20 14:12」11px mono ≈ 73px + 24px 内边距；再窄会折两行把行高从 45 撑到 51
      render: (_, record: Task) => (
        <span className="qc-cell-time qc-mono">
          {record.created_at ? dayjs(record.created_at).format('MM-DD HH:mm') : '—'}
        </span>
      ),
    },
    {
      title: t('dm_col_task'),
      key: 'task',
      width: 112,
      ellipsis: true,
      render: (_, record: Task) => {
        const p = taskParamsOf(record);
        const dataType = String(p.data_type ?? 'kline');
        const market = String(p.market ?? p.candle_type ?? 'spot');
        return (
          <span className="qc-row-chips">
            <span className="qc-cell-strat">{DATA_KIND_LABEL[dataType as keyof typeof DATA_KIND_LABEL] ?? dataType}</span>
            <span className="qc-chip quiet qc-mono">{market.toUpperCase()}</span>
            {record.task_id === currentTaskId && <span className="qc-chip info">{t('dm_tag_current')}</span>}
          </span>
        );
      },
    },
    {
      title: t('dm_col_scope'),
      key: 'scope',
      width: 112,
      ellipsis: true,
      render: (_, record: Task) => renderTaskScope(record),
    },
    {
      title: t('status'),
      key: 'status',
      width: 72,
      render: (_, record: Task) => renderTaskStatusChip(record.status),
    },
    {
      title: t('dm_col_remark'),
      key: 'remark',
      ellipsis: true,
      render: (_, record: Task) => renderTaskRemark(record),
    },
    {
      title: t('action'),
      key: 'op',
      width: 44,
      render: (_, record: Task) => {
        // 仅"当前"任务禁用删——那是自己正在盯着跑的；历史 running/pending 允许删（僵尸任务）
        const canDelete = record.task_id !== currentTaskId
          && record.status !== 'running'
          && record.status !== 'pending';
        return (
          <div className="qc-row-actions">
            <Popconfirm
              title={t('dm_del_confirm_title')}
              description={t('dm_del_confirm_desc')}
              okText={t('delete')}
              okButtonProps={{ danger: true }}
              cancelText={t('cancel')}
              disabled={!canDelete}
              onConfirm={() => handleDeleteTask(record.task_id!)}
            >
              <Tooltip title={canDelete ? t('dm_del_record_tip') : t('dm_del_record_disabled_tip')}>
                <button
                  type="button"
                  className="qc-mini-btn qc-icon-only danger"
                  aria-label={canDelete ? t('dm_del_record_tip') : t('dm_del_record_disabled_tip')}
                  disabled={!canDelete || tasksDeletingId === record.task_id}
                >
                  <DeleteOutlined />
                </button>
              </Tooltip>
            </Popconfirm>
          </div>
        );
      },
    },
  ];

  // 展开行：子任务明细（当前任务吃 WS 的 taskProgressList；历史任务按需拉取，走 taskDetailsMap）
  const fetchTaskDetails = async (taskId: string) => {
    if (taskDetailsMap[taskId]) return;
    try {
      const data = await dataApi.getTaskDetails(taskId);
      const details = data?.details;
      if (details) {
        setTaskDetailsMap((prev) => ({ ...prev, [taskId]: details }));
      }
    } catch (error) {
      console.error('Failed to fetch task details:', error);
    }
  };

  const renderTaskDetails = (task: Task) => {
    const externalProgressList = task.task_id === currentTaskId ? taskProgressList : [];
    const cachedList = taskDetailsMap[task.task_id] ?? [];
    const displayList = externalProgressList.length > 0 ? externalProgressList : cachedList;
    if (displayList.length === 0) {
      return (
        <QcEmpty
          icon={<FileSearchOutlined />}
          title={t('dm_no_subtask_details')}
        />
      );
    }
    return (
      <div className="mb-0.5">
        {displayList.slice(0, isProgressExpanded ? undefined : 5).map((subTask) => {
          // failed>0 表示该品种下载失败: 必须显式标红, 0% 空条无法区分"失败"与"未执行"
          const failed = Number(subTask.failed ?? 0) > 0;
          const statusText = typeof subTask.status === 'string' ? subTask.status : '';
          return (
            <div key={String(subTask.task_key ?? subTask.symbol ?? '')} className="mb-1.5">
              <div className="mb-0.5 flex items-center justify-between">
                <span className="qc-row-chips">
                  <Text className="text-xs font-medium">{String(subTask.symbol ?? '')}</Text>
                  {subTask.interval && <span className="qc-chip quiet qc-mono">{String(subTask.interval)}</span>}
                  {failed && <span className="qc-chip down">{t('dm_st_failed')}</span>}
                </span>
                <span className="qc-mono" style={{ fontSize: 11, color: failed ? 'var(--qc-error)' : 'var(--qc-text-tertiary)' }}>
                  {subTask.percentage?.toFixed(1)}%
                </span>
              </div>
              <span
                className={`qc-prog${(subTask.percentage ?? 0) >= 100 && !failed ? ' done' : ''}`}
                style={{ width: '100%', maxWidth: 420 }}
              >
                <i style={{ width: `${Math.min(100, Math.max(0, subTask.percentage || 0))}%`, background: failed ? 'var(--qc-error)' : undefined }} />
              </span>
              {failed && statusText && (
                <div className="text-[11px] text-error">{statusText}</div>
              )}
            </div>
          );
        })}
        {displayList.length > 5 && (
          <Button
            type="link"
            size="small"
            onClick={() => setIsProgressExpanded(!isProgressExpanded)}
            style={{ padding: 0, fontSize: 12 }}
          >
            {isProgressExpanded ? t('dm_collapse') : t('dm_expand_all', { n: displayList.length })}
          </Button>
        )}
      </div>
    );
  };

  // 渲染自选组侧边栏
  const renderGroupSidebar = () => (
    <div className="favorite-groups-sidebar w-full">
      <Card
        size="small"
        className="qc-card"
        title={
          <Space>
            <FolderOutlined />
            <span>{t('favorite_group')}</span>
          </Space>
        }
        extra={
          <Tooltip title={t('manage_watchlist')}>
            <Button
              type="text"
              size="small"
              icon={<SettingOutlined />}
              onClick={() => setIsGroupDrawerOpen(true)}
            />
          </Tooltip>
        }
        styles={{ body: { padding: '8px 0' } }}
      >
        <Menu
          mode="inline"
          selectedKeys={[String(activeGroupId)]}
          onClick={({ key }) => {
            if (key === 'all') {
              setActiveGroupId(0);
            } else {
              setActiveGroupId(Number(key));
            }
          }}
          style={{ border: 'none' }}
          items={[
            {
              key: 'all',
              icon: <DatabaseOutlined />,
              label: (
                <Space className="w-full justify-between">
                  <span>{t('all')}</span>
                  <span className="qc-count-chip qc-mono">{symbols.length}</span>
                </Space>
              ),
            },
            ...favoriteGroups.map(group => ({
              key: String(group.id),
              icon: <FolderOutlined style={{ color: group.color }} />,
              label: (
                <Space className="w-full justify-between">
                  <span>{group.name}</span>
                  <span className="qc-count-chip qc-mono">{group.symbolIds.length}</span>
                </Space>
              ),
            })),
          ]}
        />
        
        <Divider style={{ margin: 'var(--spacing-qc-2) 0' }} />
        
        <Button
          type="dashed"
          block
          icon={<PlusOutlined />}
          onClick={handleCreateGroup}
          className="mx-4"
          style={{ width: 'calc(100% - 32px)' }}
        >
          {t('create_watchlist')}
        </Button>
      </Card>
    </div>
  );

  // 渲染组管理抽屉
  const renderGroupDrawer = () => (
    <Drawer
      title={t('manage_watchlist')}
      placement="right"
      // §6.18：抽屉宽 400（原 size={400} 是无效枚举传参，按意图落为 width）
      width={400}
      open={isGroupDrawerOpen}
      onClose={() => setIsGroupDrawerOpen(false)}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateGroup}>
          {t('new')}
        </Button>
      }
    >
      <Space orientation="vertical" className="w-full">
        {favoriteGroups.sort((a, b) => a.sortOrder - b.sortOrder).map((group) => (
          <Card
            key={group.id}
            size="small"
            className="qc-card"
            style={{ borderLeft: `4px solid ${group.color}` }}
            // 删除统一放卡片右上角，与其他卡片页面一致；默认组不可删除
            extra={
              <Popconfirm
                title={t('dm_confirm_delete_group')}
                description={t('delete_description')}
                onConfirm={(e) => handleDeleteGroup(group.id, e)}
                disabled={group.isDefault}
              >
                <Tooltip title={group.isDefault ? t('default_group_undeletable') : t('delete')}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    disabled={group.isDefault}
                  />
                </Tooltip>
              </Popconfirm>
            }
            actions={[
              <Tooltip key="batch-add" title={t('batch_add_favorite')}>
                <Button
                  type="text"
                  icon={<ImportOutlined />}
                  onClick={(e) => handleOpenBatchAdd(group, e)}
                />
              </Tooltip>,
              <Tooltip key="edit" title={t('edit_watchlist')}>
                <Button
                  type="text"
                  icon={<EditOutlined />}
                  onClick={(e) => handleEditGroup(group, e)}
                />
              </Tooltip>,
            ]}
          >
            <Card.Meta
              title={
                <Space>
                  <span>{group.name}</span>
                  {group.isDefault && <span className="qc-count-chip">{t('default')}</span>}
                </Space>
              }
              description={
                <Space orientation="vertical" size={0}>
                  <Text type="secondary" className="text-xs">
                    {group.description || t('no_description')}
                  </Text>
                  <Text type="secondary" className="text-xs">
                    {t('dm_n_symbols_created', { n: group.symbolIds.length, date: group.createdAt })}
                  </Text>
                </Space>
              }
            />
          </Card>
        ))}
      </Space>
    </Drawer>
  );

  // 渲染组编辑弹窗
  const renderGroupModal = () => (
    <Modal
      className="qc-modal"
      title={editingGroup ? t('edit_watchlist') : t('create_watchlist')}
      open={isGroupModalOpen}
      onOk={handleSaveGroup}
      onCancel={() => setIsGroupModalOpen(false)}
      okText={t('save')}
      cancelText={t('cancel')}
    >
      <Form form={groupForm} layout="vertical" className="qc-form">
        <Form.Item
          name="name"
          label={t('watchlist_name')}
          rules={[{ required: true, message: t('watchlist_name_placeholder') }]}
        >
          <Input placeholder={t('watchlist_name_example')} />
        </Form.Item>

        <Form.Item
          name="description"
          label={t('watchlist_desc')}
        >
          <Input.TextArea rows={2} placeholder={t('watchlist_desc_placeholder')} />
        </Form.Item>

        <Form.Item
          name="color"
          label={t('color_tag')}
          initialValue={QUANT_COLORS.info}
        >
          <Select
            placeholder={t('dm_color_select')}
            options={[
              { value: QUANT_COLORS.info, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:QUANT_COLORS.info }} />{t('dm_color_blue')}</Space> },
              { value: QUANT_COLORS.positive, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:QUANT_COLORS.positive }} />{t('dm_color_green')}</Space> },
              { value: QUANT_COLORS.warning, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:QUANT_COLORS.warning }} />{t('dm_color_yellow')}</Space> },
              { value: QUANT_COLORS.negative, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:QUANT_COLORS.negative }} />{t('dm_color_red')}</Space> },
              { value: WATCHLIST_COLOR_PURPLE, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:WATCHLIST_COLOR_PURPLE }} />{t('dm_color_purple')}</Space> },
              { value: QUANT_COLORS.info, label: <Space><div className="h-4 w-4 rounded" style={{ backgroundColor:QUANT_COLORS.info }} />{t('dm_color_cyan')}</Space> },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );

  // 渲染批量添加穿梭框弹窗
  const renderBatchAddModal = () => {
    // 准备穿梭框数据
    const transferData = symbols.map(symbol => ({
      key: symbol.symbol,
      title: symbol.symbol,
      description: `${symbol.baseAsset}/${symbol.quoteAsset} · ${symbol.price ? '$' + symbol.price.toLocaleString() : '-'}`,
      disabled: false,
    }));

    return (
      <Modal
        className="qc-modal"
        title={
          <Space>
            <ImportOutlined />
            <span>{t('dm_batch_add_title', { name: batchAddTargetGroup?.name ?? '' })}</span>
          </Space>
        }
        open={isBatchAddModalOpen}
        onOk={handleConfirmBatchAdd}
        onCancel={handleCloseBatchAdd}
        width={800}
        okText={t('dm_ok_add')}
        cancelText={t('cancel')}
        destroyOnHidden
      >
        <div className="mb-4">
          <Text type="secondary">
            {t('dm_transfer_summary', { n: transferTargetKeys.length, total: symbols.length })}
          </Text>
        </div>
        <Transfer
          dataSource={transferData}
          titles={[t('dm_transfer_available'), t('dm_transfer_selected')]}
          targetKeys={transferTargetKeys}
          selectedKeys={transferSelectedKeys}
          onChange={handleTransferChange}
          onSelectChange={handleTransferSelectChange}
          render={item => (
            <div className="flex flex-col">
              <Text strong>{item.title}</Text>
              <Text type="secondary" className="text-xs">{item.description}</Text>
            </div>
          )}
          listStyle={{
            width: 360,
            height: 400,
          }}
          showSearch
          filterOption={(inputValue, item) =>
            item.title!.toLowerCase().includes(inputValue.toLowerCase()) ||
            item.description!.toLowerCase().includes(inputValue.toLowerCase())
          }
          locale={{
            searchPlaceholder: t('search_symbol'),
            itemUnit: t('dm_item_unit'),
            itemsUnit: t('dm_items_unit'),
            notFoundContent: t('no_data'),
          }}
        />
      </Modal>
    );
  };

  // 渲染数据清理弹窗
  const renderCleanDataModal = () => (
    <Modal
      className="qc-modal"
      title={
        <Space>
          <DeleteOutlined />
          <span>{t('dm_clean_title')}</span>
        </Space>
      }
      open={isCleanModalOpen}
      onOk={handleCleanData}
      onCancel={() => setIsCleanModalOpen(false)}
      width={600}
      okText={t('dm_ok_start_clean')}
      cancelText={t('dm_cancel')}
      confirmLoading={cleanLoading}
      okButtonProps={{ danger: true }}
    >
      <Alert
        title={t('dm_warn_title')}
        description={t('dm_clean_warn_desc')}
        type="warning"
        showIcon
        className="mb-6"
      />
      <Form
        form={cleanForm}
        layout="vertical"
        className="qc-form"
      >
        <Form.Item
          name="symbol"
          label={t('dm_col_symbol')}
          rules={[{ required: true, message: t('dm_msg_select_symbol') }]}
        >
          <Select
            showSearch
            placeholder={t('dm_ph_select_symbol')}
            options={symbols.map(s => ({ value: s.symbol, label: s.symbol }))}
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <Form.Item
          name="interval"
          label={t('dm_col_interval')}
        >
          <Select
            allowClear
            placeholder={t('dm_ph_interval_all')}
            options={[
              { value: '1m', label: t('dm_iv_1m') },
              { value: '5m', label: t('dm_iv_5m') },
              { value: '15m', label: t('dm_iv_15m') },
              { value: '1h', label: t('dm_iv_1h') },
              { value: '4h', label: t('dm_iv_4h') },
              { value: '1d', label: t('dm_iv_1d') },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="dateRange"
          label={t('dm_form_date_range')}
        >
          <DatePicker.RangePicker
            className="w-full"
            placeholder={[t('dm_ph_start_date'), t('dm_ph_end_date')]}
          />
        </Form.Item>

        <Form.Item
          name="cleanType"
          label={t('dm_clean_type')}
          initialValue="all"
          rules={[{ required: true, message: t('dm_msg_select_clean_type') }]}
        >
          <Select
            placeholder={t('dm_ph_clean_type')}
            options={[
              { value: 'all', label: t('dm_clean_type_all') },
              { value: 'duplicates', label: t('dm_clean_type_dup') },
              { value: 'invalid', label: t('dm_clean_type_invalid') },
            ]}
          />
        </Form.Item>
      </Form>

      {cleanResult && (
        <>
          <Divider style={{ margin: 'var(--spacing-qc-6) 0' }} />
          <Alert
            title={t('dm_result_title')}
            description={
              <Space orientation="vertical">
                <Text>{t('dm_result_symbol', { symbol: cleanResult.symbol })}</Text>
                <Text>{t('dm_result_interval', { interval: cleanResult.interval || t('dm_all') })}</Text>
                <Text>{t('dm_result_type', { type: cleanResult.clean_type })}</Text>
                <Text>{t('dm_result_before', { n: cleanResult.total_before })}</Text>
                <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_result_deleted', { n: cleanResult.deleted_count })}</Text>
              </Space>
            }
            type="success"
            showIcon
          />
        </>
      )}
    </Modal>
  );

  // ==================== 归档 / 衍生 浏览渲染 ====================

  // 树滚动区最大高度：按滚动区自身在文档中的真实位置动态计算，
  // 替代写死的 calc(100vh - 260px) 魔法数——页头/Tab/卡片结构变化时自动适应。
  // 滚动宿主是 ConsoleLayout 的 Layout.Content（overflow-y-auto），
  // 补偿其 scrollTop 得到文档坐标，使高度不随外层页面滚动漂移。
  const treeScrollRef = useRef<HTMLDivElement>(null);
  const [treeMaxHeight, setTreeMaxHeight] = useState(480);
  useEffect(() => {
    const measure = () => {
      const el = treeScrollRef.current;
      if (!el) return;
      const scroller = el.closest('.ant-layout-content');
      const outerScroll = scroller?.scrollTop ?? window.scrollY;
      const docTop = el.getBoundingClientRect().top + outerScroll;
      // 底部留 12px 呼吸边距；下限 320 防极小窗口挤压
      setTreeMaxHeight(Math.max(320, window.innerHeight - docTop - 12));
    };
    measure();
    // 首测可能早于布局稳定（字体加载 / 浏览器滚动恢复 / Tab 动画，实测曾
    // 偏差 200px+）：body 高度随这些迟到变化而改变，用 ResizeObserver
    // 触发重测校准。树展开只向下长、不改变滚动区文档位置，重测值不变，
    // 不会形成 measure→render→RO 的循环。
    const ro = new ResizeObserver(measure);
    ro.observe(document.body);
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [activeTab]); // 树仅在 archive tab 激活后挂载，切 tab 需重测一次

  // 渲染左侧树形导航（archive 7 种 + deriv 2 种 → market → symbols）
  const renderArchiveTree = () => {
    const kinds = archiveBrowserCategory === 'archive' ? ARCHIVE_KINDS : DERIV_KINDS;
    const marketsForKind = (k: ArchiveKind | DerivKind): MarketType[] =>
      isDerivKind(k) ? (['um', 'cm'] as MarketType[]) : ARCHIVE_MARKETS;
    const searchLower = archiveSymbolSearch.toLowerCase();

    return (
    // 分类切换 + 搜索框固定在滚动区外（滚到底部分类后无需滚回即可搜索）；
    // 树滚动区高度跟随视口而非写死 600px——7 类全展开时底部类别可直接滚到，
    // 不再需要收起上方分支才能点击
    <Flex vertical gap={8}>
      {/* 分类切换：归档数据（7 种） vs 衍生数据（2 种） */}
      <Segmented
        block
        className="qc-seg"
        size="small"
        value={archiveBrowserCategory}
        onChange={(v) => {
          const cat = v as ArchiveBrowserCategory;
          setArchiveBrowserCategory(cat);
          const firstKind = cat === 'archive' ? ARCHIVE_KINDS[0] : DERIV_KINDS[0];
          setArchiveKind(firstKind);
          setArchiveSymbol('');
          setArchiveExpandedKinds([firstKind]);
          // 切换后首个 kind 处于默认展开态，需主动拉取市场列表，否则只显示 "..."
          ensureKindSymbolsLoaded(firstKind);
        }}
        options={[
          { value: 'archive', label: t('dm_cat_archive', { n: ARCHIVE_KINDS.length }) },
          { value: 'deriv', label: t('dm_cat_deriv', { n: DERIV_KINDS.length }) },
        ]}
      />

      {/* Symbol 搜索框 */}
      <Input
        size="small"
        placeholder={t('dm_ph_search_symbol')}
        prefix={<SearchOutlined className="text-foreground/25" />}
        allowClear
        value={archiveSymbolSearch}
        onChange={(e) => setArchiveSymbolSearch(e.target.value)}
      />

      {/* kind 树滚动区：高度按滚动区真实位置自适应视口（treeMaxHeight），单层滚动 */}
      <div ref={treeScrollRef} style={{ overflow: 'auto', maxHeight: treeMaxHeight, minHeight: 320 }}>
      {kinds.map((kind) => {
        const expanded = archiveExpandedKinds.includes(kind);
        const kindLabel = (DATA_KIND_LABEL as Record<string, string>)[kind] ?? kind;
        return (
          <div key={kind} className="mb-0.5">
            <div
              onClick={() => handleArchiveExpandKind(kind, !expanded)}
              className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-[5px] text-[13px]"
              style={{
                backgroundColor: expanded ? 'color-mix(in srgb, var(--qc-info) 10%, transparent)' : 'transparent',
                fontWeight: archiveKind === kind ? 600 : 400,
              }}
            >
              {expanded ? <FolderOpenOutlined /> : <FolderOutlined />}
              <span>{kindLabel}</span>
              {archiveBrowserCategory === 'archive' && KLINE_ARCHIVE_KINDS.includes(kind as ArchiveKind) && (
                <span className="qc-chip info">{t('dm_tag_kline')}</span>
              )}
              {archiveBrowserCategory === 'deriv' && <span className="qc-chip pri">{t('dm_tag_deriv')}</span>}
            </div>
            {expanded && (
              <div className="pl-3.5 mt-0.5">
                {marketsForKind(kind).map((m) => {
                  const key = `${kind}__${m}`;
                  const symList = archiveSymbolsMap[key];
                  // 搜索过滤
                  const filteredSyms = searchLower && symList
                    ? symList.filter(s => s.toLowerCase().includes(searchLower))
                    : symList;
                  return (
                    <div key={m} className="mb-0.5">
                      <div
                        className="rounded px-1.5 py-[3px] text-xs text-foreground/60"
                        style={{
                          backgroundColor: archiveKind === kind && archiveMarket === m ? 'color-mix(in srgb, var(--qc-info) 8%, transparent)' : 'transparent',
                        }}
                      >
                        <FolderOutlined className="mr-1" />
                        {m.toUpperCase()}
                        <Text type="secondary" className="ml-1.5 text-[11px]">
                          {symList ? `(${searchLower && filteredSyms ? `${filteredSyms.length}/${symList.length}` : symList.length})` : '...'}
                        </Text>
                      </div>
                      {/* symbol 列表不再内层滚动：统一交给外层树滚动区，避免双层滚动条 */}
                      {filteredSyms && filteredSyms.length > 0 && (
                        <div className="pl-3">
                          {filteredSyms.slice(0, 100).map((s) => (
                            <div
                              key={s}
                              onClick={() => handleArchiveSelectSymbol(kind, m, s)}
                              className="cursor-pointer rounded-[3px] px-1.5 py-0.5 text-xs"
                              style={{
                                backgroundColor:
                                  archiveKind === kind && archiveMarket === m && archiveSymbol === s
                                    ? 'color-mix(in srgb, var(--qc-info) 30%, transparent)'
                                    : 'transparent',
                                color:
                                  archiveKind === kind && archiveMarket === m && archiveSymbol === s
                                    ? 'var(--qc-info)'
                                    : 'var(--qc-text)',
                              }}
                            >
                              {s}
                            </div>
                          ))}
                          {filteredSyms.length > 100 && (
                            <Text type="secondary" className="px-1.5 py-0.5 text-[11px]">
                              {t('dm_more_n', { n: filteredSyms.length - 100 })}
                            </Text>
                          )}
                        </div>
                      )}
                      {searchLower && symList && filteredSyms && filteredSyms.length === 0 && (
                        <Text type="secondary" className="pl-3 text-[11px]">{t('dm_no_match')}</Text>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </Flex>
    );
  };

  // 表格列根据当前 rows 的 key 动态生成（duck typing）+ 智能列宽/对齐
  const archiveColumns = useMemo(() => {
    if (archiveRows.length === 0) return [] as Array<{ title: string; dataIndex: string; key: string; width?: number; ellipsis?: boolean; align?: 'left' | 'right' | 'center' }>;
    const keys = Object.keys(archiveRows[0] ?? {});
    // 时间类字段名
    const TIME_KEYS = new Set(['timestamp', 'time', 'open_time', 'close_time', 'first_update_id', 'last_update_id']);
    return keys.map((k) => {
      // 判断是否为数值列（取前 5 行采样）
      const sample = archiveRows.slice(0, 5).map(r => r[k]);
      const isNumeric = sample.every(v => v === null || typeof v === 'number');
      let width = 120;
      if (TIME_KEYS.has(k) || k === 'symbol') width = 150;
      else if (isNumeric) width = 130;
      else if (k === 'side' || k === 'is_buyer_maker') width = 90;
      return {
        title: k,
        dataIndex: k,
        key: k,
        width,
        ellipsis: true,
        align: (isNumeric ? 'right' : 'left') as 'left' | 'right',
        // 数值/时间列走 mono（§6.5）；布尔列原样文本；空值统一「—」
        render: (v: unknown) => {
          if (v === null || v === undefined || v === '') return <span className="qc-cell-none">—</span>;
          if (typeof v === 'boolean') return <span>{v ? 'true' : 'false'}</span>;
          if (isNumeric || TIME_KEYS.has(k)) {
            return <span className="qc-mono">{typeof v === 'number' ? v.toLocaleString() : String(v)}</span>;
          }
          return <span className="qc-cell-id">{String(v)}</span>;
        },
      };
    });
  }, [archiveRows]);

  // 渲染主面板（统一浏览器：归档7种 + 衍生2种）
  const renderArchiveBrowser = () => {
    const kindLabel = (DATA_KIND_LABEL as Record<string, string>)[archiveKind as string] ?? archiveKind;
    // 仅当 kind 是需要 interval 的 K 线类时显示 interval selector
    const needInterval = INTERVAL_REQUIRED_KINDS.includes(archiveKind as DataKind);
    return (
    <Row gutter={[16, 16]}>
      {/* 左侧树形导航 */}
      <Col xs={24} md={8} lg={6}>
        <Card
          className="qc-card"
          size="small"
          title={
            <Space>
              <DatabaseOutlined />
              <span>{t('dm_archive_browse_title')}</span>
            </Space>
          }
          extra={
            <Text type="secondary" className="text-[11px]">
              {archiveSymbolsLoading ? t('dm_loading') : ''}
            </Text>
          }
        >
          {renderArchiveTree()}
        </Card>
      </Col>

      {/* 右侧内容 */}
      <Col xs={24} md={16} lg={18}>
        <Card
          className="qc-card"
          size="small"
          title={
            archiveSymbol ? (
              <Space wrap>
                <span className="qc-chip info">{kindLabel}</span>
                <span className="qc-chip quiet qc-mono">{archiveMarket.toUpperCase()}</span>
                <span className="qc-cell-id">{archiveSymbol}</span>
                {needInterval && (
                  <span className="qc-chip quiet qc-mono">{archiveInterval}</span>
                )}
                {isDerivKind(archiveKind as DerivKind) && <span className="qc-chip pri">{t('dm_tag_deriv')}</span>}
              </Space>
            ) : (
              <span>
                <FileSearchOutlined /> {t('dm_pick_hint')}
              </span>
            )
          }
          extra={
            archiveSymbol ? (
              <Space size="small">
                {/* K 线类数据才支持逐根回放 */}
                {needInterval && (
                  <Button
                    size="small"
                    icon={<PlayCircleOutlined />}
                    onClick={() =>
                      navigate(`/data-management/market-replay?symbol=${archiveSymbol}&interval=${archiveInterval}`)
                    }
                  >
                    {t('dm_replay_label')}
                  </Button>
                )}
                <Popconfirm
                  title={t('dm_del_data_confirm_title', { symbol: archiveSymbol, kind: kindLabel })}
                  description={t('dm_del_data_confirm_desc')}
                  okText={t('dm_ok_delete')}
                  cancelText={t('dm_cancel')}
                  okButtonProps={{ danger: true }}
                  onConfirm={handleArchiveDelete}
                >
                  <Button
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    loading={archiveDeleting}
                  >
                    {t('dm_del_symbol_short')}
                  </Button>
                </Popconfirm>
              </Space>
            ) : null
          }
        >
          {!archiveSymbol ? (
            <QcEmpty
              icon={<FileSearchOutlined />}
              title={t('dm_pick_browse_hint')}
              description={t('dm_browse_steps')}
            />
          ) : (
            <Space orientation="vertical" className="w-full" size="middle">
              {/* 元数据概览（值走 mono，§5 kv 口径） */}
              {archiveMeta && (
                <Descriptions size="small" column={{ xs: 2, sm: 4 }} bordered={false} className="rounded-qc-sm bg-foreground/2 px-3 py-2">
                  <Descriptions.Item label={t('dm_meta_start')}><span className="qc-mono">{archiveMeta.earliest_date}</span></Descriptions.Item>
                  <Descriptions.Item label={t('dm_meta_end')}><span className="qc-mono">{archiveMeta.latest_date}</span></Descriptions.Item>
                  <Descriptions.Item label={t('dm_meta_rows')}><span className="qc-mono">{archiveMeta.total_rows.toLocaleString()}</span></Descriptions.Item>
                  <Descriptions.Item label={t('dm_meta_files')}><span className="qc-mono">{archiveMeta.file_count}</span></Descriptions.Item>
                </Descriptions>
              )}
              {archiveMeta && archiveMeta.corrupt_dates.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  title={t('dm_corrupt_dates', { n: archiveMeta.corrupt_dates.length })}
                  description={archiveMeta.corrupt_dates.slice(0, 10).join(', ')}
                  className="text-xs"
                />
              )}

              {/* bookDepth 大数据量警告 */}
              {archiveKind === 'bookDepth' && (
                <Alert
                  type="warning"
                  showIcon
                  title={t('dm_bookdepth_warn_title')}
                  description={t('dm_bookdepth_warn_desc')}
                />
              )}

              {/* 查询控件 */}
              <Space wrap size={8} align="center">
                {/* 快捷时间预设 */}
                <Segmented
                  className="qc-seg"
                  size="small"
                  value=""
                  onChange={(v) => {
                    const end = Date.now();
                    const ranges: Record<string, number> = { '1d': 86400_000, '7d': 7 * 86400_000, '30d': 30 * 86400_000, 'all': 365 * 86400_000 };
                    const ms = ranges[v as string] || 7 * 86400_000;
                    setArchiveTimeRange([end - ms, end]);
                  }}
                  options={[
                    { value: '1d', label: t('dm_prs_1d') },
                    { value: '7d', label: t('dm_prs_7d') },
                    { value: '30d', label: t('dm_prs_30d') },
                    { value: 'all', label: t('dm_prs_1y') },
                  ]}
                />
                <RangePicker
                  showTime
                  size="small"
                  style={{ width: 320 }}
                  value={[dayjs(archiveTimeRange[0]), dayjs(archiveTimeRange[1])]}
                  onChange={(dates) => {
                    if (dates && dates[0] && dates[1]) {
                      setArchiveTimeRange([dates[0].valueOf(), dates[1].valueOf()]);
                    }
                  }}
                />
                {needInterval && (
                  <Select
                    size="small"
                    style={{ width: 80 }}
                    value={archiveInterval}
                    onChange={setArchiveInterval}
                    options={ARCHIVE_INTERVALS.map((i) => ({ value: i, label: i }))}
                  />
                )}
                <Button
                  type="primary"
                  size="small"
                  icon={<SearchOutlined />}
                  loading={archiveQueryLoading}
                  onClick={() =>
                    doArchiveQuery(archiveKind, archiveMarket, archiveSymbol, archiveTimeRange, 1, archivePageSize)
                  }
                >
                  {t('dm_query')}
                </Button>
                <Text type="secondary" className="text-xs">
                  {t('dm_total_rows_n', { n: archiveTotal.toLocaleString() })}
                  {archiveTruncated && t('dm_truncated')}
                </Text>
              </Space>

              {/* 数据表（qc-table 密度 + §6.7 分页；归档独立档位 100/200/500/1000，见上方注释） */}
              <DataTable<KeyedArchiveRow>
                dataSource={archiveRows.map((r, i): KeyedArchiveRow => ({ ...r, __rk: i }))}
                rowKey={(r) => String(r.__rk)}
                columns={archiveColumns}
                loading={archiveQueryLoading}
                scroll={{ x: 'max-content', y: 480 }}
                remote={true}
                pagination={{
                  current: archivePage,
                  pageSize: archivePageSize,
                  total: archiveTotal,
                  showSizeChanger: true,
                  // 归档明细查询一次返回整段数据，单页行数即取数上限，
                  // 与全局每页条数配置语义不同，独立档位不参与全局分页体系
                  pageSizeOptions: [100, 200, 500, 1000],
                  onChange: (p, s) => {
                    setArchivePage(p);
                    setArchivePageSize(s);
                    doArchiveQuery(archiveKind, archiveMarket, archiveSymbol, archiveTimeRange, p, s);
                  },
                }}
              />
            </Space>
          )}
        </Card>
      </Col>
    </Row>
    );
  };

  // 渲染货币对工具栏 - 参考策略回测页面风格
  // 批量开启自动更新
  const batchEnableAutoUpdate = () => {
    if (selectedSymbols.length === 0) {
      message.warning(t('dm_msg_select_symbols_first'));
      return;
    }
    setSymbols(prev =>
      prev.map(s => selectedSymbols.includes(s.symbol) ? { ...s, autoUpdate: true } : s)
    );
    message.success(t('dm_msg_auto_on', { n: selectedSymbols.length }));
  };

  // 批量关闭自动更新
  const batchDisableAutoUpdate = () => {
    if (selectedSymbols.length === 0) {
      message.warning(t('dm_msg_select_symbols_first'));
      return;
    }
    setSymbols(prev =>
      prev.map(s => selectedSymbols.includes(s.symbol) ? { ...s, autoUpdate: false } : s)
    );
    message.success(t('dm_msg_auto_off', { n: selectedSymbols.length }));
  };

  // 批量采集数据
  const batchCollectData = () => {
    if (selectedSymbols.length === 0) {
      message.warning(t('dm_msg_select_symbols_first'));
      return;
    }
    // 这里可以实现批量采集逻辑
    message.info(t('dm_msg_batch_collect_wip', { n: selectedSymbols.length }));
  };

  // 清空选择
  const clearSelection = () => {
    setSelectedSymbols([]);
  };

  const renderSymbolToolbar = () => (
    <div className="mb-4">
      {/* §6.6 工具栏：搜索 + 计价货币 ichip + 排序 + 右侧刷新 */}
      <PageToolbar
        search={{
          value: searchText,
          onChange: setSearchText,
          placeholder: t('search_symbol'),
          ariaLabel: t('search_symbol'),
        }}
        filters={
          <>
            <div role="group" aria-label={t('quote_currency')} style={{ display: 'contents' }}>
              {(['all', 'USDT', 'BTC', 'ETH'] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  className={`qc-ichip${quoteFilter === q ? ' qc-ichip-on' : ''}`}
                  onClick={() => setQuoteFilter(q)}
                >
                  {q === 'all' ? t('all') : q}
                </button>
              ))}
            </div>
            <Select
              aria-label={t('dm_sort')}
              value={`${sortField}-${sortOrder}`}
              onChange={(value) => {
                const [field, order] = value.split('-');
                setSortField(field as SortField);
                setSortOrder(order as SortOrder);
              }}
              style={{ width: 170 }}
              options={[
                { value: 'rank-asc', label: t('sort_by_rank') },
                { value: 'symbol-asc', label: t('sort_by_name_asc') },
                { value: 'symbol-desc', label: t('sort_by_name_desc') },
                { value: 'price-desc', label: t('sort_by_price_desc') },
                { value: 'price-asc', label: t('sort_by_price_asc') },
                { value: 'change-desc', label: t('sort_by_change_desc') },
                { value: 'change-asc', label: t('sort_by_change_asc') },
                { value: 'volume-desc', label: t('sort_by_volume_desc') },
              ]}
            />
          </>
        }
        count={(() => {
          // 与 DataTable 分页口径一致；空表按「0 / 共 0」显示
          const total = filteredSymbols.length;
          if (total === 0) return t('shown_range', { start: 0, end: 0, total: 0 });
          const page = Math.min(Math.max(1, currentPage), Math.max(1, Math.ceil(total / pageSize)));
          return t('shown_range', {
            start: (page - 1) * pageSize + 1,
            end: Math.min(page * pageSize, total),
            total,
          });
        })()}
        actions={
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchSymbols}
            loading={symbolLoading}
          >
            {t('refresh')}
          </Button>
        }
      />

      {/* 批量操作条 - 当有选中项时显示（§6.2 提示条：success 8% 底 + 45% 边） */}
      {selectedSymbols.length > 0 && (
        <Card
          size="small"
          className="mb-3 qc-card"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--qc-success) 8%, transparent)',
            borderColor: 'color-mix(in srgb, var(--qc-success) 45%, transparent)',
          }}
        >
          <Row align="middle" justify="space-between">
            <Col>
              <Space>
                <span className="font-medium text-success">
                  {t('dm_selected_n', { n: selectedSymbols.length })}
                </span>
                <Button type="link" size="small" onClick={clearSelection}>
                  {t('clear_selection')}
                </Button>
              </Space>
            </Col>
            <Col>
              <Space wrap>
                <Button
                  size="small"
                  icon={<CheckCircleOutlined />}
                  onClick={batchEnableAutoUpdate}
                >
                  {t('batch_enable_auto_update')}
                </Button>
                <Button
                  size="small"
                  icon={<CloseCircleOutlined />}
                  onClick={batchDisableAutoUpdate}
                >
                  {t('batch_disable_auto_update')}
                </Button>
                <Button
                  size="small"
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  onClick={batchCollectData}
                >
                  {t('batch_collection')}
                </Button>
              </Space>
            </Col>
          </Row>
        </Card>
      )}
    </div>
  );

  // 渲染统计卡片（§6.4 KPI：label 11px fg-4 → mono 22px/650 → 弱注 10.5px）
  const renderStatistics = () => (
    <div className="qc-kpi-grid mb-4">
      <div className="qc-kpi">
        <div className="qc-kpi-top">
          <span className="qc-kpi-lb">{t('total_symbols')}</span>
          <DatabaseOutlined style={{ color: 'var(--qc-text-quaternary)', fontSize: 14 }} />
        </div>
        <div className="qc-kpi-num">{symbols.length}</div>
        <div className="qc-kpi-sub">{t('dm_kpi_groups_n', { n: favoriteGroups.length })}</div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top">
          <span className="qc-kpi-lb">{t('current_group')}</span>
          <FolderOpenOutlined style={{ color: activeGroup?.color ?? 'var(--qc-text-quaternary)', fontSize: 14 }} />
        </div>
        {/* 「全部」不是自选组（activeGroupId=0），此时口径应等于总标的数，不能显示 0 */}
        <div className="qc-kpi-num">{activeGroup ? activeGroup.symbolIds.length : symbols.length}</div>
        <div className="qc-kpi-sub">{activeGroup?.name ?? t('dm_all')}</div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top">
          <span className="qc-kpi-lb">{t('has_data')}</span>
          <CheckCircleOutlined style={{ color: 'var(--qc-text-quaternary)', fontSize: 14 }} />
        </div>
        <div className="qc-kpi-num">{filteredSymbols.filter(s => s.hasData).length}</div>
        <div className="qc-kpi-sub">{t('dm_kpi_denom', { n: filteredSymbols.length })}</div>
      </div>
      <div className="qc-kpi">
        <div className="qc-kpi-top">
          <span className="qc-kpi-lb">{t('auto_update')}</span>
          <ReloadOutlined style={{ color: 'var(--qc-text-quaternary)', fontSize: 14 }} />
        </div>
        <div className="qc-kpi-num">{filteredSymbols.filter(s => s.autoUpdate).length}</div>
        <div className="qc-kpi-sub">{t('dm_kpi_denom', { n: filteredSymbols.length })}</div>
      </div>
    </div>
  );

  // 检查货币对是否在任何自选组中
  const isSymbolInAnyGroup = (symbolId: string) => {
    return favoriteGroups.some(group => group.symbolIds.includes(symbolId));
  };

  // 获取货币对所在的第一个自选组（用于显示星星颜色）
  const getSymbolFirstGroup = (symbolId: string) => {
    return favoriteGroups.find(group => group.symbolIds.includes(symbolId));
  };

  // 列表视图列定义（§6.5：标的双列 mono / 数值右侧 mono / 空值「—」/ 操作 24px）
  const symbolColumns: TableProps<SymbolData>['columns'] = [
    {
      title: '',
      key: 'inGroup',
      width: 44,
      render: (_: unknown, record: SymbolData) => {
        // 在"全部"视图时，检查是否在任何自选组中
        // 在特定自选组视图时，只检查是否在当前组中
        const isInActiveGroup = activeGroup
          ? activeGroup.symbolIds.includes(record.symbol)
          : isSymbolInAnyGroup(record.symbol);
        // 获取要显示的组（用于星星颜色）
        const displayGroup = activeGroup || getSymbolFirstGroup(record.symbol);

        return (
          <Dropdown
            menu={{ items: getGroupMenuItems(record.symbol) }}
            trigger={['click']}
          >
            <button
              type="button"
              className="qc-mini-btn qc-icon-only"
              aria-label={t('favorite_group')}
              onClick={(e) => e.stopPropagation()}
            >
              {isInActiveGroup
                ? <StarFilled style={{ color: displayGroup?.color || 'var(--qc-warning)' }} />
                : <StarOutlined />}
            </button>
          </Dropdown>
        );
      },
    },
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 200,
      render: (text: string, record: SymbolData) => (
        <span className="qc-row-chips">
          <span className="qc-cell-id">{text}</span>
          {record.rank && <span className="qc-chip quiet qc-mono">#{record.rank}</span>}
          {record.hasData && <span className="qc-chip ok"><span className="qc-pdot" />{t('dm_live')}</span>}
        </span>
      ),
    },
    {
      title: t('latest_price'),
      dataIndex: 'price',
      key: 'price',
      width: 120,
      align: 'right' as const,
      render: (price: number | null, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        return price
          ? <span className="qc-mono">${price.toLocaleString()}</span>
          : <span className="qc-cell-none">—</span>;
      },
    },
    {
      title: t('change_24h'),
      key: 'change',
      width: 108,
      align: 'right' as const,
      render: (_: unknown, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        if (record.priceChangePercent24h === null) return <span className="qc-cell-none">—</span>;
        const cls = record.priceChangePercent24h >= 0 ? 'qc-cell-up' : 'qc-cell-down';
        return (
          <span className={`qc-mono ${cls}`}>
            {record.priceChangePercent24h >= 0 ? '+' : ''}
            {record.priceChangePercent24h.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: t('volume_24h'),
      dataIndex: 'volume24h',
      key: 'volume24h',
      width: 108,
      align: 'right' as const,
      render: (volume: number | null, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        return volume
          ? <span className="qc-mono">{formatVolume(volume)}</span>
          : <span className="qc-cell-none">—</span>;
      },
    },
    {
      title: t('market_cap'),
      dataIndex: 'marketCap',
      key: 'marketCap',
      width: 104,
      align: 'right' as const,
      render: (cap?: number) => cap
        ? <span className="qc-mono">${(cap / 1000000000).toFixed(2)}B</span>
        : <span className="qc-cell-none">—</span>,
    },
    {
      title: t('data_status'),
      key: 'dataStatus',
      width: 170,
      render: (_: unknown, record: SymbolData) => (
        record.hasData ? (
          <span className="qc-row-chips">
            {getQualityTag(record.dataQuality)}
            {record.lastUpdateTime && (
              <span className="qc-cell-time qc-mono">{record.lastUpdateTime}</span>
            )}
          </span>
        ) : (
          <span className="qc-chip quiet">{t('no_data')}</span>
        )
      ),
    },
    {
      title: t('auto_update'),
      key: 'autoUpdate',
      width: 100,
      render: (_: unknown, record: SymbolData) => (
        <Switch
          size="small"
          checked={record.autoUpdate}
          onChange={(checked) => {
            setSymbols(prev =>
              prev.map(s => s.symbol === record.symbol ? { ...s, autoUpdate: checked } : s)
            );
          }}
        />
      ),
    },
    {
      title: t('action'),
      key: 'action',
      width: 76,
      fixed: 'right',
      render: (_: unknown, record: SymbolData) => (
        <div className="qc-row-actions">
          {!record.hasData ? (
            <Tooltip title={t('collect')}>
              <button
                type="button"
                className="qc-mini-btn qc-icon-only"
                aria-label={t('collect')}
                onClick={() => startCollection(record.symbol)}
              >
                <CloudDownloadOutlined />
              </button>
            </Tooltip>
          ) : (
            <>
              <Tooltip title={t('quality')}>
                <button
                  type="button"
                  className="qc-mini-btn qc-icon-only"
                  aria-label={t('quality')}
                  onClick={() => checkQuality(record.symbol, '1h')}
                >
                  <BarChartOutlined />
                </button>
              </Tooltip>
              <Tooltip title={t('update')}>
                <button
                  type="button"
                  className="qc-mini-btn qc-icon-only"
                  aria-label={t('update')}
                  onClick={() => startCollection(record.symbol)}
                >
                  <ReloadOutlined />
                </button>
              </Tooltip>
            </>
          )}
        </div>
      ),
    },
  ];

  // 渲染列表视图（DataTable：qc-table 密度 + 空态 + §6.7 自绘分页）
  const renderListView = () => (
    <DataTable<SymbolData>
      columns={symbolColumns}
      dataSource={filteredSymbols}
      rowKey="symbol"
      loading={symbolLoading}
      scroll={{ x: 1200 }}
      rowSelection={{
        selectedRowKeys: selectedSymbols,
        onChange: (keys) => setSelectedSymbols(keys as string[]),
      }}
      pagination={{
        current: currentPage,
        pageSize: pageSize,
        total: filteredSymbols.length,
        showSizeChanger: true,
        pageSizeOptions: PAGE_SIZE_OPTIONS,
        onChange: handlePageChange,
      }}
      emptyTitle={t('no_data')}
      emptyDescription={searchText.trim() ? t('dm_search_no_match', { q: searchText.trim() }) : undefined}
    />
  );

  // 渲染卡片视图
  const renderCardView = () => {
    // 计算当前页的货币对
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const currentPageSymbols = filteredSymbols.slice(startIndex, endIndex);

    return (
      <>
        <Row gutter={[16, 16]}>
          {currentPageSymbols.map(symbol => {
        // 在"全部"视图时，检查是否在任何自选组中
        // 在特定自选组视图时，只检查是否在当前组中
        const isInActiveGroup = activeGroup 
          ? activeGroup.symbolIds.includes(symbol.symbol)
          : isSymbolInAnyGroup(symbol.symbol);
        // 获取要显示的组（用于星星颜色和边框）
        const displayGroup = activeGroup || getSymbolFirstGroup(symbol.symbol);
        const isLoading = marketDataLoading[symbol.symbol];
        return (
          <Col xs={24} sm={12} md={8} lg={6} key={symbol.symbol}>
            <Card
              size="small"
              className="qc-card"
              title={
                <Space>
                  <Text strong>{symbol.symbol}</Text>
                  {symbol.rank && <span className="qc-count-chip qc-mono">#{symbol.rank}</span>}
                </Space>
              }
              extra={
                <Dropdown menu={{ items: getGroupMenuItems(symbol.symbol) }} trigger={['click']}>
                  <Button
                    type="text"
                    size="small"
                    icon={isInActiveGroup ? <StarFilled style={{ color: displayGroup?.color || 'var(--qc-warning)' }} /> : <StarOutlined />}
                  />
                </Dropdown>
              }
              style={{ 
                borderTop: `3px solid ${isInActiveGroup ? displayGroup?.color : 'transparent'}`,
              }}
            >
              <Space orientation="vertical" className="w-full">
                <Row justify="space-between">
                  <Text type="secondary">{t('dm_card_price')}</Text>
                  {isLoading ? <Spin size="small" /> : (
                    <Text strong className="text-base">
                      {symbol.price ? `$${symbol.price.toLocaleString()}` : '-'}
                    </Text>
                  )}
                </Row>
                <Row justify="space-between">
                  <Text type="secondary">{t('change_24h')}</Text>
                  {isLoading ? <Spin size="small" /> : (
                    <Text style={{ color: getPriceChangeColor(symbol.priceChangePercent24h || 0) }}>
                      {symbol.priceChangePercent24h !== null ? (
                        <>
                          {symbol.priceChangePercent24h >= 0 ? '+' : ''}
                          {symbol.priceChangePercent24h.toFixed(2)}%
                        </>
                      ) : '-'}
                    </Text>
                  )}
                </Row>
                <Row justify="space-between">
                  <Text type="secondary">{t('dm_volume')}</Text>
                  {isLoading ? <Spin size="small" /> : (
                    <Text>{symbol.volume24h ? formatVolume(symbol.volume24h) : '-'}</Text>
                  )}
                </Row>
                <Divider style={{ margin: 'var(--spacing-qc-2) 0' }} />
                <Row justify="space-between" align="middle">
                  {getQualityTag(symbol.dataQuality)}
                  <Space>
                    {!symbol.hasData ? (
                      <Button
                        type="primary"
                        size="small"
                        icon={<CloudDownloadOutlined />}
                        onClick={() => startCollection(symbol.symbol)}
                      >
                        {t('collect')}
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        icon={<BarChartOutlined />}
                        onClick={() => checkQuality(symbol.symbol, '1h')}
                      >
                        {t('quality')}
                      </Button>
                    )}
                  </Space>
                </Row>
              </Space>
            </Card>
          </Col>
        );
      })}
        </Row>
        <Row justify="center" className="mt-4">
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={filteredSymbols.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => t('dm_total_n', { n: total })}
            onChange={handlePageChange}
          />
        </Row>
      </>
    );
  };

  // 渲染货币对列表 - 响应式布局：小屏幕自选组在上，列表在下
  const renderSymbolList = () => (
    <Row gutter={[16, 16]}>
      {/* 自选组侧边栏 - 小屏幕在上，大屏幕在左 */}
      <Col xs={24} lg={4}>
        {renderGroupSidebar()}
      </Col>
      {/* 列表内容 */}
      <Col xs={24} lg={20}>
        <Card className="qc-card">
          {renderSymbolToolbar()}
          {renderStatistics()}
          {viewType === 'list' ? renderListView() : renderCardView()}
        </Card>
      </Col>
    </Row>
  );

  // 渲染数据采集
  const renderCollection = () => {
    // 判断当前 data_type 是否需要 interval
    const needInterval = INTERVAL_REQUIRED_KINDS.includes(collectionDataType as DataKind);
    // 期货专属数据（标记/指数/溢价 K线 + fundingRate/openInterest）现货市场没有该数据，spot 选项禁用
    const spotDisabled = FUTURES_ONLY_KINDS.includes(collectionDataType as DataKind);
    // 当前默认 kline + spot，保持与旧行为一致
    return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card className="qc-card" title={t('dm_batch_collect_title')}>
          <Form
            form={collectionForm}
            layout="vertical"
            className="qc-form"
            onValuesChange={(changed) => {
              // 切到期货专属数据类型时现货市场承载不了，自动纠正为 U本位，
              // 避免用户先选好 spot 再切类型后旧值残留导致提交非法组合
              if (
                changed.dataType &&
                FUTURES_ONLY_KINDS.includes(changed.dataType) &&
                collectionForm.getFieldValue('market') === 'spot'
              ) {
                collectionForm.setFieldsValue({ market: 'um' });
                message.info(t('dm_msg_auto_switch_um'));
              }
            }}
            initialValues={{
              dateRange: [dayjs().subtract(1, 'month'), dayjs()],
              intervals: ['15m'],
              dataType: 'kline',
              market: 'spot',
            }}
          >
            {/* 1) 数据类型（下拉选择，支持分组） */}
            <Form.Item
              name="dataType"
              label={t('dm_form_datatype')}
              rules={[{ required: true, message: t('dm_msg_select_datatype') }]}
            >
              <Select
                placeholder={t('dm_msg_select_datatype')}
                className="w-full"
                showSearch
                optionFilterProp="label"
                options={[
                  {
                    label: t('dm_group_kline'),
                    options: [
                      { value: 'kline', label: t('dm_opt_kline') },
                      { value: 'markPriceKlines', label: t('dm_opt_mark') },
                      { value: 'indexPriceKlines', label: t('dm_opt_index') },
                      { value: 'premiumIndexKlines', label: t('dm_opt_premium') },
                    ],
                  },
                  {
                    label: t('dm_group_ticker'),
                    options: [
                      { value: 'aggTrades', label: t('dm_opt_aggtrades') },
                      { value: 'trades', label: t('dm_opt_trades') },
                      { value: 'bookDepth', label: t('dm_opt_bookdepth') },
                      { value: 'bookTicker', label: t('dm_opt_bookticker') },
                    ],
                  },
                  {
                    label: t('dm_group_deriv'),
                    options: [
                      { value: 'fundingRate', label: t('dm_opt_funding') },
                      { value: 'openInterest', label: t('dm_opt_oi') },
                    ],
                  },
                ]}
              />
            </Form.Item>

            {/* 2) 市场选择（spot / um / cm） */}
            <Form.Item
              name="market"
              label={t('dm_form_market')}
              rules={[{ required: true, message: t('dm_msg_select_market') }]}
              tooltip={spotDisabled ? t('dm_tooltip_futures_only') : undefined}
            >
              <Segmented
                className="qc-seg"
                options={[
                  { label: t('dm_mkt_spot'), value: 'spot', disabled: spotDisabled },
                  { label: t('dm_mkt_um'), value: 'um' },
                  { label: t('dm_mkt_cm'), value: 'cm' },
                ]}
              />
            </Form.Item>

            {/* 3) symbols 多选 */}
            <Form.Item
              name="symbols"
              label={t('select_symbol_or_group')}
              rules={[{ required: true, message: t('please_select_symbol_or_group') }]}
            >
              <Select
                mode="multiple"
                placeholder={t('select_symbol_or_group_placeholder')}
                showSearch
                allowClear
                options={[
                  // 自选组选项
                  ...(favoriteGroups.length > 0 ? [
                    {
                      label: <Text type="secondary" className="text-xs">{t('favorite_groups')}</Text>,
                      options: favoriteGroups.map((group) => ({
                        value: `group:${group.id}`,
                        label: t('dm_group_symbols_n', { name: group.name, n: group.symbolIds?.length || 0 }),
                      })),
                    }
                  ] : []),
                  // 货币对选项
                  {
                    label: <Text type="secondary" className="text-xs">{t('symbols')}</Text>,
                    options: symbols.map((s) => ({
                      value: s.symbol,
                      label: s.symbol,
                    })),
                  },
                ]}
                filterOption={(input, option) =>
                  (option?.label?.props?.children?.[0] || option?.label || '').toLowerCase().includes(input.toLowerCase())
                }
                onChange={(values) => {
                  // 处理自选组选择
                  const expandedSymbols: string[] = [];
                  values.forEach((value: string) => {
                    if (value.startsWith('group:')) {
                      const groupId = parseInt(value.replace('group:', ''));
                      const group = favoriteGroups.find(g => g.id === groupId);
                      if (group?.symbolIds) {
                        expandedSymbols.push(...group.symbolIds);
                      }
                    } else {
                      expandedSymbols.push(value);
                    }
                  });
                  const uniqueSymbols = [...new Set(expandedSymbols)];
                  collectionForm.setFieldsValue({ symbols: uniqueSymbols });
                }}
              />
            </Form.Item>

            {/* 4) 仅 K 线类显示 intervals */}
            {needInterval && (
              <Form.Item
                name="intervals"
                label={t('interval')}
                rules={[{ required: true, message: t('please_select_interval') }]}
              >
                <Select
                  mode="multiple"
                  placeholder={t('select_interval_placeholder')}
                  options={[
                    { value: '1m', label: t('interval_1m') },
                    { value: '5m', label: t('interval_5m') },
                    { value: '15m', label: t('interval_15m') },
                    { value: '30m', label: t('interval_30m') },
                    { value: '1h', label: t('interval_1h') },
                    { value: '4h', label: t('interval_4h') },
                    { value: '1d', label: t('interval_1d') },
                  ]}
                />
              </Form.Item>
            )}

            {/* 5) 时间范围 */}
            <Form.Item
              name="dateRange"
              label={t('date_range')}
              rules={[{ required: true, message: t('please_select_date_range') }]}
            >
              <RangePicker className="w-full" />
            </Form.Item>

            {/* 并发数：驱动 symbol 层线程数与单 symbol 日期分片并行数（后端夹紧 1-8） */}
            <Form.Item
              name="maxWorkers"
              label={t('dm_concurrency')}
              initialValue={4}
              tooltip={t('dm_tooltip_workers')}
            >
              <InputNumber min={1} max={8} step={1} precision={0} style={{ width: 120 }} />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={handleBatchCollection}
                block
              >
                {t('dm_start_collect_type', { type: DATA_KIND_LABEL[collectionDataType as keyof typeof DATA_KIND_LABEL] || collectionDataType })}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card
          className="qc-card"
          title={t('collection_tasks')}
          extra={<span className="qc-count-chip qc-mono">{t('dm_total_n', { n: tasksTotal })}</span>}
        >
          {/* 工具栏 §6.6：搜索（已加载行前端过滤） + 状态 ichip + 右侧计数 */}
          <PageToolbar
            search={{
              value: taskSearchText,
              onChange: (value) => {
                setTaskSearchText(value);
                // §6.6 过滤后页码归 1
                setTaskSearchPage(1);
              },
              placeholder: t('dm_search_tasks'),
              ariaLabel: t('dm_search_tasks'),
            }}
            filters={
              <div role="group" aria-label={t('filter_status')} style={{ display: 'contents' }}>
                {[
                  { value: 'all', i18nKey: 'dm_all' },
                  { value: 'completed', i18nKey: 'dm_st_completed' },
                  { value: 'running', i18nKey: 'dm_st_running' },
                  { value: 'failed', i18nKey: 'dm_st_failed' },
                ].map((chip) => (
                  <button
                    key={chip.value}
                    type="button"
                    className={`qc-ichip${taskStatusFilter === chip.value ? ' qc-ichip-on' : ''}`}
                    onClick={() => {
                      setTaskStatusFilter(chip.value);
                      // 服务端状态过滤 + 页码归 1
                      fetchCollectionTasks({ page: 1 });
                    }}
                  >
                    {t(chip.i18nKey)}
                  </button>
                ))}
              </div>
            }
            count={(() => {
              // 与 DataTable 分页条的钳制口径一致；0 条时按 demo 显示「0 / 共 0」
              const total = isTaskSearching ? searchedTasks.length : tasksTotal;
              if (total === 0) return t('shown_range', { start: 0, end: 0, total: 0 });
              const rawPage = isTaskSearching ? taskSearchPage : tasksPage;
              const page = Math.min(Math.max(1, rawPage), Math.max(1, Math.ceil(total / tasksPageSize)));
              return t('shown_range', {
                start: (page - 1) * tasksPageSize + 1,
                end: Math.min(page * tasksPageSize, total),
                total,
              });
            })()}
            actions={
              <Button
                icon={<ReloadOutlined />}
                onClick={() => fetchCollectionTasks({ page: tasksPage })}
                loading={taskListLoading}
              >
                {t('refresh')}
              </Button>
            }
          />

          <DataTable<Task>
            className="qc-tasks-table"
            columns={taskColumns}
            dataSource={visibleTasks}
            rowKey="task_id"
            loading={taskListLoading}
            remote={!isTaskSearching}
            scroll={{ x: 520 }} // 与左侧表单卡同排，容器常 ≈560px；580 会撑出横向滚动条并把操作列切掉
            expandable={{
              columnWidth: 40,
              expandedRowRender: renderTaskDetails,
              onExpand: (expanded, record) => {
                if (expanded && record.task_id !== currentTaskId) {
                  void fetchTaskDetails(record.task_id);
                }
              },
            }}
            pagination={visibleTasks.length > 0 ? {
              current: isTaskSearching ? taskSearchPage : tasksPage,
              pageSize: tasksPageSize,
              total: isTaskSearching ? searchedTasks.length : tasksTotal,
              showSizeChanger: false,
              onChange: (page) => {
                if (isTaskSearching) {
                  setTaskSearchPage(page);
                } else {
                  fetchCollectionTasks({ page });
                }
              },
            } : false}
            emptyTitle={isTaskSearching
              ? t('dm_search_no_match', { q: taskSearchText.trim() })
              : taskStatusFilter !== 'all' ? t('dm_no_tasks_for_status') : t('no_collection_tasks')}
            emptyDescription={isTaskSearching || taskStatusFilter !== 'all' ? undefined : t('dm_tasks_empty_hint')}
          />

          <div className="qc-footnote">
            <span>{t('dm_tasks_footnote')}</span>
          </div>
        </Card>
      </Col>
    </Row>
    );
  };

  // 质量概览 KPI 计数与占比（分母=已检测数，是纯展示算术）
  const kpiQualityCount = (q: 'good' | 'warning' | 'bad') =>
    symbols.filter((s) => s.dataQuality === q).length;
  const kpiQualityPct = (q: 'good' | 'warning' | 'bad') => {
    const detected = symbols.filter((s) => s.dataQuality !== 'unknown').length;
    return detected ? Math.round((kpiQualityCount(q) / detected) * 100) : 0;
  };

  // 渲染数据质量
  const renderQuality = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card className="qc-card" title={t('dm_quality_overview')}>
          <Space orientation="vertical" className="w-full">
            {/* §6.4 KPI：已检测 / 良好 / 警告 / 异常（2×2，复用 qc-kpi 原语） */}
            <div className="qc-kpi-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
              <div className="qc-kpi">
                <div className="qc-kpi-lb">{t('dm_stat_checked')}</div>
                <div className="qc-kpi-num">{symbols.filter((s) => s.dataQuality !== 'unknown').length}</div>
                <div className="qc-kpi-sub">{t('dm_kpi_of_total', { n: symbols.length })}</div>
              </div>
              <div className="qc-kpi">
                <div className="qc-kpi-lb">{t('dm_quality_good')}</div>
                <div className="qc-kpi-num up">{kpiQualityCount('good')}</div>
                <div className="qc-kpi-sub">{t('dm_kpi_pct_detected', { pct: kpiQualityPct('good') })}</div>
              </div>
              <div className="qc-kpi">
                <div className="qc-kpi-lb">{t('dm_quality_warning')}</div>
                <div className="qc-kpi-num warn">{kpiQualityCount('warning')}</div>
                <div className="qc-kpi-sub">{t('dm_kpi_pct_detected', { pct: kpiQualityPct('warning') })}</div>
              </div>
              <div className="qc-kpi">
                <div className="qc-kpi-lb">{t('dm_quality_bad')}</div>
                <div className="qc-kpi-num down">{kpiQualityCount('bad')}</div>
                <div className="qc-kpi-sub">{t('dm_kpi_pct_detected', { pct: kpiQualityPct('bad') })}</div>
              </div>
            </div>

            <Divider />

            <div>
              <Text strong>{t('dm_quick_check')}</Text>
              <Select
                placeholder={t('dm_ph_pick_symbol')}
                className="w-full mt-2"
                value={selectedSymbolForQuality || undefined}
                onChange={(value) => setSelectedSymbolForQuality(value)}
                options={symbols
                  .filter((s) => s.hasData)
                  .map((s) => ({ value: s.symbol, label: s.symbol }))}
              />
              <Select
                placeholder={t('dm_ph_pick_interval')}
                className="w-full mt-2"
                value={selectedIntervalForQuality || undefined}
                onChange={(value) => setSelectedIntervalForQuality(value)}
                options={[
                  { value: '1m', label: t('dm_iv_1m') },
                  { value: '5m', label: t('dm_iv_5m') },
                  { value: '15m', label: t('dm_iv_15m') },
                  { value: '1h', label: t('dm_iv_1h') },
                  { value: '4h', label: t('dm_iv_4h') },
                  { value: '1d', label: t('dm_iv_1d') },
                ]}
              />
              <Button
                type="primary"
                icon={<BarChartOutlined />}
                className="w-full mt-2"
                loading={qualityLoading}
                disabled={!selectedSymbolForQuality || !selectedIntervalForQuality}
                onClick={() =>
                  checkQuality(selectedSymbolForQuality, selectedIntervalForQuality)
                }
              >
                {t('dm_start_check')}
              </Button>
            </div>

            <Divider />

            <div>
              <Text strong>{t('dm_clean_title')}</Text>
              <Text type="secondary" className="mt-1 block text-xs">
                {t('dm_clean_desc')}
              </Text>
              <Button
                danger
                icon={<DeleteOutlined />}
                className="w-full mt-2"
                onClick={handleOpenCleanModal}
              >
                {t('dm_open_clean_tool')}
              </Button>
            </div>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={16}>
        <Card className="qc-card" title={t('dm_check_results')} loading={qualityLoading}>
          {qualityDetail ? (
            <Space orientation="vertical" className="w-full">
              <div className="qc-kpi-grid" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
                <div className="qc-kpi">
                  <div className="qc-kpi-lb">{t('dm_overall_status')}</div>
                  {(() => {
                    const status = qualityDetail.summary?.status;
                    const ok = status === 'good' || status === 'pass';
                    const warn = status === 'warning';
                    return <div className={`qc-kpi-num ${ok ? 'up' : warn ? 'warn' : 'down'}`}>{ok ? t('dm_q_pass') : warn ? t('dm_q_warn') : t('dm_q_fail')}</div>;
                  })()}
                </div>
                <div className="qc-kpi">
                  <div className="qc-kpi-lb">{t('dm_total_records')}</div>
                  <div className="qc-kpi-num">{qualityDetail.total_records}</div>
                </div>
                <div className="qc-kpi">
                  <div className="qc-kpi-lb">{t('dm_quality_score')}</div>
                  <div className="qc-kpi-num">{qualityDetail.summary?.score || 0}<span className="qc-kpi-sub" style={{ marginLeft: 4 }}>{t('dm_score_unit')}</span></div>
                </div>
              </div>

              {qualityDetail.details && (
                <Tabs
                  size="small"
                  items={[
                    {
                      key: 'integrity',
                      label: t('dm_tab_integrity'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.integrity?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_rec_total')}</Text> {qualityDetail.details.integrity?.total_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.integrity?.missing_columns && qualityDetail.details.integrity.missing_columns.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_missing_cols')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.integrity.missing_columns.map((col: string) => (
                                  <span key={col} className="qc-chip down qc-mono mb-1">{col}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.integrity?.missing_values && Object.keys(qualityDetail.details.integrity.missing_values).length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_missing_values')}</Text>
                              <div className="mt-2">
                                {Object.entries(qualityDetail.details.integrity.missing_values).map(([key, value]) => (
                                  <div key={key} className="mb-1">
                                    <span key={key} className="qc-chip warn qc-mono">{key}</span>
                                    <Text type="secondary"> {t('dm_missing_n', { n: value })}</Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'continuity',
                      label: t('dm_tab_continuity'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.continuity?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_expected_records')}</Text> {qualityDetail.details.continuity?.expected_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_actual_records')}</Text> {qualityDetail.details.continuity?.actual_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_missing_records')}</Text> {qualityDetail.details.continuity?.missing_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_coverage_label')}</Text> {Math.round((qualityDetail.details.continuity?.coverage_ratio || 0) * 100)}%
                            </Col>
                          </Row>
                          {qualityDetail.details.continuity?.missing_time_ranges && qualityDetail.details.continuity.missing_time_ranges.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong>{t('dm_missing_ranges')}</Text>
                              <div className="mt-2" style={{ maxHeight: 200, overflow: 'auto' }}>
                                {qualityDetail.details.continuity.missing_time_ranges.map((range, index: number) => (
                                  <div key={index} className="mb-1 text-xs">
                                    <span className="qc-mono">{range.start}</span> ~ <span className="qc-mono">{range.end}</span>
                                    <Text type="secondary" className="ml-2">
                                      {t('dm_missing_rows', { n: range.count })}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'uniqueness',
                      label: t('dm_tab_uniqueness'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.uniqueness?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_dup_records')}</Text> {qualityDetail.details.uniqueness?.duplicate_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.uniqueness?.duplicate_periods && qualityDetail.details.uniqueness.duplicate_periods.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong>{t('dm_dup_ranges')}</Text>
                              <div className="mt-2" style={{ maxHeight: 200, overflow: 'auto' }}>
                                {qualityDetail.details.uniqueness.duplicate_periods.map((interval: string, index: number) => (
                                  <span key={index} className="qc-chip quiet qc-mono mb-1">{interval}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.uniqueness?.duplicate_details && qualityDetail.details.uniqueness.duplicate_details.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong>{t('dm_dup_details')}</Text>
                              <div className="mt-2" style={{ maxHeight: 300, overflow: 'auto' }}>
                                {qualityDetail.details.uniqueness.duplicate_details.map((detail, index: number) => (
                                  <Card key={index} size="small" className="mb-2 qc-card">
                                    <Text strong>{t('dm_time_label', { key: detail.key })}</Text>
                                    <Text className="ml-2" type="secondary">({t('dm_dup_n', { n: detail.count })})</Text>
                                    <div className="mt-2">
                                      {(detail.records ?? []).map((record, rIndex: number) => (
                                        <div key={rIndex} className="mb-1 rounded bg-foreground/4 px-2 py-1 text-xs">
                                          <Text type="secondary">#{record.row_number}</Text>
                                          <Text className="ml-2">{t('dm_ohlc_o', { v: record.open })}</Text>
                                          <Text className="ml-2">{t('dm_ohlc_h', { v: record.high })}</Text>
                                          <Text className="ml-2">{t('dm_ohlc_l', { v: record.low })}</Text>
                                          <Text className="ml-2">{t('dm_ohlc_c', { v: record.close })}</Text>
                                          <Text className="ml-2">{t('dm_ohlc_v', { v: record.volume })}</Text>
                                        </div>
                                      ))}
                                    </div>
                                  </Card>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'validity',
                      label: t('dm_tab_validity'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.validity?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_invalid_total')}</Text> {qualityDetail.details.validity?.total_invalid_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.validity?.negative_prices && qualityDetail.details.validity.negative_prices.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_neg_prices')}</Text>
                              <Text type="secondary" className="ml-2">{t('dm_n_records', { n: qualityDetail.details.validity.negative_prices.length })}</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.negative_volumes && qualityDetail.details.validity.negative_volumes.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_neg_volumes')}</Text>
                              <Text type="secondary" className="ml-2">{t('dm_n_records', { n: qualityDetail.details.validity.negative_volumes.length })}</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.invalid_high_low && qualityDetail.details.validity.invalid_high_low.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_invalid_hl')}</Text>
                              <Text type="secondary" className="ml-2">{t('dm_n_records', { n: qualityDetail.details.validity.invalid_high_low.length })}</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.invalid_price_logic && qualityDetail.details.validity.invalid_price_logic.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_invalid_price_logic')}</Text>
                              <Text type="secondary" className="ml-2">{t('dm_n_records', { n: qualityDetail.details.validity.invalid_price_logic.length })}</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.abnormal_price_changes && qualityDetail.details.validity.abnormal_price_changes.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-warning)' }}>{t('dm_abnormal_change')}</Text>
                              <div className="mt-2" style={{ maxHeight: 200, overflow: 'auto' }}>
                                {qualityDetail.details.validity.abnormal_price_changes.map((item, index: number) => (
                                  <div key={index} className="mb-1 text-xs">
                                    <span className="qc-mono">{item.timestamp}</span>
                                    <Text type="secondary" className="ml-2">
                                      {t('dm_change_pct', { v: item.change_pct })}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.validity?.abnormal_volumes && qualityDetail.details.validity.abnormal_volumes.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-warning)' }}>{t('dm_abnormal_volume')}</Text>
                              <div className="mt-2" style={{ maxHeight: 200, overflow: 'auto' }}>
                                {qualityDetail.details.validity.abnormal_volumes.map((item, index: number) => (
                                  <div key={index} className="mb-1 text-xs">
                                    <span className="qc-mono">{item.timestamp}</span>
                                    <Text type="secondary" className="ml-2">
                                      {t('dm_volume_30d', { v: item.volume, avg: item.avg_30d_volume })}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.validity?.price_gaps && qualityDetail.details.validity.price_gaps.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-warning)' }}>{t('dm_price_gaps')}</Text>
                              <div className="mt-2" style={{ maxHeight: 200, overflow: 'auto' }}>
                                {qualityDetail.details.validity.price_gaps.map((item, index: number) => (
                                  <div key={index} className="mb-1 text-xs">
                                    <span className="qc-mono">{item.timestamp}</span>
                                    <Text type="secondary" className="ml-2">
                                      {t('dm_gap_pct', { v: item.gap_pct })}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'consistency',
                      label: t('dm_tab_consistency'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.consistency?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                          </Row>
                          {qualityDetail.details.consistency?.time_format_issues && qualityDetail.details.consistency.time_format_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_time_format_issues')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.consistency.time_format_issues.map((issue: string, index: number) => (
                                  <div key={index} className="mb-1">
                                    <span className="qc-chip down qc-mono">{issue}</span>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.duplicate_codes && qualityDetail.details.consistency.duplicate_codes.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_dup_codes')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.consistency.duplicate_codes.map((code: string, index: number) => (
                                  <span key={index} className="qc-chip down qc-mono mb-1">{code}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.code_name_mismatches && qualityDetail.details.consistency.code_name_mismatches.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_code_name_mismatch')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.consistency.code_name_mismatches.map((mismatch: string, index: number) => (
                                  <span key={index} className="qc-chip warn qc-mono mb-1">{mismatch}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.inconsistent_adj_factors && qualityDetail.details.consistency.inconsistent_adj_factors.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_adj_factor_mismatch')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.consistency.inconsistent_adj_factors.map((issue: string, index: number) => (
                                  <span key={index} className="qc-chip warn qc-mono mb-1">{issue}</span>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'logic',
                      label: t('dm_tab_logic'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.logic?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                          </Row>
                          {qualityDetail.details.logic?.trading_time_issues && qualityDetail.details.logic.trading_time_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_trading_time_issues')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.logic.trading_time_issues.map((issue: string, index: number) => (
                                  <span key={index} className="qc-chip down qc-mono mb-1">{issue}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.logic?.suspension_issues && qualityDetail.details.logic.suspension_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_suspension_issues')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.logic.suspension_issues.map((issue: string, index: number) => (
                                  <span key={index} className="qc-chip warn qc-mono mb-1">{issue}</span>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.logic?.price_limit_issues && qualityDetail.details.logic.price_limit_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Text strong style={{ color: 'var(--qc-error)' }}>{t('dm_price_limit_issues')}</Text>
                              <div className="mt-2">
                                {qualityDetail.details.logic.price_limit_issues.map((issue: string, index: number) => (
                                  <span key={index} className="qc-chip down qc-mono mb-1">{issue}</span>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'coverage',
                      label: t('dm_tab_coverage'),
                      children: (
                        <Space orientation="vertical" className="w-full">
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>{t('dm_status_label')}</Text> {qualityDetail.details.coverage?.status === 'pass' ? <span className="qc-chip ok">{t('dm_q_pass')}</span> : <span className="qc-chip down">{t('dm_q_fail')}</span>}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_data_start_date')}</Text> {qualityDetail.details.coverage?.data_start_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_data_end_date')}</Text> {qualityDetail.details.coverage?.data_end_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_expected_start')}</Text> {qualityDetail.details.coverage?.expected_start_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>{t('dm_expected_end')}</Text> {qualityDetail.details.coverage?.expected_end_date || '-'}
                            </Col>
                          </Row>
                          {qualityDetail.details.coverage?.missing_historical_data && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Alert
                                title={t('dm_missing_history_t')}
                                description={t('dm_missing_history_d', { n: qualityDetail.details.coverage?.historical_gap_days || 0 })}
                                type="warning"
                                showIcon
                              />
                            </>
                          )}
                          {qualityDetail.details.coverage?.missing_future_data && (
                            <>
                              <Divider style={{ margin: 'var(--spacing-qc-3) 0' }} />
                              <Alert
                                title={t('dm_missing_future_t')}
                                description={t('dm_missing_future_d', { n: qualityDetail.details.coverage?.future_gap_days || 0 })}
                                type="warning"
                                showIcon
                              />
                            </>
                          )}
                        </Space>
                      ),
                    },
                  ]}
                />
              )}
            </Space>
          ) : (
            <QcEmpty
              icon={<BarChartOutlined />}
              title={t('dm_empty_pick_check')}
              description={t('dm_quick_check')}
            />
          )}
        </Card>
      </Col>
    </Row>
  );

  // 处理 Tab 切换 - 更新 URL 参数
  const handleTabChange = (key: string) => {
    setActiveTab(key);
    // 更新 URL 参数，保留其他参数
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', key);
    setSearchParams(newParams);
  };

  return (
    <PageContainer
      title={t('data_management')}
      subtitle={t('dm_subtitle', { types: Object.keys(DATA_KIND_LABEL).length, symbols: symbols.length })}
    >
      {/* 首屏两块只读卡（数据源水位 + 存储用量）：四个页签下都可见，demo #view-data 1979-2047 */}
      <ArchiveWatermarkStrip />
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'symbols',
            label: t('symbols'),
            children: renderSymbolList(),
          },
          {
            key: 'collection',
            label: t('data_collection'),
            children: renderCollection(),
          },
          {
            key: 'quality',
            label: t('data_quality'),
            children: renderQuality(),
          },
          {
            key: 'archive',
            label: t('dm_archive_browse_title'),
            children: renderArchiveBrowser(),
          },
        ]}
      />
      
      {renderGroupDrawer()}
      {renderGroupModal()}
      {renderBatchAddModal()}
      {renderCleanDataModal()}
    </PageContainer>
  );
};

export default DataManagementPage;
