/**
 * 统一数据管理页面 - 多自选组管理优化版
 * 整合数据池、数据采集、数据质量三个核心功能模块
 * 支持多自选组管理（创建、命名、编辑、删除）
 * 参考主流金融工具设计，以货币对为核心展示单位
 */
import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
  message,
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
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

import dayjs from 'dayjs';
import PageContainer from '@/components/PageContainer';
import { dataApi } from '@/api/dataApi';
import { wsService } from '@/services/websocketService';
import type { Task } from '@/types/data';

const { Text } = Typography;
const { TabPane } = Tabs;
const { RangePicker } = DatePicker;
const { Search } = Input;

// 系统配置
const SYSTEM_CONFIG = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot',
};

// 获取全局配置中的默认分页大小
const getDefaultPageSize = () => {
  if (typeof window !== 'undefined' && (window as any).APP_CONFIG?.userSettings?.defaultPerPage) {
    return parseInt((window as any).APP_CONFIG.userSettings.defaultPerPage, 10) || 10;
  }
  return 10;
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
  const [activeTab, setActiveTab] = useState('symbols');

  // ==================== 自选组管理状态 ====================
  const [favoriteGroups, setFavoriteGroups] = useState<FavoriteGroup[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<number>(0);
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
  const [searchText, setSearchText] = useState('');
  const [quoteFilter, setQuoteFilter] = useState<string>('all');
  const [viewType, setViewType] = useState<ViewType>('list');
  const [sortField, setSortField] = useState<SortField>('rank');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);

  // 市场数据加载状态
  const [marketDataLoading, setMarketDataLoading] = useState<Record<string, boolean>>({});

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(getDefaultPageSize());

  // 是否已经获取过市场数据的标志
  const [hasFetchedMarketData, setHasFetchedMarketData] = useState(false);

  // ==================== 数据质量状态 ====================
  const [selectedSymbolForQuality, setSelectedSymbolForQuality] = useState<string>('');
  const [selectedIntervalForQuality, setSelectedIntervalForQuality] = useState<string>('');
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityDetail, setQualityDetail] = useState<any>(null);

  // ==================== 数据采集状态 ====================
  const [collectionForm] = Form.useForm();
  const [collectionTasks, setCollectionTasks] = useState<Task[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [taskProgress, setTaskProgress] = useState<number>(0);
  // 使用 ref 存储最新的 currentTaskId，避免 WebSocket 回调中的闭包问题
  const currentTaskIdRef = useRef<string>('');
  useEffect(() => {
    currentTaskIdRef.current = currentTaskId;
  }, [currentTaskId]);

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
  }, [symbols, searchText, quoteFilter, activeGroupId, activeGroup, sortField, sortOrder]);

  // 初始化加载
  useEffect(() => {
    fetchSymbols();
    fetchFavoriteGroups();
    fetchCollectionTasks();
  }, []);

  // 监听全局配置变化，更新分页大小
  useEffect(() => {
    const checkConfigChange = () => {
      const newPageSize = getDefaultPageSize();
      if (newPageSize !== pageSize) {
        setPageSize(newPageSize);
        setCurrentPage(1); // 重置到第一页
      }
    };

    // 每秒检查一次全局配置变化
    const interval = setInterval(checkConfigChange, 1000);

    // 监听 storage 事件（跨标签页同步）
    const handleStorageChange = () => {
      checkConfigChange();
    };
    window.addEventListener('storage', handleStorageChange);

    return () => {
      clearInterval(interval);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [pageSize]);

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

  // WebSocket 连接
  useEffect(() => {
    console.log('[DataManagement] 初始化 WebSocket 连接');
    wsService.connect();

    const handleTaskProgress = (data: any) => {
      console.log('[DataManagement] 收到任务进度:', data, '当前任务ID:', currentTaskIdRef.current);
      // 使用 ref 获取最新的 currentTaskId，避免闭包问题
      if (data.task_id === currentTaskIdRef.current) {
        console.log('[DataManagement] 更新任务进度:', data.progress?.percentage);
        setTaskProgress(data.progress?.percentage || 0);
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
        if (response.code === 0) {
          message.success('自选组已创建');
          await fetchFavoriteGroups(); // 刷新列表
        } else {
          message.error(response.message || '创建失败');
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

  // 获取采集任务列表
  const fetchCollectionTasks = async () => {
    try {
      const params = {
        page: 1,
        page_size: 10,
        sort_by: 'created_at',
        sort_order: 'desc',
        task_type: 'download_crypto',
      };
      const response = await dataApi.getTasks(params);
      const taskList: Task[] = Array.isArray(response.tasks) ? response.tasks : [];
      setCollectionTasks(taskList);
    } catch (error) {
      console.error('获取任务列表失败:', error);
    }
  };

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
        wsService.subscribe(['task:progress', 'task:status']);
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

      if (selectedSymbols.length === 0) {
        message.warning('请至少选择一个货币对');
        return;
      }

      const response = await dataApi.downloadCryptoData({
        symbols: selectedSymbols,
        interval: values.intervals || ['15m'],
        start: values.dateRange?.[0]?.format('YYYY-MM-DD') || dayjs().subtract(1, 'month').format('YYYY-MM-DD'),
        end: values.dateRange?.[1]?.format('YYYY-MM-DD') || dayjs().format('YYYY-MM-DD'),
        exchange: SYSTEM_CONFIG.exchange,
        max_workers: 2,
        candle_type: SYSTEM_CONFIG.crypto_trading_mode,
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus('running');
        setTaskProgress(0);
        wsService.subscribe(['task:progress', 'task:status']);
        fetchCollectionTasks();
        message.success('批量采集任务已启动');
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

  // ==================== 渲染方法 ====================

  // 渲染自选组侧边栏
  const renderGroupSidebar = () => (
    <div className="favorite-groups-sidebar" style={{ width: 220, flexShrink: 0 }}>
      <Card
        size="small"
        title={
          <Space>
            <FolderOutlined />
            <span>自选组</span>
          </Space>
        }
        extra={
          <Tooltip title="管理自选组">
            <Button
              type="text"
              size="small"
              icon={<SettingOutlined />}
              onClick={() => setIsGroupDrawerOpen(true)}
            />
          </Tooltip>
        }
        style={{ height: '100%' }}
        bodyStyle={{ padding: '8px 0' }}
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
                  <span>全部</span>
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
          新建自选组
        </Button>
      </Card>
    </div>
  );

  // 渲染组管理抽屉
  const renderGroupDrawer = () => (
    <Drawer
      title="管理自选组"
      placement="right"
      width={400}
      open={isGroupDrawerOpen}
      onClose={() => setIsGroupDrawerOpen(false)}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateGroup}>
          新建
        </Button>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        {favoriteGroups.sort((a, b) => a.sortOrder - b.sortOrder).map((group) => (
          <Card
            key={group.id}
            size="small"
            style={{ borderLeft: `4px solid ${group.color}` }}
            actions={[
              <Tooltip key="batch-add" title="批量添加自选">
                <Button
                  type="text"
                  icon={<ImportOutlined />}
                  onClick={(e) => handleOpenBatchAdd(group, e)}
                />
              </Tooltip>,
              <Tooltip key="edit" title="编辑自选组">
                <Button
                  type="text"
                  icon={<EditOutlined />}
                  onClick={(e) => handleEditGroup(group, e)}
                />
              </Tooltip>,
              <Popconfirm
                key="delete"
                title="确定删除此自选组？"
                description="组内的货币对不会被删除"
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
                  {group.isDefault && <Tag>默认</Tag>}
                </Space>
              }
              description={
                <Space direction="vertical" size={0}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {group.description || '暂无描述'}
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
      title={editingGroup ? '编辑自选组' : '新建自选组'}
      open={isGroupModalOpen}
      onOk={handleSaveGroup}
      onCancel={() => setIsGroupModalOpen(false)}
      okText="保存"
      cancelText="取消"
    >
      <Form form={groupForm} layout="vertical">
        <Form.Item
          name="name"
          label="组名称"
          rules={[{ required: true, message: '请输入组名称' }]}
        >
          <Input placeholder="例如：小市值、热门币种" />
        </Form.Item>
        
        <Form.Item
          name="description"
          label="描述"
        >
          <Input.TextArea rows={2} placeholder="可选，描述此自选组的用途" />
        </Form.Item>
        
        <Form.Item
          name="color"
          label="颜色标识"
          initialValue="#1890ff"
        >
          <Select
            placeholder="选择颜色"
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
        destroyOnClose
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
            searchPlaceholder: '搜索货币对',
            itemUnit: '项',
            itemsUnit: '项',
            notFoundContent: '暂无数据',
          }}
        />
      </Modal>
    );
  };

  // 渲染货币对工具栏
  const renderSymbolToolbar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 第一行：搜索和视图切换 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 12 }} align="middle">
        <Col xs={24} sm={16} md={12} lg={10}>
          <Search
            placeholder="搜索货币对"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ width: '100%' }}
          />
        </Col>
        <Col xs={24} sm={8} md={12} lg={14} style={{ textAlign: 'right' }}>
          <Segmented
            value={viewType}
            onChange={(value) => setViewType(value as ViewType)}
            options={[
              { value: 'list', icon: <UnorderedListOutlined />, label: '列表' },
              { value: 'card', icon: <AppstoreOutlined />, label: '卡片' },
            ]}
          />
        </Col>
      </Row>
      
      {/* 第二行：筛选、排序、刷新按钮 */}
      <Row gutter={[12, 12]} align="middle">
        <Col xs={12} sm={8} md={6} lg={5}>
          <Select
            placeholder="计价货币"
            value={quoteFilter}
            onChange={setQuoteFilter}
            style={{ width: '100%' }}
            options={[
              { value: 'all', label: '全部' },
              { value: 'USDT', label: 'USDT' },
              { value: 'BTC', label: 'BTC' },
              { value: 'ETH', label: 'ETH' },
            ]}
          />
        </Col>
        
        <Col xs={12} sm={10} md={8} lg={6}>
          <Select
            placeholder="排序"
            value={`${sortField}-${sortOrder}`}
            onChange={(value) => {
              const [field, order] = value.split('-');
              setSortField(field as SortField);
              setSortOrder(order as SortOrder);
            }}
            style={{ width: '100%' }}
            options={[
              { value: 'rank-asc', label: '按排名' },
              { value: 'symbol-asc', label: '名称 A-Z' },
              { value: 'symbol-desc', label: '名称 Z-A' },
              { value: 'price-desc', label: '价格 高-低' },
              { value: 'price-asc', label: '价格 低-高' },
              { value: 'change-desc', label: '涨幅 高-低' },
              { value: 'change-asc', label: '涨幅 低-高' },
              { value: 'volume-desc', label: '成交量 高-低' },
            ]}
          />
        </Col>
        
        <Col xs={24} sm={6} md={10} lg={13} style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Space>
            <Text type="secondary">
              {activeGroup?.name || '全部'}: {filteredSymbols.length} 个
            </Text>
            <Button icon={<ReloadOutlined />} onClick={fetchSymbols} loading={symbolLoading}>
              刷新
            </Button>
          </Space>
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
            title="总货币对"
            value={symbols.length}
            prefix={<DatabaseOutlined />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="当前组"
            value={activeGroup?.symbolIds.length || 0}
            prefix={<FolderOpenOutlined style={{ color: activeGroup?.color }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="有数据"
            value={filteredSymbols.filter(s => s.hasData).length}
            prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
          />
        </Card>
      </Col>
      <Col xs={12} sm={6}>
        <Card size="small">
          <Statistic
            title="自动更新"
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
      title: '货币对',
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
      title: '最新价格',
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
      title: '24h涨跌',
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
      title: '24h成交量',
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
      title: '市值',
      dataIndex: 'marketCap',
      key: 'marketCap',
      align: 'right' as const,
      render: (cap?: number) => cap ? `$${(cap / 1000000000).toFixed(2)}B` : '-',
    },
    {
      title: '数据状态',
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
            <Tag>无数据</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '自动更新',
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
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: SymbolData) => (
        <Space>
          {!record.hasData ? (
            <Button
              type="primary"
              size="small"
              icon={<CloudDownloadOutlined />}
              onClick={() => startCollection(record.symbol)}
            >
              采集
            </Button>
          ) : (
            <>
              <Button
                size="small"
                icon={<BarChartOutlined />}
                onClick={() => checkQuality(record.symbol, '1h')}
              >
                质量
              </Button>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => startCollection(record.symbol)}
              >
                更新
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
              <Space direction="vertical" style={{ width: '100%' }}>
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
            showTotal={(total) => `共 ${total} 条`}
            onChange={handlePageChange}
          />
        </Row>
      </>
    );
  };

  // 渲染货币对列表
  const renderSymbolList = () => (
    <div style={{ display: 'flex', gap: 16 }}>
      {renderGroupSidebar()}
      <div style={{ flex: 1, minWidth: 0 }}>
        <Card>
          {renderSymbolToolbar()}
          {renderStatistics()}
          {viewType === 'list' ? renderListView() : renderCardView()}
        </Card>
      </div>
    </div>
  );

  // 渲染数据采集
  const renderCollection = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card title="批量数据采集">
          <Form
            form={collectionForm}
            layout="vertical"
            initialValues={{
              dateRange: [dayjs().subtract(1, 'month'), dayjs()],
              intervals: ['15m'],
            }}
          >
            <Form.Item
              name="symbols"
              label="选择货币对"
              rules={[{ required: true, message: '请至少选择一个货币对' }]}
            >
              <Select
                mode="multiple"
                placeholder="请选择货币对"
                showSearch
                options={symbols.map((s) => ({
                  value: s.symbol,
                  label: s.symbol,
                }))}
                filterOption={(input, option) =>
                  (option?.label || '').toLowerCase().includes(input.toLowerCase())
                }
              />
            </Form.Item>

            <Form.Item
              name="intervals"
              label="时间周期"
              rules={[{ required: true, message: '请至少选择一个时间周期' }]}
            >
              <Select
                mode="multiple"
                placeholder="选择时间周期"
                options={[
                  { value: '1m', label: '1分钟' },
                  { value: '5m', label: '5分钟' },
                  { value: '15m', label: '15分钟' },
                  { value: '30m', label: '30分钟' },
                  { value: '1h', label: '1小时' },
                  { value: '4h', label: '4小时' },
                  { value: '1d', label: '1天' },
                ]}
              />
            </Form.Item>

            <Form.Item
              name="dateRange"
              label="时间范围"
              rules={[{ required: true, message: '请选择时间范围' }]}
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
                开始批量采集
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card title="采集任务">
          {currentTaskId && (
            <Card size="small" style={{ marginBottom: 16 }} title="当前任务">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Row justify="space-between">
                  <Text type="secondary">任务ID:</Text>
                  <Text copyable>{currentTaskId}</Text>
                </Row>
                <Row justify="space-between">
                  <Text type="secondary">状态:</Text>
                  <Tag
                    color={
                      taskStatus === 'running'
                        ? 'processing'
                        : taskStatus === 'completed'
                        ? 'success'
                        : taskStatus === 'failed'
                        ? 'error'
                        : 'default'
                    }
                  >
                    {taskStatus === 'running'
                      ? '运行中'
                      : taskStatus === 'completed'
                      ? '已完成'
                      : taskStatus === 'failed'
                      ? '失败'
                      : '等待中'}
                  </Tag>
                </Row>
                <Progress percent={taskProgress} status={taskStatus === 'running' ? 'active' : 'normal'} />
              </Space>
            </Card>
          )}

          <div style={{ maxHeight: 400, overflow: 'auto' }}>
            {collectionTasks.length === 0 ? (
              <Empty description="暂无采集任务" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {collectionTasks.map((task) => (
                  <Card key={task.task_id} size="small">
                    <Row justify="space-between" align="middle">
                      <Space direction="vertical" size={0}>
                        <Text strong>{task.task_id}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {task.created_at ? dayjs(task.created_at).format('YYYY-MM-DD HH:mm') : '-'}
                        </Text>
                      </Space>
                      <Tag
                        color={
                          task.status === 'running'
                            ? 'processing'
                            : task.status === 'completed'
                            ? 'success'
                            : task.status === 'failed'
                            ? 'error'
                            : 'default'
                        }
                      >
                        {task.status === 'running'
                          ? '运行中'
                          : task.status === 'completed'
                          ? '已完成'
                          : task.status === 'failed'
                          ? '失败'
                          : '等待中'}
                      </Tag>
                    </Row>
                    <Progress
                      percent={task.progress?.percentage || 0}
                      size="small"
                      style={{ marginTop: 8 }}
                    />
                  </Card>
                ))}
              </Space>
            )}
          </div>
        </Card>
      </Col>
    </Row>
  );

  // 渲染数据质量
  const renderQuality = () => (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="质量概览">
          <Space direction="vertical" style={{ width: '100%' }}>
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
                  valueStyle={{ color: '#52c41a' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="警告"
                  value={symbols.filter((s) => s.dataQuality === 'warning').length}
                  valueStyle={{ color: '#faad14' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="异常"
                  value={symbols.filter((s) => s.dataQuality === 'bad').length}
                  valueStyle={{ color: '#ff4d4f' }}
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
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={16}>
        <Card title="检测结果" loading={qualityLoading}>
          {qualityDetail ? (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={[16, 16]}>
                <Col span={8}>
                  <Card size="small">
                    <Statistic
                      title="总体状态"
                      value={qualityDetail.overall_status === 'pass' ? '通过' : '失败'}
                      valueStyle={{
                        color: qualityDetail.overall_status === 'pass' ? '#52c41a' : '#ff4d4f',
                      }}
                    />
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
                      value={(() => {
                        const checks = Object.values(qualityDetail.checks || {});
                        const passed = checks.filter((c: any) => c.status === 'pass').length;
                        return checks.length > 0 ? Math.round((passed / checks.length) * 100) : 0;
                      })()}
                      suffix="分"
                    />
                  </Card>
                </Col>
              </Row>

              {qualityDetail.checks && (
                <Tabs type="card" size="small">
                  <TabPane tab="连续性" key="continuity">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.continuity?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>预期记录: {qualityDetail.checks.continuity?.expected_records}</Text>
                      <Text>实际记录: {qualityDetail.checks.continuity?.actual_records}</Text>
                      <Text>缺失记录: {qualityDetail.checks.continuity?.missing_records}</Text>
                      <Text>
                        覆盖率:{' '}
                        {Math.round((qualityDetail.checks.continuity?.coverage_ratio || 0) * 100)}%
                      </Text>
                    </Space>
                  </TabPane>
                  <TabPane tab="完整性" key="integrity">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.integrity?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>总记录: {qualityDetail.checks.integrity?.total_records}</Text>
                    </Space>
                  </TabPane>
                  <TabPane tab="唯一性" key="uniqueness">
                    <Space direction="vertical">
                      <Text>状态: {qualityDetail.checks.uniqueness?.status === 'pass' ? '通过' : '失败'}</Text>
                      <Text>重复记录: {qualityDetail.checks.uniqueness?.duplicate_records}</Text>
                    </Space>
                  </TabPane>
                </Tabs>
              )}
            </Space>
          ) : (
            <Empty description="请选择货币对并点击检测按钮" />
          )}
        </Card>
      </Col>
    </Row>
  );

  return (
    <PageContainer title={t('data_management') || '数据管理'}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[
          {
            key: 'symbols',
            label: (
              <span>
                <DatabaseOutlined /> 货币对
              </span>
            ),
            children: renderSymbolList(),
          },
          {
            key: 'collection',
            label: (
              <span>
                <CloudDownloadOutlined /> 数据采集
              </span>
            ),
            children: renderCollection(),
          },
          {
            key: 'quality',
            label: (
              <span>
                <BarChartOutlined /> 数据质量
              </span>
            ),
            children: renderQuality(),
          },
        ]}
      />
      
      {renderGroupDrawer()}
      {renderGroupModal()}
      {renderBatchAddModal()}
    </PageContainer>
  );
};

export default DataManagementPage;
