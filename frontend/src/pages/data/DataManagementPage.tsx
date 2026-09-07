/**
 * 统一数据管理页面 - 多自选组管理优化版
 * 整合数据池、数据采集、数据质量三个核心功能模块
 * 支持多自选组管理（创建、命名、编辑、删除）
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, useLocation } from 'react-router-dom';
import {
  Card,
  Tabs,
  Table,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Badge,
  Progress,
  Form,
  DatePicker,
  Empty,
  Switch,
  Divider,
  Typography,
  Row,
  Col,
  Statistic,
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
  Grid,
  Alert,
  App,
  Descriptions,
} from 'antd';
import {
  StarOutlined,
  StarFilled,
  DownloadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
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
  AppstoreOutlined,
  UnorderedListOutlined,
  SettingOutlined,
  ImportOutlined,
  FileSearchOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { dataApi } from '@/api/dataApi';
import { archiveApi } from '@/api/archiveApi';
import { derivApi } from '@/api/derivApi';
import { wsService } from '@/services/websocketService';
import { useConfigStore } from '@/store';
import type {
  Task,
  TaskStatus,
  ArchiveKind,
  MarketType,
  ArchiveMeta,
  ArchiveRow,
  DerivKind,
} from '@/types/data';
import {
  ARCHIVE_KINDS,
  KLINE_ARCHIVE_KINDS,
  ARCHIVE_MARKETS,
  ARCHIVE_INTERVALS,
  DERIV_KINDS,
  DATA_KIND_LABEL,
  INTERVAL_REQUIRED_KINDS,
} from '@/types/data';
import { setPageTitle } from '@/utils/pageTitle';

const { Text } = Typography;
const { RangePicker } = DatePicker;
const { Search } = Input;
const { useBreakpoint } = Grid;

// ==================== 采集任务状态/格式常量 ====================

const TASK_STATUS_CONFIG: Record<TaskStatus, { color: string; label: string; badge: 'processing' | 'success' | 'error' | 'default' | 'warning' }> = {
  running: { color: '#1677ff', label: '运行中', badge: 'processing' },
  completed: { color: '#52c41a', label: '已完成', badge: 'success' },
  failed: { color: '#ff4d4f', label: '失败', badge: 'error' },
  pending: { color: '#d9d9d9', label: '等待中', badge: 'default' },
  canceled: { color: '#faad14', label: '已取消', badge: 'warning' },
};

/** 数据类型 → 标签颜色 */
const DATA_TYPE_TAG_COLOR: Record<string, string> = {
  kline: 'blue',
  aggTrades: 'cyan',
  trades: 'geekblue',
  bookDepth: 'purple',
  bookTicker: 'magenta',
  markPriceKlines: 'orange',
  indexPriceKlines: 'gold',
  premiumIndexKlines: 'lime',
  fundingRate: 'green',
  openInterest: 'volcano',
};

/** 市场 → 标签颜色 */
const MARKET_TAG_COLOR: Record<string, string> = {
  spot: 'blue',
  um: 'orange',
  cm: 'purple',
};

// 任务卡片组件
interface TaskCardProps {
  task: Task;
  isCurrent: boolean;
  taskProgressList?: any[];
  isProgressExpanded?: boolean;
  setIsProgressExpanded?: (expanded: boolean) => void;
}

const TaskCard: React.FC<TaskCardProps> = ({
  task,
  isCurrent,
  taskProgressList: externalProgressList = [],
  isProgressExpanded = false,
  setIsProgressExpanded,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [details, setDetails] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const displayList = externalProgressList.length > 0 ? externalProgressList : details;
  const statusCfg = TASK_STATUS_CONFIG[task.status] || TASK_STATUS_CONFIG.pending;
  const progress = task.progress || { percentage: 0, total: 0, completed: 0, failed: 0, current: '' };

  // 从 params 提取数据类型和市场
  const dataType: string = task.params?.data_type || task.params?.dataType || 'kline';
  const market: string = task.params?.market || task.params?.candle_type || 'spot';
  const dataTypeLabel = DATA_KIND_LABEL[dataType as keyof typeof DATA_KIND_LABEL] || dataType;

  // 获取任务详情
  const fetchTaskDetails = async () => {
    if (task.task_id) {
      setLoading(true);
      try {
        const data = await dataApi.getTaskDetails(task.task_id);
        if (data?.details) {
          setDetails(data.details);
        }
      } catch (error) {
        console.error('获取任务详情失败:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleExpand = async () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    if (newExpanded && details.length === 0) {
      await fetchTaskDetails();
    }
  };

  return (
    <Card
      size="small"
      style={{
        marginBottom: 8,
        borderLeft: `3px solid ${statusCfg.color}`,
        opacity: task.status === 'completed' ? 0.85 : 1,
      }}
    >
      {/* 第一行：类型/来源徽章 + 状态 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 6 }}>
        <Space size={4} wrap>
          <Tag color={DATA_TYPE_TAG_COLOR[dataType] || 'default'} style={{ margin: 0 }}>
            {dataTypeLabel}
          </Tag>
          <Tag color={MARKET_TAG_COLOR[market] || 'default'} style={{ margin: 0 }}>
            {market.toUpperCase()}
          </Tag>
          {isCurrent && <Tag color="blue" style={{ margin: 0 }}>当前</Tag>}
        </Space>
        <Badge status={statusCfg.badge} text={<Text style={{ fontSize: 12, color: statusCfg.color }}>{statusCfg.label}</Text>} />
      </Row>

      {/* 第二行：进度条 + 数量统计 */}
      <Progress
        percent={progress.percentage || 0}
        size="small"
        status={task.status === 'failed' ? 'exception' : task.status === 'running' ? 'active' : undefined}
        format={(percent) => `${percent?.toFixed(1) || '0.0'}%`}
      />
      {(progress.total > 0 || progress.completed > 0) && (
        <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
          已完成 {progress.completed}/{progress.total}
          {progress.failed > 0 && <Text type="danger" style={{ fontSize: 11, marginLeft: 8 }}>失败 {progress.failed}</Text>}
          {progress.current && <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>正在: {progress.current}</Text>}
        </div>
      )}

      {/* 第三行：时间信息 */}
      <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
        <Space size={12}>
          <span>创建: {task.created_at ? dayjs(task.created_at).format('MM-DD HH:mm') : '-'}</span>
          {task.start_time && <span>开始: {dayjs(task.start_time).format('HH:mm:ss')}</span>}
          {task.end_time && <span>结束: {dayjs(task.end_time).format('HH:mm:ss')}</span>}
        </Space>
      </div>

      {/* 错误信息 */}
      {task.status === 'failed' && task.error_message && (
        <Alert
          type="error"
          showIcon
          message={task.error_message}
          style={{ marginTop: 6, padding: '4px 8px', fontSize: 12 }}
          banner
        />
      )}

      {/* 展开/收起子任务 */}
      <Button
        type="link"
        size="small"
        onClick={handleExpand}
        style={{ padding: 0, marginTop: 4, fontSize: 12 }}
        loading={loading}
      >
        {expanded ? '收起详情' : `子任务详情 (${displayList.length || '...'})`}
      </Button>

      {expanded && (
        <div style={{ marginTop: 8, padding: '8px 12px', background: '#fafafa', borderRadius: 6 }}>
          {displayList.length > 0 ? (
            <>
              {displayList.slice(0, isProgressExpanded ? undefined : 5).map((subTask: any) => (
                <div key={subTask.task_key || subTask.symbol} style={{ marginBottom: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                    <Space size={4}>
                      <Text style={{ fontSize: 12, fontWeight: 500 }}>{subTask.symbol}</Text>
                      {subTask.interval && <Tag style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{subTask.interval}</Tag>}
                    </Space>
                    <Text style={{ fontSize: 11, color: '#8c8c8c' }}>{subTask.percentage?.toFixed(1)}%</Text>
                  </div>
                  <Progress
                    percent={subTask.percentage || 0}
                    size="small"
                    showInfo={false}
                    status={task.status === 'running' && subTask.percentage < 100 ? 'active' : undefined}
                    strokeColor={subTask.percentage >= 100 ? '#52c41a' : undefined}
                  />
                </div>
              ))}
              {displayList.length > 5 && setIsProgressExpanded && (
                <Button
                  type="link"
                  size="small"
                  onClick={() => setIsProgressExpanded(!isProgressExpanded)}
                  style={{ padding: 0, fontSize: 12 }}
                >
                  {isProgressExpanded ? '收起' : `展开全部 (${displayList.length} 个)`}
                </Button>
              )}
            </>
          ) : (
            <Empty description="暂无子任务详情" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
          )}
        </div>
      )}
    </Card>
  );
};

// 系统配置
const SYSTEM_CONFIG = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot',
};

// 分页选项（与系统配置一致）
const PAGE_SIZE_OPTIONS = ['10', '15', '20', '30', '50', '100'];

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

// 视图类型
type ViewType = 'list' | 'card';

// 排序字段
 type SortField = 'symbol' | 'price' | 'change' | 'volume' | 'marketCap' | 'rank';
 type SortOrder = 'asc' | 'desc';

/**
 * 统一数据管理页面组件
 */
const DataManagementPage = () => {
  const { t } = useTranslation();
  const screens = useBreakpoint();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message } = App.useApp();

  const location = useLocation();
  const getDefaultPageSize = useConfigStore((state: { getDefaultPageSize: () => number }) => state.getDefaultPageSize);

  // 从路由状态恢复页面状态
  const restoredState = location.state as { pageState?: Record<string, any> } | null;

  // 从 URL 参数读取 Tab 状态，优先从恢复的状态读取
  const tabFromUrl = searchParams.get('tab');
  const validTab =
    tabFromUrl === 'symbols' ||
    tabFromUrl === 'tasks' ||
    tabFromUrl === 'archive'
      ? tabFromUrl
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
  const [viewType, setViewType] = useState<ViewType>(restoredState?.pageState?.viewType || 'list');
  const [sortField, setSortField] = useState<SortField>(restoredState?.pageState?.sortField || 'rank');
  const [sortOrder, setSortOrder] = useState<SortOrder>(restoredState?.pageState?.sortOrder || 'asc');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(restoredState?.pageState?.selectedSymbols || []);

  // 市场数据加载状态
  const [marketDataLoading, setMarketDataLoading] = useState<Record<string, boolean>>({});

  // 分页状态
  const [currentPage, setCurrentPage] = useState(restoredState?.pageState?.currentPage || 1);
  const [pageSize, setPageSize] = useState(restoredState?.pageState?.pageSize || 10);

  // 从全局配置加载分页大小
  useEffect(() => {
    console.log('[DataManagement] 从全局配置加载分页大小');
    const defaultPageSize = getDefaultPageSize();
    console.log('[DataManagement] 获取到的默认分页大小:', defaultPageSize);
    setPageSize(defaultPageSize);
  }, [getDefaultPageSize]);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('data_management'));
  }, [t]);

  // 页面加载时输出全局配置（用于调试）
  useEffect(() => {
    const configState = useConfigStore.getState();
    console.log('[DataManagement] 页面加载，当前全局配置状态:', configState);
    console.log('[DataManagement] 全局配置详情:', {
      config: configState.config,
      isLoading: configState.isLoading,
      error: configState.error,
    });
    if (configState.config) {
      console.log('[DataManagement] 系统配置项:', Object.keys(configState.config));
      Object.entries(configState.config).forEach(([key, value]) => {
        console.log(`[DataManagement] 配置项 ${key}:`, value);
      });
    }
  }, []);

  // 是否已经获取过市场数据的标志
  const [hasFetchedMarketData, setHasFetchedMarketData] = useState(false);

  // ==================== 数据质量状态 ====================
  const [selectedSymbolForQuality, setSelectedSymbolForQuality] = useState<string>('');
  const [selectedIntervalForQuality, setSelectedIntervalForQuality] = useState<string>('');
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityDetail, setQualityDetail] = useState<any>(null);

  // ==================== 数据清理状态 ====================
  const [cleanForm] = Form.useForm();
  const [cleanLoading, setCleanLoading] = useState(false);
  const [cleanResult, setCleanResult] = useState<any>(null);
  const [isCleanModalOpen, setIsCleanModalOpen] = useState(false);

  // ==================== 数据采集状态 ====================
  const [collectionForm] = Form.useForm();
  // 监听采集表单中的 dataType 变化，用于动态控制 intervals / market 字段
  const collectionDataType = Form.useWatch('dataType', collectionForm) ?? 'kline';
  const [collectionTasks, setCollectionTasks] = useState<Task[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<TaskStatus>('pending');
  const [taskProgress, setTaskProgress] = useState<number>(0);
  // 任务进度列表 - 支持多时间周期多货币对
  const [taskProgressList, setTaskProgressList] = useState<any[]>([]);
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
      let pools: any[] = [];
      if (Array.isArray(response)) {
        pools = response;
      } else if (response && Array.isArray(response.data)) {
        pools = response.data;
      } else if (response && typeof response === 'object') {
        // 尝试从各种可能的字段获取数据
        pools = response.data || response.pools || response.items || [];
      }
      
      console.log('pools:', pools);
      
      if (pools.length > 0) {
        // 转换后端数据格式为前端格式
        const groups: FavoriteGroup[] = await Promise.all(
          pools.map(async (pool: any) => {
            // 获取每个组的资产
            let symbolIds: string[] = [];
            try {
              const assetsResponse = await dataApi.getDataPoolAssets(pool.id);
              console.log(`assets for pool ${pool.id}:`, assetsResponse);
              if (Array.isArray(assetsResponse?.assets)) {
                symbolIds = assetsResponse.assets;
              } else if (Array.isArray(assetsResponse)) {
                symbolIds = assetsResponse;
              }
            } catch (e) {
              console.error(`获取资产失败 pool ${pool.id}:`, e);
            }
            
            return {
              id: pool.id,
              name: pool.name,
              description: pool.description,
              color: pool.color || '#1890ff',
              symbolIds: symbolIds,
              isDefault: pool.is_default || pool.isDefault || false,
              sortOrder: pool.id,
              createdAt: pool.created_at || pool.createdAt,
              updatedAt: pool.updated_at || pool.updatedAt,
            };
          })
        );
        
        console.log('groups:', groups);
        
        setFavoriteGroups(groups);
      } else {
        setFavoriteGroups([]);
      }
    } catch (error) {
      message.error('获取自选组列表失败');
      console.error('获取自选组列表失败:', error);
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
    console.log('[DataManagement] 注册 WebSocket 消息监听');

    const handleTaskProgress = (data: any) => {
      console.log('[DataManagement] 收到任务进度:', data, '当前任务ID:', currentTaskIdRef.current);
      // 使用 ref 获取最新的 currentTaskId，避免闭包问题
      if (data.task_id === currentTaskIdRef.current) {
        const progress = data.progress;
        console.log('[DataManagement] 更新任务进度:', progress?.percentage, progress?.task_key);

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
        console.log('[DataManagement] 任务ID不匹配，忽略:', data.task_id, '!==', currentTaskIdRef.current);
      }
    };

    const handleTaskStatus = (data: any) => {
      console.log('[DataManagement] 收到任务状态:', data);
      // 使用 ref 获取最新的 currentTaskId，避免闭包问题
      if (data.task_id === currentTaskIdRef.current) {
        setTaskStatus(data.status);
        if (data.status === 'completed' || data.status === 'failed') {
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
      const responseData = response?.data || response;
      // 后端返回的是 symbols 字段，不是 items
      const symbolList = responseData?.symbols || responseData?.items || responseData;

      if (symbolList && Array.isArray(symbolList)) {
        const symbolsData: SymbolData[] = symbolList.map((item: any, index: number) => ({
          id: String(item.id || index),
          symbol: item.symbol,
          baseAsset: item.base,
          quoteAsset: item.quote,
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
      message.error('获取货币对列表失败');
      console.error('获取货币对列表失败:', error);
      setSymbols([]);
    } finally {
      setSymbolLoading(false);
    }
  };

  // 获取市场数据（第二步）
  const fetchMarketData = async (symbolList: string[]) => {
    if (!symbolList || symbolList.length === 0) return;

    // 设置所有symbol为加载中
    const loadingMap: Record<string, boolean> = {};
    symbolList.forEach(symbol => {
      loadingMap[symbol] = true;
    });
    setMarketDataLoading(loadingMap);

    try {
      // 分批获取，每批最多100个
      const batchSize = 100;
      const newMarketDataMap: Record<string, any> = {};

      for (let i = 0; i < symbolList.length; i += batchSize) {
        const batch = symbolList.slice(i, i + batchSize);
        const response = await dataApi.getMarketData({
          symbols: batch,
          exchange: SYSTEM_CONFIG.exchange,
        });

        // 处理后端返回的 ApiResponse 格式 { code, message, data: [...] }
        const responseData = response?.data || response;
        const marketDataList = Array.isArray(responseData) ? responseData : [];
        if (marketDataList.length > 0) {
          marketDataList.forEach((data: any) => {
            newMarketDataMap[data.symbol] = data;
          });
        }
      }

      // 更新symbols数据
      setSymbols(prev => prev.map(symbol => {
        const marketData = newMarketDataMap[symbol.symbol];
        if (marketData) {
          return {
            ...symbol,
            price: marketData.price,
            priceChange24h: marketData.price_change_24h,
            priceChangePercent24h: marketData.price_change_percent_24h,
            volume24h: marketData.volume_24h,
            high24h: marketData.high_24h,
            low24h: marketData.low_24h,
            hasData: true,
            dataQuality: 'good',
          };
        }
        return symbol;
      }));
    } catch (error) {
      message.error('获取市场数据失败');
      console.error('获取市场数据失败:', error);
    } finally {
      // 清除加载状态
      setMarketDataLoading({});
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

  // 处理分页变化
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
      message.warning('默认自选组不能删除');
      return;
    }
    try {
      const response = await dataApi.deleteDataPool(groupId);
      if (response.code === 0) {
        message.success('自选组已删除');
        await fetchFavoriteGroups(); // 刷新列表
        if (activeGroupId === groupId) {
          // 删除当前激活的组时，切换到第一个组
          const remainingGroups = favoriteGroups.filter(g => g.id !== groupId);
          if (remainingGroups.length > 0) {
            setActiveGroupId(remainingGroups[0].id);
          }
        }
      } else {
        message.error(response.message || '删除失败');
      }
    } catch (error) {
      message.error('删除自选组失败');
      console.error('删除自选组失败:', error);
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
          message.success('自选组已更新');
          await fetchFavoriteGroups(); // 刷新列表
        } else {
          message.error(response.message || '更新失败');
        }
      } else {
        // 创建新组
        const response = await dataApi.createDataPool({
          name: values.name,
          type: 'crypto',
          description: values.description,
          color: values.color || '#1890ff',
          tags: [],
        });
        // 拦截器只返回 data 字段，判断 pool_id 是否存在表示成功
        if (response && response.pool_id) {
          message.success('自选组已创建');
          await fetchFavoriteGroups(); // 刷新列表
        } else {
          message.error('创建失败');
        }
      }
      
      setIsGroupModalOpen(false);
    } catch (error) {
      console.error('保存自选组失败:', error);
      message.error('保存失败');
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
      message.success('已添加到自选组');
      // 更新本地自选组数据，不等待刷新
      updateGroupAssetCount(groupId, 1);
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error('添加到自选组失败');
      console.error('添加到自选组失败:', error);
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
      message.success('已从自选组移除');
      // 更新本地自选组数据，不等待刷新
      updateGroupAssetCount(groupId, -1);
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error('从自选组移除失败');
      console.error('从自选组移除失败:', error);
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
        message.success(`已添加 ${addedCount} 个，移除 ${removedCount} 个货币对`);
      } else if (addedCount > 0) {
        message.success(`已成功添加 ${addedCount} 个货币对`);
      } else if (removedCount > 0) {
        message.success(`已移除 ${removedCount} 个货币对`);
      } else {
        message.info('未做任何更改');
      }

      // 更新本地自选组数据，不等待刷新
      const delta = addedCount - removedCount;
      if (delta !== 0) {
        updateGroupAssetCount(batchAddTargetGroup.id, delta);
      }
      await fetchFavoriteGroups(); // 刷新列表
    } catch (error) {
      message.error('批量添加失败');
      console.error('批量添加失败:', error);
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

  // 获取采集任务列表（自动恢复正在运行的任务）
  const fetchCollectionTasks = async (silent = false) => {
    if (!silent) setTaskListLoading(true);
    try {
      const params: Record<string, any> = {
        page: 1,
        page_size: 20,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto',
      };
      if (taskStatusFilter !== 'all') {
        params.status = taskStatusFilter;
      }
      const response = await dataApi.getTasks(params);
      const taskList: Task[] = Array.isArray(response.tasks) ? response.tasks : [];
      setCollectionTasks(taskList);

      // 自动检测并恢复正在运行的任务状态
      const runningTask = taskList.find(task =>
        task.status === 'running' || task.status === 'pending'
      );
      if (runningTask && runningTask.task_id) {
        if (!currentTaskIdRef.current) {
          setCurrentTaskId(runningTask.task_id);
          setTaskStatus(runningTask.status);
          setTaskProgress(runningTask.progress?.percentage || 0);
        }
      }
    } catch (error) {
      console.error('获取任务列表失败:', error);
    } finally {
      if (!silent) setTaskListLoading(false);
    }
  };

  // 自动刷新：当有运行中任务时，每 5s 静默刷新任务列表
  useEffect(() => {
    const hasRunning = taskStatus === 'running' || taskStatus === 'pending'
      || collectionTasks.some(t => t.status === 'running' || t.status === 'pending');
    if (!hasRunning) return;
    const timer = setInterval(() => fetchCollectionTasks(true), 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [taskStatus, collectionTasks]);

  // 状态筛选变化时重新拉取
  useEffect(() => {
    fetchCollectionTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [taskStatusFilter]);

  // 开始数据采集
  const startCollection = async (symbol: string) => {
    try {
      const endDate = dayjs();
      const startDate = dayjs().subtract(1, 'month');

      const response = await dataApi.downloadCryptoData({
        symbols: [symbol],
        interval: ['15m', '1h', '1d'],
        start: startDate.format('YYYY-MM-DD'),
        end: endDate.format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 1,
        candle_type: SYSTEM_CONFIG.crypto_trading_mode,
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus('running');
        setTaskProgress(0);
        // 订阅已移至全局，此处不再需要
        fetchCollectionTasks();
        message.success(`已开始采集 ${symbol} 数据`);
      }
    } catch (error) {
      message.error('启动采集任务失败');
      console.error('启动采集任务失败:', error);
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
        message.warning('请至少选择一个货币对');
        return;
      }

      // 仅 K 线类 & 特殊 K 线类（mark/index/premium Klines）需要 interval
      const KLINE_TYPES = new Set(['kline', 'markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines']);
      const interval = KLINE_TYPES.has(dataType)
        ? (values.intervals || ['15m'])
        : [];

      // 衍生数据（fundingRate/openInterest）仅支持 um/cm（Binance 约定）
      const DERIV_TYPES = new Set(['fundingRate', 'openInterest']);
      if (DERIV_TYPES.has(dataType) && market === 'spot') {
        message.warning(`数据类型 ${dataType} 仅支持合约市场（UM/CM）`);
        return;
      }

      const response = await dataApi.downloadCryptoData({
        symbols: selectedSymbols,
        // data_type + market: 新统一入口的两个核心参数
        data_type: dataType,
        market,
        interval,
        start: values.dateRange?.[0]?.format('YYYY-MM-DD') || dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
        end: values.dateRange?.[1]?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 2,
        // 兼容旧字段：K 线时保留 candle_type 以便原有逻辑继续工作
        candle_type: KLINE_TYPES.has(dataType) ? market : undefined,
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus('running');
        setTaskProgress(0);
        fetchCollectionTasks();
        message.success(`采集任务已启动：${dataType} (${market})`);
      }
    } catch (error) {
      message.error('启动批量采集失败');
      console.error('启动批量采集失败:', error);
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
      message.success('数据质量检查完成');
    } catch (error) {
      message.error('数据质量检查失败');
      console.error('数据质量检查失败:', error);
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
      message.success(`数据清理完成，共清理 ${response.deleted_count || 0} 条记录`);
    } catch (error) {
      message.error('数据清理失败');
      console.error('数据清理失败:', error);
    } finally {
      setCleanLoading(false);
    }
  };

  // 获取质量状态标签
  const getQualityTag = (quality?: string) => {
    switch (quality) {
      case 'good':
        return <Tag icon={<CheckCircleOutlined />} color="success">良好</Tag>;
      case 'warning':
        return <Tag icon={<ExclamationCircleOutlined />} color="warning">警告</Tag>;
      case 'bad':
        return <Tag icon={<CloseCircleOutlined />} color="error">异常</Tag>;
      default:
        return <Tag>未检测</Tag>;
    }
  };

  // 获取价格变化颜色
  const getPriceChangeColor = (change: number) => change >= 0 ? '#52c41a' : '#ff4d4f';

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
        label: <Text type="secondary" style={{ fontSize: 12 }}>添加到自选组</Text>,
        disabled: true,
      },
      ...favoriteGroups.map(group => ({
        key: group.id,
        label: (
          <Space>
            <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: group.color }} />
            <span>{group.name}</span>
            {group.symbolIds.includes(symbolId) && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
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
      console.error('获取 symbols 失败:', error);
      message.error('获取 symbols 失败');
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

    try {
      const resp = isDerivKind(kind)
        ? await derivApi.getMeta(kind, market, symbol)
        : await archiveApi.getMeta(kind as ArchiveKind, market, symbol);
      setArchiveMeta(resp?.meta ?? null);
    } catch (error) {
      console.error('读取元数据失败:', error);
    }

    await doArchiveQuery(kind, market, symbol, archiveTimeRange, 1, archivePageSize);
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
      message.warning('请先选择 symbol');
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
      console.error('查询数据失败:', error);
      message.error('查询数据失败');
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
      message.success(`已删除 ${archiveSymbol} 的数据`);
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
      console.error('删除数据失败:', error);
      message.error('删除数据失败');
    } finally {
      setArchiveDeleting(false);
    }
  };

  // 当展开 kind 时，加载其下的 3 个 market 子树（仅 metadata）
  const handleArchiveExpandKind = (kind: ArchiveKind | DerivKind, expanded: boolean) => {
    if (expanded) {
      setArchiveExpandedKinds((prev) => (prev.includes(kind) ? prev : [...prev, kind]));
      // 衍生数据仅支持 um/cm（spot 无意义），故只拉 2 个；archive 拉全 3 个
      const markets: MarketType[] = isDerivKind(kind)
        ? (['um', 'cm'] as MarketType[])
        : ARCHIVE_MARKETS;
      markets.forEach((m) => {
        const key = `${kind}__${m}`;
        if (!archiveSymbolsMap[key]) {
          fetchArchiveSymbols(kind, m);
        }
      });
    } else {
      setArchiveExpandedKinds((prev) => prev.filter((k) => k !== kind));
    }
  };

  // ==================== 渲染方法 ====================

  // 渲染自选组侧边栏
  const renderGroupSidebar = () => (
    <div className="favorite-groups-sidebar" style={{ width: '100%' }}>
      <Card
        size="small"
        title={
          <Space>
            <FolderOutlined />
            <span>{t('favorite_group') || '自选组'}</span>
          </Space>
        }
        extra={
          <Tooltip title={t('manage_watchlist') || '管理自选组'}>
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
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <span>{t('all') || '全部'}</span>
                  <Tag>{symbols.length}</Tag>
                </Space>
              ),
            },
            ...favoriteGroups.map(group => ({
              key: String(group.id),
              icon: <FolderOutlined style={{ color: group.color }} />,
              label: (
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <span>{group.name}</span>
                  <Tag>{group.symbolIds.length}</Tag>
                </Space>
              ),
            })),
          ]}
        />
        
        <Divider style={{ margin: '8px 0' }} />
        
        <Button
          type="dashed"
          block
          icon={<PlusOutlined />}
          onClick={handleCreateGroup}
          style={{ margin: '0 16px', width: 'calc(100% - 32px)' }}
        >
          {t('create_watchlist') || '新建自选组'}
        </Button>
      </Card>
    </div>
  );

  // 渲染组管理抽屉
  const renderGroupDrawer = () => (
    <Drawer
      title={t('manage_watchlist') || '管理自选组'}
      placement="right"
      size={400}
      open={isGroupDrawerOpen}
      onClose={() => setIsGroupDrawerOpen(false)}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateGroup}>
          {t('new') || '新建'}
        </Button>
      }
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        {favoriteGroups.sort((a, b) => a.sortOrder - b.sortOrder).map((group) => (
          <Card
            key={group.id}
            size="small"
            style={{ borderLeft: `4px solid ${group.color}` }}
            actions={[
              <Tooltip key="batch-add" title={t('batch_add_favorite') || '批量添加自选'}>
                <Button
                  type="text"
                  icon={<ImportOutlined />}
                  onClick={(e) => handleOpenBatchAdd(group, e)}
                />
              </Tooltip>,
              <Tooltip key="edit" title={t('edit_watchlist') || '编辑自选组'}>
                <Button
                  type="text"
                  icon={<EditOutlined />}
                  onClick={(e) => handleEditGroup(group, e)}
                />
              </Tooltip>,
              <Popconfirm
                key="delete"
                title={t('confirm_delete') || '确定删除此自选组？'}
                description={t('delete_description') || '组内的货币对不会被删除'}
                onConfirm={(e) => handleDeleteGroup(group.id, e as any)}
                disabled={group.isDefault}
              >
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={group.isDefault}
                />
              </Popconfirm>,
            ]}
          >
            <Card.Meta
              title={
                <Space>
                  <span>{group.name}</span>
                  {group.isDefault && <Tag>{t('default') || '默认'}</Tag>}
                </Space>
              }
              description={
                <Space orientation="vertical" size={0}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {group.description || t('no_description') || '暂无描述'}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {group.symbolIds.length} 个货币对 · 创建于 {group.createdAt}
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
      title={editingGroup ? t('edit_watchlist') || '编辑自选组' : t('create_watchlist') || '新建自选组'}
      open={isGroupModalOpen}
      onOk={handleSaveGroup}
      onCancel={() => setIsGroupModalOpen(false)}
      okText={t('save') || '保存'}
      cancelText={t('cancel') || '取消'}
    >
      <Form form={groupForm} layout="vertical">
        <Form.Item
          name="name"
          label={t('watchlist_name') || '组名称'}
          rules={[{ required: true, message: t('watchlist_name_placeholder') || '请输入组名称' }]}
        >
          <Input placeholder={t('watchlist_name_example') || '例如：小市值、热门币种'} />
        </Form.Item>
        
        <Form.Item
          name="description"
          label={t('watchlist_desc') || '描述'}
        >
          <Input.TextArea rows={2} placeholder={t('watchlist_desc_placeholder') || '可选，描述此自选组的用途'} />
        </Form.Item>
        
        <Form.Item
          name="color"
          label={t('color_tag') || '颜色标识'}
          initialValue="#1890ff"
        >
          <Select
            placeholder={t('color_tag_placeholder') || '选择颜色'}
            options={[
              { value: '#1890ff', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#1890ff', borderRadius: 4 }} />蓝色</Space> },
              { value: '#52c41a', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#52c41a', borderRadius: 4 }} />绿色</Space> },
              { value: '#faad14', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#faad14', borderRadius: 4 }} />黄色</Space> },
              { value: '#f5222d', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#f5222d', borderRadius: 4 }} />红色</Space> },
              { value: '#722ed1', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#722ed1', borderRadius: 4 }} />紫色</Space> },
              { value: '#13c2c2', label: <Space><div style={{ width: 16, height: 16, backgroundColor: '#13c2c2', borderRadius: 4 }} />青色</Space> },
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
        title={
          <Space>
            <ImportOutlined />
            <span>批量添加自选 - {batchAddTargetGroup?.name}</span>
          </Space>
        }
        open={isBatchAddModalOpen}
        onOk={handleConfirmBatchAdd}
        onCancel={handleCloseBatchAdd}
        width={800}
        okText="确认添加"
        cancelText="取消"
        destroyOnHidden
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            已选择 {transferTargetKeys.length} 个货币对，共 {symbols.length} 个可选
          </Text>
        </div>
        <Transfer
          dataSource={transferData}
          titles={['可选货币对', '已选货币对']}
          targetKeys={transferTargetKeys}
          selectedKeys={transferSelectedKeys}
          onChange={handleTransferChange}
          onSelectChange={handleTransferSelectChange}
          render={item => (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <Text strong>{item.title}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text>
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
            searchPlaceholder: t('search_symbol') || '搜索货币对',
            itemUnit: t('item_unit') || '项',
            itemsUnit: t('items_unit') || '项',
            notFoundContent: t('not_found') || '暂无数据',
          }}
        />
      </Modal>
    );
  };

  // 渲染数据清理弹窗
  const renderCleanDataModal = () => (
    <Modal
      title={
        <Space>
          <DeleteOutlined />
          <span>数据清理</span>
        </Space>
      }
      open={isCleanModalOpen}
      onOk={handleCleanData}
      onCancel={() => setIsCleanModalOpen(false)}
      width={600}
      okText="开始清理"
      cancelText="取消"
      confirmLoading={cleanLoading}
      okButtonProps={{ danger: true }}
    >
      <Alert
        message="警告"
        description="数据清理操作不可恢复，请谨慎操作！"
        type="warning"
        showIcon
        style={{ marginBottom: 24 }}
      />
      <Form
        form={cleanForm}
        layout="vertical"
      >
        <Form.Item
          name="symbol"
          label="货币对"
          rules={[{ required: true, message: '请选择货币对' }]}
        >
          <Select
            showSearch
            placeholder="选择要清理的货币对"
            options={symbols.map(s => ({ value: s.symbol, label: s.symbol }))}
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>

        <Form.Item
          name="interval"
          label="时间周期"
        >
          <Select
            allowClear
            placeholder="选择时间周期（为空则清理所有周期）"
            options={[
              { value: '1m', label: '1分钟' },
              { value: '5m', label: '5分钟' },
              { value: '15m', label: '15分钟' },
              { value: '1h', label: '1小时' },
              { value: '4h', label: '4小时' },
              { value: '1d', label: '1天' },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="dateRange"
          label="时间范围"
        >
          <DatePicker.RangePicker
            style={{ width: '100%' }}
            placeholder={['开始日期', '结束日期']}
          />
        </Form.Item>

        <Form.Item
          name="cleanType"
          label="清理类型"
          initialValue="all"
          rules={[{ required: true, message: '请选择清理类型' }]}
        >
          <Select
            placeholder="选择清理类型"
            options={[
              { value: 'all', label: '全部数据（清空指定范围的所有数据）' },
              { value: 'duplicates', label: '仅重复数据（保留第一条，删除重复）' },
              { value: 'invalid', label: '仅无效数据（负价格、负成交量、高低价异常等）' },
            ]}
          />
        </Form.Item>
      </Form>

      {cleanResult && (
        <>
          <Divider style={{ margin: '24px 0' }} />
          <Alert
            message="清理结果"
            description={
              <Space orientation="vertical">
                <Text>货币对: {cleanResult.symbol}</Text>
                <Text>时间周期: {cleanResult.interval || '全部'}</Text>
                <Text>清理类型: {cleanResult.clean_type}</Text>
                <Text>清理前记录数: {cleanResult.total_before}</Text>
                <Text strong style={{ color: '#ff4d4f' }}>已清理记录数: {cleanResult.deleted_count}</Text>
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

  // 渲染左侧树形导航（archive 7 种 + deriv 2 种 → market → symbols）
  const renderArchiveTree = () => {
    const kinds = archiveBrowserCategory === 'archive' ? ARCHIVE_KINDS : DERIV_KINDS;
    const marketsForKind = (k: ArchiveKind | DerivKind): MarketType[] =>
      isDerivKind(k) ? (['um', 'cm'] as MarketType[]) : ARCHIVE_MARKETS;
    const searchLower = archiveSymbolSearch.toLowerCase();

    return (
    <div style={{ maxHeight: 600, overflow: 'auto' }}>
      {/* 分类切换：归档数据（7 种） vs 衍生数据（2 种） */}
      <div style={{ marginBottom: 8 }}>
        <Segmented
          block
          size="small"
          value={archiveBrowserCategory}
          onChange={(v) => {
            const cat = v as ArchiveBrowserCategory;
            setArchiveBrowserCategory(cat);
            const firstKind = cat === 'archive' ? ARCHIVE_KINDS[0] : DERIV_KINDS[0];
            setArchiveKind(firstKind);
            setArchiveSymbol('');
            setArchiveExpandedKinds([firstKind]);
          }}
          options={[
            { value: 'archive', label: `行情 (${ARCHIVE_KINDS.length})` },
            { value: 'deriv', label: `指标 (${DERIV_KINDS.length})` },
          ]}
        />
      </div>

      {/* Symbol 搜索框 */}
      <Input
        size="small"
        placeholder="搜索 symbol..."
        prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
        allowClear
        value={archiveSymbolSearch}
        onChange={(e) => setArchiveSymbolSearch(e.target.value)}
        style={{ marginBottom: 8 }}
      />

      {kinds.map((kind) => {
        const expanded = archiveExpandedKinds.includes(kind);
        const kindLabel = (DATA_KIND_LABEL as Record<string, string>)[kind] ?? kind;
        return (
          <div key={kind} style={{ marginBottom: 2 }}>
            <div
              onClick={() => handleArchiveExpandKind(kind, !expanded)}
              style={{
                cursor: 'pointer',
                padding: '5px 8px',
                backgroundColor: expanded ? '#e6f4ff' : 'transparent',
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontWeight: archiveKind === kind ? 600 : 400,
                fontSize: 13,
              }}
            >
              {expanded ? <FolderOpenOutlined /> : <FolderOutlined />}
              <span>{kindLabel}</span>
              {archiveBrowserCategory === 'archive' && KLINE_ARCHIVE_KINDS.includes(kind as ArchiveKind) && (
                <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>K线</Tag>
              )}
              {archiveBrowserCategory === 'deriv' && <Tag color="purple" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>衍生</Tag>}
            </div>
            {expanded && (
              <div style={{ paddingLeft: 14, marginTop: 2 }}>
                {marketsForKind(kind).map((m) => {
                  const key = `${kind}__${m}`;
                  const symList = archiveSymbolsMap[key];
                  // 搜索过滤
                  const filteredSyms = searchLower && symList
                    ? symList.filter(s => s.toLowerCase().includes(searchLower))
                    : symList;
                  return (
                    <div key={m} style={{ marginBottom: 2 }}>
                      <div
                        style={{
                          padding: '3px 6px',
                          backgroundColor: archiveKind === kind && archiveMarket === m ? '#f0f5ff' : 'transparent',
                          borderRadius: 4,
                          fontSize: 12,
                          color: '#666',
                        }}
                      >
                        <FolderOutlined style={{ marginRight: 4 }} />
                        {m.toUpperCase()}
                        <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                          {symList ? `(${searchLower && filteredSyms ? `${filteredSyms.length}/${symList.length}` : symList.length})` : '...'}
                        </Text>
                      </div>
                      {filteredSyms && filteredSyms.length > 0 && (
                        <div style={{ paddingLeft: 12, maxHeight: 180, overflow: 'auto' }}>
                          {filteredSyms.slice(0, 100).map((s) => (
                            <div
                              key={s}
                              onClick={() => handleArchiveSelectSymbol(kind, m, s)}
                              style={{
                                cursor: 'pointer',
                                padding: '2px 6px',
                                fontSize: 12,
                                backgroundColor:
                                  archiveKind === kind && archiveMarket === m && archiveSymbol === s
                                    ? '#bae0ff'
                                    : 'transparent',
                                borderRadius: 3,
                                color:
                                  archiveKind === kind && archiveMarket === m && archiveSymbol === s
                                    ? '#1677ff'
                                    : '#333',
                              }}
                            >
                              {s}
                            </div>
                          ))}
                          {filteredSyms.length > 100 && (
                            <Text type="secondary" style={{ fontSize: 11, padding: '2px 6px' }}>
                              还有 {filteredSyms.length - 100} 个，请搜索缩小范围
                            </Text>
                          )}
                        </div>
                      )}
                      {searchLower && symList && filteredSyms && filteredSyms.length === 0 && (
                        <Text type="secondary" style={{ fontSize: 11, paddingLeft: 12 }}>无匹配</Text>
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
      };
    });
  }, [archiveRows]);

  // 渲染主面板（统一浏览器：归档7种 + 衍生2种）
  const renderArchiveBrowser = () => {
    const kindLabel = (DATA_KIND_LABEL as Record<string, string>)[archiveKind as string] ?? archiveKind;
    // 仅当 kind 是需要 interval 的 K 线类时显示 interval selector
    const needInterval = INTERVAL_REQUIRED_KINDS.includes(archiveKind as any);
    return (
    <Row gutter={[16, 16]}>
      {/* 左侧树形导航 */}
      <Col xs={24} md={8} lg={6}>
        <Card
          size="small"
          title={
            <Space>
              <DatabaseOutlined />
              <span>历史行情浏览</span>
            </Space>
          }
          extra={
            <Text type="secondary" style={{ fontSize: 11 }}>
              {archiveSymbolsLoading ? '加载中...' : ''}
            </Text>
          }
        >
          {renderArchiveTree()}
        </Card>
      </Col>

      {/* 右侧内容 */}
      <Col xs={24} md={16} lg={18}>
        <Card
          size="small"
          title={
            archiveSymbol ? (
              <Space wrap>
                <Tag color="blue">{kindLabel}</Tag>
                <Tag color="purple">{archiveMarket}</Tag>
                <Text strong>{archiveSymbol}</Text>
                {needInterval && (
                  <Tag color="cyan">{archiveInterval}</Tag>
                )}
                {isDerivKind(archiveKind as DerivKind) && <Tag color="magenta">衍生</Tag>}
              </Space>
            ) : (
              <span>
                <FileSearchOutlined /> 请在左侧选择 (kind / market / symbol)
              </span>
            )
          }
          extra={
            archiveSymbol ? (
              <Popconfirm
                title={`确定删除 ${archiveSymbol} 的 ${kindLabel} 数据？`}
                description="此操作不可恢复"
                okText="确定删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={handleArchiveDelete}
              >
                <Button
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  loading={archiveDeleting}
                >
                  删除该 symbol
                </Button>
              </Popconfirm>
            ) : null
          }
        >
          {!archiveSymbol ? (
            <Empty
              description={
                <Space orientation="vertical" size={4}>
                  <Text type="secondary">请在左侧选择数据浏览</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    步骤：展开数据种类 → 选择市场 → 点击 symbol
                  </Text>
                </Space>
              }
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ padding: '48px 0' }}
            />
          ) : (
            <Space orientation="vertical" style={{ width: '100%' }} size="middle">
              {/* 元数据概览 */}
              {archiveMeta && (
                <Descriptions size="small" column={{ xs: 2, sm: 4 }} bordered={false} style={{ background: '#fafafa', padding: '8px 12px', borderRadius: 6 }}>
                  <Descriptions.Item label="数据起始">{archiveMeta.earliest_date}</Descriptions.Item>
                  <Descriptions.Item label="数据结束">{archiveMeta.latest_date}</Descriptions.Item>
                  <Descriptions.Item label="总行数">{archiveMeta.total_rows.toLocaleString()}</Descriptions.Item>
                  <Descriptions.Item label="文件数">{archiveMeta.file_count}</Descriptions.Item>
                </Descriptions>
              )}
              {archiveMeta && archiveMeta.corrupt_dates.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message={`损坏日期: ${archiveMeta.corrupt_dates.length} 个`}
                  description={archiveMeta.corrupt_dates.slice(0, 10).join(', ')}
                  style={{ fontSize: 12 }}
                />
              )}

              {/* bookDepth 大数据量警告 */}
              {archiveKind === 'bookDepth' && (
                <Alert
                  type="warning"
                  showIcon
                  message="bookDepth 数据量较大"
                  description="单天可展平为千万行，请缩小时间范围（建议 ≤ 1 天）"
                />
              )}

              {/* 查询控件 */}
              <Space wrap size={8} align="center">
                {/* 快捷时间预设 */}
                <Segmented
                  size="small"
                  value=""
                  onChange={(v) => {
                    const end = Date.now();
                    const ranges: Record<string, number> = { '1d': 86400_000, '7d': 7 * 86400_000, '30d': 30 * 86400_000, 'all': 365 * 86400_000 };
                    const ms = ranges[v as string] || 7 * 86400_000;
                    setArchiveTimeRange([end - ms, end]);
                  }}
                  options={[
                    { value: '1d', label: '近1天' },
                    { value: '7d', label: '近7天' },
                    { value: '30d', label: '近30天' },
                    { value: 'all', label: '近1年' },
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
                  查询
                </Button>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  共 {archiveTotal.toLocaleString()} 行
                  {archiveTruncated && '（已截断）'}
                </Text>
              </Space>

              {/* 数据表 */}
              <Table
                size="small"
                rowKey={(_r, idx) => String(idx)}
                dataSource={archiveRows}
                columns={archiveColumns}
                loading={archiveQueryLoading}
                scroll={{ x: 'max-content', y: 480 }}
                pagination={{
                  current: archivePage,
                  pageSize: archivePageSize,
                  total: archiveTotal,
                  showSizeChanger: true,
                  size: 'small',
                  pageSizeOptions: [100, 200, 500, 1000],
                  showTotal: (t) => `共 ${t.toLocaleString()} 行`,
                  onChange: (p, s) => {
                    setArchivePage(p);
                    setArchivePageSize(s);
                    doArchiveQuery(archiveKind, archiveMarket, archiveSymbol, archiveTimeRange, p, s);
                  },
                }}
                bordered
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
      message.warning('请先选择货币对');
      return;
    }
    setSymbols(prev =>
      prev.map(s => selectedSymbols.includes(s.symbol) ? { ...s, autoUpdate: true } : s)
    );
    message.success(`已开启 ${selectedSymbols.length} 个货币对的自动更新`);
  };

  // 批量关闭自动更新
  const batchDisableAutoUpdate = () => {
    if (selectedSymbols.length === 0) {
      message.warning('请先选择货币对');
      return;
    }
    setSymbols(prev =>
      prev.map(s => selectedSymbols.includes(s.symbol) ? { ...s, autoUpdate: false } : s)
    );
    message.success(`已关闭 ${selectedSymbols.length} 个货币对的自动更新`);
  };

  // 批量采集数据
  const batchCollectData = () => {
    if (selectedSymbols.length === 0) {
      message.warning('请先选择货币对');
      return;
    }
    // 这里可以实现批量采集逻辑
    message.info(`批量采集功能开发中，已选择 ${selectedSymbols.length} 个货币对`);
  };

  // 清空选择
  const clearSelection = () => {
    setSelectedSymbols([]);
  };

  const renderSymbolToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索（左） + 视图切换（右） */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={16} sm={16} md={12} lg={10}>
          <Search
            placeholder={t('search_symbol') || '搜索货币对'}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={8} sm={8} md={12} lg={14} style={{ textAlign: 'right' }}>
          <Segmented
            value={viewType}
            onChange={(value) => setViewType(value as ViewType)}
            options={[
              { value: 'list', icon: <UnorderedListOutlined />, label: screens.sm ? t('list_view') || '列表' : undefined },
              { value: 'card', icon: <AppstoreOutlined />, label: screens.sm ? t('card_view') || '卡片' : undefined },
            ]}
          />
        </Col>
      </Row>

      {/* 批量操作工具栏 - 当有选中项时显示 */}
      {selectedSymbols.length > 0 && (
        <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
          <Col xs={24}>
            <Card size="small" style={{ backgroundColor: '#f6ffed', borderColor: '#b7eb8f' }}>
              <Row align="middle" justify="space-between">
                <Col>
                  <Space>
                    <span style={{ color: '#52c41a', fontWeight: 500 }}>
                      已选择 {selectedSymbols.length} 个货币对
                    </span>
                    <Button type="link" size="small" onClick={clearSelection}>
                      {t('clear_selection') || '清空选择'}
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
                      {t('batch_enable_auto_update') || '批量开启自动更新'}
                    </Button>
                    <Button
                      size="small"
                      icon={<CloseCircleOutlined />}
                      onClick={batchDisableAutoUpdate}
                    >
                      {t('batch_disable_auto_update') || '批量关闭自动更新'}
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      icon={<CloudDownloadOutlined />}
                      onClick={batchCollectData}
                    >
                      {t('batch_collection') || '批量采集'}
                    </Button>
                  </Space>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>
      )}

      {/* 第二行：筛选工具（左） + 刷新按钮（右） */}
      <Row gutter={[12, 12]} align="middle">
        {/* 筛选工具 - 左侧 */}
        <Col xs={24} md={16} lg={14}>
          <Row gutter={[8, 8]}>
            <Col xs={12} sm={12} md={12}>
              <Select
                placeholder={t('quote_currency') || '计价货币'}
                value={quoteFilter}
                onChange={setQuoteFilter}
                style={{ width: '100%' }}
                options={[
                  { value: 'all', label: t('all') || '全部' },
                  { value: 'USDT', label: 'USDT' },
                  { value: 'BTC', label: 'BTC' },
                  { value: 'ETH', label: 'ETH' },
                ]}
              />
            </Col>
            <Col xs={12} sm={12} md={12}>
              <Select
                placeholder={t('sort') || '排序'}
                value={`${sortField}-${sortOrder}`}
                onChange={(value) => {
                  const [field, order] = value.split('-');
                  setSortField(field as SortField);
                  setSortOrder(order as SortOrder);
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'rank-asc', label: t('sort_by_rank') || '按排名' },
                  { value: 'symbol-asc', label: t('sort_by_name_asc') || '名称 A-Z' },
                  { value: 'symbol-desc', label: t('sort_by_name_desc') || '名称 Z-A' },
                  { value: 'price-desc', label: t('sort_by_price_desc') || '价格 高-低' },
                  { value: 'price-asc', label: t('sort_by_price_asc') || '价格 低-高' },
                  { value: 'change-desc', label: t('sort_by_change_desc') || '涨幅 高-低' },
                  { value: 'change-asc', label: t('sort_by_change_asc') || '涨幅 低-高' },
                  { value: 'volume-desc', label: t('sort_by_volume_desc') || '成交量 高-低' },
                ]}
              />
            </Col>
          </Row>
        </Col>

        {/* 刷新按钮 - 右侧 */}
        <Col xs={24} md={8} lg={10}>
          <Row gutter={[8, 8]}>
            <Col xs={24} style={{ textAlign: 'right' }}>
              <Button
                icon={<ReloadOutlined />}
                onClick={fetchSymbols}
                loading={symbolLoading}
                style={{ width: screens.xs ? '100%' : 'auto' }}
              >
                {t('refresh') || '刷新'}
              </Button>
            </Col>
          </Row>
        </Col>
      </Row>
    </div>
  );

  // 渲染统计卡片
  const renderStatistics = () => (
    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('total_symbols') || '总货币对'}
            value={symbols.length}
            prefix={<DatabaseOutlined />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('current_group') || '当前组'}
            value={activeGroup?.symbolIds.length || 0}
            prefix={<FolderOpenOutlined style={{ color: activeGroup?.color }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('has_data') || '有数据'}
            value={filteredSymbols.filter(s => s.hasData).length}
            prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title={t('auto_update') || '自动更新'}
            value={filteredSymbols.filter(s => s.autoUpdate).length}
            prefix={<ReloadOutlined style={{ color: '#1890ff' }} />}
          />
        </Card>
      </Col>
    </Row>
  );

  // 检查货币对是否在任何自选组中
  const isSymbolInAnyGroup = (symbolId: string) => {
    return favoriteGroups.some(group => group.symbolIds.includes(symbolId));
  };

  // 获取货币对所在的第一个自选组（用于显示星星颜色）
  const getSymbolFirstGroup = (symbolId: string) => {
    return favoriteGroups.find(group => group.symbolIds.includes(symbolId));
  };

  // 列表视图列定义
  const symbolColumns = [
    {
      title: '',
      key: 'inGroup',
      width: 50,
      render: (_: any, record: SymbolData) => {
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
            <Button
              type="text"
              icon={isInActiveGroup ? <StarFilled style={{ color: displayGroup?.color || '#faad14' }} /> : <StarOutlined />}
              onClick={(e) => e.stopPropagation()}
            />
          </Dropdown>
        );
      },
    },
    {
      title: t('symbol') || '货币对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (text: string, record: SymbolData) => (
        <Space>
          <Text strong>{text}</Text>
          {record.rank && <Tag color="default">#{record.rank}</Tag>}
          {record.hasData && <Badge status="success" />}
        </Space>
      ),
    },
    {
      title: t('latest_price') || '最新价格',
      dataIndex: 'price',
      key: 'price',
      align: 'right' as const,
      render: (price: number | null, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        return price ? <Text strong>${price.toLocaleString()}</Text> : '-';
      },
    },
    {
      title: t('change_24h') || '24h涨跌',
      key: 'change',
      align: 'right' as const,
      render: (_: any, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        if (record.priceChangePercent24h === null) return '-';
        return (
          <Text style={{ color: getPriceChangeColor(record.priceChangePercent24h) }}>
            {record.priceChangePercent24h >= 0 ? '+' : ''}
            {record.priceChangePercent24h.toFixed(2)}%
          </Text>
        );
      },
    },
    {
      title: t('volume_24h') || '24h成交量',
      dataIndex: 'volume24h',
      key: 'volume24h',
      align: 'right' as const,
      render: (volume: number | null, record: SymbolData) => {
        if (marketDataLoading[record.symbol]) {
          return <Spin size="small" />;
        }
        return volume ? formatVolume(volume) : '-';
      },
    },
    {
      title: t('market_cap') || '市值',
      dataIndex: 'marketCap',
      key: 'marketCap',
      align: 'right' as const,
      render: (cap?: number) => cap ? `$${(cap / 1000000000).toFixed(2)}B` : '-',
    },
    {
      title: t('data_status') || '数据状态',
      key: 'dataStatus',
      render: (_: any, record: SymbolData) => (
        <Space>
          {record.hasData ? (
            <>
              {getQualityTag(record.dataQuality)}
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.lastUpdateTime}
              </Text>
            </>
          ) : (
            <Tag>{t('no_data') || '无数据'}</Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('auto_update') || '自动更新',
      key: 'autoUpdate',
      width: 100,
      render: (_: any, record: SymbolData) => (
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
      title: t('action') || '操作',
      key: 'action',
      width: 280,
      render: (_: any, record: SymbolData) => (
        <Space>
          {!record.hasData ? (
            <Button
              type="primary"
              size="small"
              icon={<CloudDownloadOutlined />}
              onClick={() => startCollection(record.symbol)}
            >
              {t('collect') || '采集'}
            </Button>
          ) : (
            <>
              <Button
                size="small"
                icon={<BarChartOutlined />}
                onClick={() => checkQuality(record.symbol, '1h')}
              >
                {t('quality') || '质量'}
              </Button>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => startCollection(record.symbol)}
              >
                {t('update') || '更新'}
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  // 渲染列表视图
  const renderListView = () => (
    <Table
      columns={symbolColumns}
      dataSource={filteredSymbols}
      rowKey="symbol"
      loading={symbolLoading}
      pagination={{
        current: currentPage,
        pageSize: pageSize,
        showSizeChanger: true,
        pageSizeOptions: PAGE_SIZE_OPTIONS,
        showTotal: (total) => `共 ${total} 条`,
        onChange: handlePageChange,
      }}
      scroll={{ x: 1200 }}
      rowSelection={{
        selectedRowKeys: selectedSymbols,
        onChange: (keys) => setSelectedSymbols(keys as string[]),
      }}
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
              title={
                <Space>
                  <Text strong>{symbol.symbol}</Text>
                  {symbol.rank && <Tag>#{symbol.rank}</Tag>}
                </Space>
              }
              extra={
                <Dropdown menu={{ items: getGroupMenuItems(symbol.symbol) }} trigger={['click']}>
                  <Button
                    type="text"
                    size="small"
                    icon={isInActiveGroup ? <StarFilled style={{ color: displayGroup?.color || '#faad14' }} /> : <StarOutlined />}
                  />
                </Dropdown>
              }
              style={{ 
                borderTop: `3px solid ${isInActiveGroup ? displayGroup?.color : 'transparent'}`,
              }}
            >
              <Space orientation="vertical" style={{ width: '100%' }}>
                <Row justify="space-between">
                  <Text type="secondary">价格</Text>
                  {isLoading ? <Spin size="small" /> : (
                    <Text strong style={{ fontSize: 16 }}>
                      {symbol.price ? `$${symbol.price.toLocaleString()}` : '-'}
                    </Text>
                  )}
                </Row>
                <Row justify="space-between">
                  <Text type="secondary">24h涨跌</Text>
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
                  <Text type="secondary">成交量</Text>
                  {isLoading ? <Spin size="small" /> : (
                    <Text>{symbol.volume24h ? formatVolume(symbol.volume24h) : '-'}</Text>
                  )}
                </Row>
                <Divider style={{ margin: '8px 0' }} />
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
                        采集
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        icon={<BarChartOutlined />}
                        onClick={() => checkQuality(symbol.symbol, '1h')}
                      >
                        质量
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
        <Row justify="center" style={{ marginTop: 16 }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={filteredSymbols.length}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(total) => `${t('total_prefix') || '共'} ${total} ${t('items') || '条'}`}
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
        <Card>
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
    const needInterval = INTERVAL_REQUIRED_KINDS.includes(collectionDataType as any);
    // 衍生数据仅支持 um/cm，market 里 spot 要禁用
    const FUTURES_ONLY = new Set(['fundingRate', 'openInterest']);
    const spotDisabled = FUTURES_ONLY.has(collectionDataType);
    // 当前默认 kline + spot，保持与旧行为一致
    return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card title={t('batch_collect') || '批量数据采集（支持全数据类型）'}>
          <Form
            form={collectionForm}
            layout="vertical"
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
              label="数据类型"
              rules={[{ required: true, message: '请选择数据类型' }]}
            >
              <Select
                placeholder="请选择数据类型"
                style={{ width: '100%' }}
                showSearch
                optionFilterProp="label"
                options={[
                  {
                    label: 'K 线数据',
                    options: [
                      { value: 'kline', label: 'Spot / UM / CM 现货及合约K线' },
                      { value: 'markPriceKlines', label: '标记价格K线 (Mark Price)' },
                      { value: 'indexPriceKlines', label: '指数价格K线 (Index Price)' },
                      { value: 'premiumIndexKlines', label: '溢价指数K线 (Premium Index)' },
                    ],
                  },
                  {
                    label: '行情数据',
                    options: [
                      { value: 'aggTrades', label: '聚合成交 (Aggregated Trades)' },
                      { value: 'trades', label: '逐笔成交 (Trades)' },
                      { value: 'bookDepth', label: '订单簿深度 (Book Depth)' },
                      { value: 'bookTicker', label: '最优挂单 (Book Ticker)' },
                    ],
                  },
                  {
                    label: '衍生品指标',
                    options: [
                      { value: 'fundingRate', label: '资金费率 (Funding Rate)' },
                      { value: 'openInterest', label: '持仓量 (Open Interest)' },
                    ],
                  },
                ]}
              />
            </Form.Item>

            {/* 2) 市场选择（spot / um / cm） */}
            <Form.Item
              name="market"
              label="市场"
              rules={[{ required: true, message: '请选择市场' }]}
              tooltip={spotDisabled ? '该数据类型仅支持合约市场（UM/CM）' : undefined}
            >
              <Segmented
                options={[
                  { label: '现货 Spot', value: 'spot', disabled: spotDisabled },
                  { label: 'U本位 UM', value: 'um' },
                  { label: '币本位 CM', value: 'cm' },
                ]}
              />
            </Form.Item>

            {/* 3) symbols 多选 */}
            <Form.Item
              name="symbols"
              label={t('select_symbol_or_group') || '选择货币对'}
              rules={[{ required: true, message: t('please_select_symbol_or_group') || '请至少选择一个货币对或自选组' }]}
            >
              <Select
                mode="multiple"
                placeholder={t('select_symbol_or_group_placeholder') || '请选择货币对或自选组'}
                showSearch
                allowClear
                options={[
                  // 自选组选项
                  ...(favoriteGroups.length > 0 ? [
                    {
                      label: <Text type="secondary" style={{ fontSize: 12 }}>{t('favorite_groups') || '自选组'}</Text>,
                      options: favoriteGroups.map((group) => ({
                        value: `group:${group.id}`,
                        label: `${group.name} (${group.symbolIds?.length || 0}${t('item') || '个'})`,
                      })),
                    }
                  ] : []),
                  // 货币对选项
                  {
                    label: <Text type="secondary" style={{ fontSize: 12 }}>{t('symbols') || '货币对'}</Text>,
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
                label={t('interval') || '时间周期'}
                rules={[{ required: true, message: t('please_select_interval') || '请至少选择一个时间周期' }]}
              >
                <Select
                  mode="multiple"
                  placeholder={t('select_interval_placeholder') || '选择时间周期'}
                  options={[
                    { value: '1m', label: t('interval_1m') || '1分钟' },
                    { value: '5m', label: t('interval_5m') || '5分钟' },
                    { value: '15m', label: t('interval_15m') || '15分钟' },
                    { value: '30m', label: t('interval_30m') || '30分钟' },
                    { value: '1h', label: t('interval_1h') || '1小时' },
                    { value: '4h', label: t('interval_4h') || '4小时' },
                    { value: '1d', label: t('interval_1d') || '1天' },
                  ]}
                />
              </Form.Item>
            )}

            {/* 5) 时间范围 */}
            <Form.Item
              name="dateRange"
              label={t('date_range') || '时间范围'}
              rules={[{ required: true, message: t('please_select_date_range') || '请选择时间范围' }]}
            >
              <RangePicker style={{ width: '100%' }} />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={handleBatchCollection}
                block
              >
                {t('start_batch_collect') || `开始采集 · ${DATA_KIND_LABEL[collectionDataType as keyof typeof DATA_KIND_LABEL] || collectionDataType}`}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card
          title={
            <Space>
              <span>{t('collection_tasks') || '采集任务'}</span>
              <Badge count={collectionTasks.filter(t => t.status === 'running').length} size="small" color="#1677ff" />
            </Space>
          }
          extra={
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={() => fetchCollectionTasks()}
              loading={taskListLoading}
            >
              刷新
            </Button>
          }
        >
          {/* 状态筛选 */}
          <Segmented
            size="small"
            value={taskStatusFilter}
            onChange={(val) => { setTaskStatusFilter(val as string); }}
            options={[
              { label: '全部', value: 'all' },
              { label: '运行中', value: 'running' },
              { label: '已完成', value: 'completed' },
              { label: '失败', value: 'failed' },
            ]}
            style={{ marginBottom: 12 }}
            block
          />

          <Spin spinning={taskListLoading}>
            <div style={{ maxHeight: 560, overflow: 'auto' }}>
              {collectionTasks.length === 0 && !currentTaskId ? (
                <Empty
                  description={taskStatusFilter !== 'all' ? '无匹配该状态的任务' : (t('no_collection_tasks') || '暂无采集任务')}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ padding: '32px 0' }}
                />
              ) : (
                <Space orientation="vertical" style={{ width: '100%' }} size={0}>
                  {/* 当前任务放在最前面 */}
                  {currentTaskId && taskStatusFilter === 'all' || (currentTaskId && taskStatusFilter === taskStatus) ? (
                    <TaskCard
                      task={{
                        task_id: currentTaskId,
                        status: taskStatus,
                        task_type: 'download',
                        params: {},
                        progress: { percentage: taskProgress, total: taskProgressList.length, completed: taskProgressList.filter(t => (t.percentage || 0) >= 100).length, failed: 0, current: '' },
                        created_at: new Date().toISOString(),
                      }}
                      isCurrent={true}
                      taskProgressList={taskProgressList}
                      isProgressExpanded={isProgressExpanded}
                      setIsProgressExpanded={setIsProgressExpanded}
                    />
                  ) : null}
                  {/* 历史任务列表 */}
                  {collectionTasks
                    .filter((task) => task.task_id !== currentTaskId)
                    .map((task) => (
                      <TaskCard key={task.task_id} task={task} isCurrent={false} />
                    ))}
                </Space>
              )}
            </div>
          </Spin>
        </Card>
      </Col>
    </Row>
    );
  };

  // 渲染数据质量
  const renderQuality = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="质量概览">
          <Space orientation="vertical" style={{ width: '100%' }}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="已检测"
                  value={symbols.filter((s) => s.dataQuality !== 'unknown').length}
                  suffix={`/ ${symbols.length}`}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="良好"
                  value={symbols.filter((s) => s.dataQuality === 'good').length}
                  styles={{ content: { color: '#52c41a' } }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="警告"
                  value={symbols.filter((s) => s.dataQuality === 'warning').length}
                  styles={{ content: { color: '#faad14' } }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="异常"
                  value={symbols.filter((s) => s.dataQuality === 'bad').length}
                  styles={{ content: { color: '#ff4d4f' } }}
                />
              </Col>
            </Row>

            <Divider />

            <div>
              <Text strong>快速检测</Text>
              <Select
                placeholder="选择货币对"
                style={{ width: '100%', marginTop: 8 }}
                value={selectedSymbolForQuality || undefined}
                onChange={(value) => setSelectedSymbolForQuality(value)}
                options={symbols
                  .filter((s) => s.hasData)
                  .map((s) => ({ value: s.symbol, label: s.symbol }))}
              />
              <Select
                placeholder="选择周期"
                style={{ width: '100%', marginTop: 8 }}
                value={selectedIntervalForQuality || undefined}
                onChange={(value) => setSelectedIntervalForQuality(value)}
                options={[
                  { value: '1m', label: '1分钟' },
                  { value: '5m', label: '5分钟' },
                  { value: '15m', label: '15分钟' },
                  { value: '1h', label: '1小时' },
                  { value: '4h', label: '4小时' },
                  { value: '1d', label: '1天' },
                ]}
              />
              <Button
                type="primary"
                icon={<BarChartOutlined />}
                style={{ width: '100%', marginTop: 8 }}
                loading={qualityLoading}
                disabled={!selectedSymbolForQuality || !selectedIntervalForQuality}
                onClick={() =>
                  checkQuality(selectedSymbolForQuality, selectedIntervalForQuality)
                }
              >
                开始检测
              </Button>
            </div>

            <Divider />

            <div>
              <Text strong>数据清理</Text>
              <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
                清理指定货币对、周期或时间范围的数据
              </Text>
              <Button
                danger
                icon={<DeleteOutlined />}
                style={{ width: '100%', marginTop: 8 }}
                onClick={handleOpenCleanModal}
              >
                打开清理工具
              </Button>
            </div>
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={16}>
        <Card title="检测结果" loading={qualityLoading}>
          {qualityDetail ? (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Row gutter={[16, 16]}>
                <Col span={8}>
                  <Card size="small">
                    {(() => {
                      const status = qualityDetail.summary?.status;
                      const statusText = status === 'good' || status === 'pass' ? '通过' : status === 'warning' ? '警告' : '失败';
                      const statusColor = status === 'good' || status === 'pass' ? '#52c41a' : status === 'warning' ? '#faad14' : '#ff4d4f';
                      return (
                        <Statistic
                          title="总体状态"
                          value={statusText}
                          styles={{ content: { color: statusColor } }}
                        />
                      );
                    })()}
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small">
                    <Statistic title="总记录数" value={qualityDetail.total_records} />
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small">
                    <Statistic
                      title="质量评分"
                      value={qualityDetail.summary?.score || 0}
                      suffix="分"
                    />
                  </Card>
                </Col>
              </Row>

              {qualityDetail.details && (
                <Tabs
                  type="card"
                  size="small"
                  items={[
                    {
                      key: 'integrity',
                      label: '完整性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.integrity?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                            <Col span={12}>
                              <Text strong>总记录:</Text> {qualityDetail.details.integrity?.total_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.integrity?.missing_columns && qualityDetail.details.integrity.missing_columns.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>缺失列:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.integrity.missing_columns.map((col: string) => (
                                  <Tag key={col} color="error" style={{ marginBottom: 4 }}>{col}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.integrity?.missing_values && Object.keys(qualityDetail.details.integrity.missing_values).length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>缺失值统计:</Text>
                              <div style={{ marginTop: 8 }}>
                                {Object.entries(qualityDetail.details.integrity.missing_values).map(([key, value]: [string, any]) => (
                                  <div key={key} style={{ marginBottom: 4 }}>
                                    <Tag color="warning">{key}</Tag>
                                    <Text type="secondary"> 缺失 {value} 个</Text>
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
                      label: '连续性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.continuity?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                            <Col span={12}>
                              <Text strong>预期记录:</Text> {qualityDetail.details.continuity?.expected_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>实际记录:</Text> {qualityDetail.details.continuity?.actual_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>缺失记录:</Text> {qualityDetail.details.continuity?.missing_records || 0}
                            </Col>
                            <Col span={12}>
                              <Text strong>覆盖率:</Text> {Math.round((qualityDetail.details.continuity?.coverage_ratio || 0) * 100)}%
                            </Col>
                          </Row>
                          {qualityDetail.details.continuity?.missing_time_ranges && qualityDetail.details.continuity.missing_time_ranges.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong>缺失时间段:</Text>
                              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.continuity.missing_time_ranges.map((range: any, index: number) => (
                                  <div key={index} style={{ marginBottom: 4, fontSize: 12 }}>
                                    <Tag style={{ fontSize: 12 }}>{range.start}</Tag> ~ <Tag style={{ fontSize: 12 }}>{range.end}</Tag>
                                    <Text type="secondary" style={{ marginLeft: 8 }}>
                                      缺失 {range.count} 条
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
                      label: '唯一性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.uniqueness?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                            <Col span={12}>
                              <Text strong>重复记录:</Text> {qualityDetail.details.uniqueness?.duplicate_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.uniqueness?.duplicate_periods && qualityDetail.details.uniqueness.duplicate_periods.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong>重复时间段:</Text>
                              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.uniqueness.duplicate_periods.map((period: string, index: number) => (
                                  <Tag key={index} style={{ marginBottom: 4, fontSize: 12 }}>{period}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.uniqueness?.duplicate_details && qualityDetail.details.uniqueness.duplicate_details.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong>重复详情:</Text>
                              <div style={{ maxHeight: 300, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.uniqueness.duplicate_details.map((detail: any, index: number) => (
                                  <Card key={index} size="small" style={{ marginBottom: 8 }}>
                                    <Text strong>时间: {detail.key}</Text>
                                    <Text style={{ marginLeft: 8 }} type="secondary">({detail.count} 条重复)</Text>
                                    <div style={{ marginTop: 8 }}>
                                      {detail.records.map((record: any, rIndex: number) => (
                                        <div key={rIndex} style={{ fontSize: 12, marginBottom: 4, padding: '4px 8px', background: '#f5f5f5', borderRadius: 4 }}>
                                          <Text type="secondary">#{record.row_number}</Text>
                                          <Text style={{ marginLeft: 8 }}>开: {record.open}</Text>
                                          <Text style={{ marginLeft: 8 }}>高: {record.high}</Text>
                                          <Text style={{ marginLeft: 8 }}>低: {record.low}</Text>
                                          <Text style={{ marginLeft: 8 }}>收: {record.close}</Text>
                                          <Text style={{ marginLeft: 8 }}>量: {record.volume}</Text>
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
                      label: '有效性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.validity?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                            <Col span={12}>
                              <Text strong>无效记录总数:</Text> {qualityDetail.details.validity?.total_invalid_records || 0}
                            </Col>
                          </Row>
                          {qualityDetail.details.validity?.negative_prices && qualityDetail.details.validity.negative_prices.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>负价格记录:</Text>
                              <Text type="secondary" style={{ marginLeft: 8 }}>{qualityDetail.details.validity.negative_prices.length} 条</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.negative_volumes && qualityDetail.details.validity.negative_volumes.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>负成交量记录:</Text>
                              <Text type="secondary" style={{ marginLeft: 8 }}>{qualityDetail.details.validity.negative_volumes.length} 条</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.invalid_high_low && qualityDetail.details.validity.invalid_high_low.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>高低价异常记录 (high &lt; low):</Text>
                              <Text type="secondary" style={{ marginLeft: 8 }}>{qualityDetail.details.validity.invalid_high_low.length} 条</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.invalid_price_logic && qualityDetail.details.validity.invalid_price_logic.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>价格逻辑异常记录:</Text>
                              <Text type="secondary" style={{ marginLeft: 8 }}>{qualityDetail.details.validity.invalid_price_logic.length} 条</Text>
                            </>
                          )}
                          {qualityDetail.details.validity?.abnormal_price_changes && qualityDetail.details.validity.abnormal_price_changes.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#faad14' }}>异常涨跌幅记录 (&gt;±20%):</Text>
                              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.validity.abnormal_price_changes.map((item: any, index: number) => (
                                  <div key={index} style={{ marginBottom: 4, fontSize: 12 }}>
                                    <Tag style={{ fontSize: 12 }}>{item.timestamp}</Tag>
                                    <Text type="secondary" style={{ marginLeft: 8 }}>
                                      涨跌幅: {item.change_pct}%
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.validity?.abnormal_volumes && qualityDetail.details.validity.abnormal_volumes.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#faad14' }}>异常成交量记录 (&gt;30日均量10倍):</Text>
                              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.validity.abnormal_volumes.map((item: any, index: number) => (
                                  <div key={index} style={{ marginBottom: 4, fontSize: 12 }}>
                                    <Tag style={{ fontSize: 12 }}>{item.timestamp}</Tag>
                                    <Text type="secondary" style={{ marginLeft: 8 }}>
                                      成交量: {item.volume}, 30日均量: {item.avg_30d_volume}
                                    </Text>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.validity?.price_gaps && qualityDetail.details.validity.price_gaps.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#faad14' }}>价格跳空记录 (&gt;±5%):</Text>
                              <div style={{ maxHeight: 200, overflow: 'auto', marginTop: 8 }}>
                                {qualityDetail.details.validity.price_gaps.map((item: any, index: number) => (
                                  <div key={index} style={{ marginBottom: 4, fontSize: 12 }}>
                                    <Tag style={{ fontSize: 12 }}>{item.timestamp}</Tag>
                                    <Text type="secondary" style={{ marginLeft: 8 }}>
                                      跳空: {item.gap_pct}%
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
                      label: '一致性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.consistency?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                          </Row>
                          {qualityDetail.details.consistency?.time_format_issues && qualityDetail.details.consistency.time_format_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>时间格式问题:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.consistency.time_format_issues.map((issue: string, index: number) => (
                                  <div key={index} style={{ marginBottom: 4 }}>
                                    <Tag color="error">{issue}</Tag>
                                  </div>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.duplicate_codes && qualityDetail.details.consistency.duplicate_codes.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>重复代码:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.consistency.duplicate_codes.map((code: string, index: number) => (
                                  <Tag key={index} color="error" style={{ marginBottom: 4 }}>{code}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.code_name_mismatches && qualityDetail.details.consistency.code_name_mismatches.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>代码名称不匹配:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.consistency.code_name_mismatches.map((mismatch: string, index: number) => (
                                  <Tag key={index} color="warning" style={{ marginBottom: 4 }}>{mismatch}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.consistency?.inconsistent_adj_factors && qualityDetail.details.consistency.inconsistent_adj_factors.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>复权因子不一致:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.consistency.inconsistent_adj_factors.map((issue: string, index: number) => (
                                  <Tag key={index} color="warning" style={{ marginBottom: 4 }}>{issue}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'logic',
                      label: '逻辑性',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.logic?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                          </Row>
                          {qualityDetail.details.logic?.trading_time_issues && qualityDetail.details.logic.trading_time_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>交易时间异常:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.logic.trading_time_issues.map((issue: string, index: number) => (
                                  <Tag key={index} color="error" style={{ marginBottom: 4 }}>{issue}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.logic?.suspension_issues && qualityDetail.details.logic.suspension_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>停牌数据问题:</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.logic.suspension_issues.map((issue: string, index: number) => (
                                  <Tag key={index} color="warning" style={{ marginBottom: 4 }}>{issue}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                          {qualityDetail.details.logic?.price_limit_issues && qualityDetail.details.logic.price_limit_issues.length > 0 && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Text strong style={{ color: '#ff4d4f' }}>涨跌停异常 (&gt;±10.1%):</Text>
                              <div style={{ marginTop: 8 }}>
                                {qualityDetail.details.logic.price_limit_issues.map((issue: string, index: number) => (
                                  <Tag key={index} color="error" style={{ marginBottom: 4 }}>{issue}</Tag>
                                ))}
                              </div>
                            </>
                          )}
                        </Space>
                      ),
                    },
                    {
                      key: 'coverage',
                      label: '覆盖率',
                      children: (
                        <Space orientation="vertical" style={{ width: '100%' }}>
                          <Row gutter={[16, 8]}>
                            <Col span={12}>
                              <Text strong>状态:</Text> {qualityDetail.details.coverage?.status === 'pass' ? <Tag color="success">通过</Tag> : <Tag color="error">失败</Tag>}
                            </Col>
                            <Col span={12}>
                              <Text strong>数据起始日期:</Text> {qualityDetail.details.coverage?.data_start_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>数据结束日期:</Text> {qualityDetail.details.coverage?.data_end_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>预期起始日期:</Text> {qualityDetail.details.coverage?.expected_start_date || '-'}
                            </Col>
                            <Col span={12}>
                              <Text strong>预期结束日期:</Text> {qualityDetail.details.coverage?.expected_end_date || '-'}
                            </Col>
                          </Row>
                          {qualityDetail.details.coverage?.missing_historical_data && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Alert
                                message="缺少历史数据"
                                description={`缺少 ${qualityDetail.details.coverage?.historical_gap_days || 0} 天的历史数据`}
                                type="warning"
                                showIcon
                              />
                            </>
                          )}
                          {qualityDetail.details.coverage?.missing_future_data && (
                            <>
                              <Divider style={{ margin: '12px 0' }} />
                              <Alert
                                message="缺少最新数据"
                                description={`缺少 ${qualityDetail.details.coverage?.future_gap_days || 0} 天的最新数据`}
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
            <Empty description="请选择货币对并点击检测按钮" />
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
    <PageContainer title={t('data_management') || '数据管理'}>
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        type="card"
        items={[
          {
            key: 'symbols',
            label: (
              <span>
                <DatabaseOutlined /> {t('symbols') || '货币对'}
              </span>
            ),
            children: renderSymbolList(),
          },
          {
            key: 'collection',
            label: (
              <span>
                <CloudDownloadOutlined /> {t('data_collection') || '数据采集（全类型）'}
              </span>
            ),
            children: renderCollection(),
          },
          {
            key: 'quality',
            label: (
              <span>
                <BarChartOutlined /> {t('data_quality') || '数据质量'}
              </span>
            ),
            children: renderQuality(),
          },
          {
            key: 'archive',
            label: (
              <span>
                <FileSearchOutlined /> 历史行情浏览
              </span>
            ),
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
