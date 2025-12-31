/**
 * 资产池管理组件
 * 功能：管理资产池的组件，包括列表展示、创建、编辑和删除功能
 */
import { useState, useEffect } from 'react';
import { Table, Modal, Button, Space, message, Popconfirm, Spin, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
import { assetPoolApi, configApi, dataApi } from '../api';
import AssetPoolForm from './AssetPoolForm';

interface AssetPool {
  id: string;
  name: string;
  description: string;
  type: string;
  asset_count: number;
  createdAt: string;
}

interface SystemConfig {
  current_market_type: string;
  exchange: string;
  crypto_trading_mode: string;
  [key: string]: any;
}

const AssetPoolManager = () => {
  // 资产池列表数据
  const [assetPools, setAssetPools] = useState<AssetPool[]>([]);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // 模态框可见性
  const [modalVisible, setModalVisible] = useState(false);
  // 当前编辑的资产池数据
  const [currentPool, setCurrentPool] = useState<AssetPool | null>(null);
  // 模态框标题
  const [modalTitle, setModalTitle] = useState('创建资产池');
  // 系统配置
  const [systemConfig, setSystemConfig] = useState<SystemConfig>({
    current_market_type: 'crypto',
    exchange: 'binance',
    crypto_trading_mode: 'spot'
  });
  // 可用符号列表
  const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
  // 穿梭框选中的符号
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  // 符号加载状态
  const [symbolsLoading, setSymbolsLoading] = useState(false);
  // 搜索关键词
  const [searchKeyword, setSearchKeyword] = useState('');
  // 分页状态
  const [page, setPage] = useState(1);
  const [pageSize] = useState(100);
  const [, setTotalSymbols] = useState(0);
  // 是否还有更多数据
  const [hasMore, setHasMore] = useState(true);

  // 加载系统配置
  const loadSystemConfig = async () => {
    try {
      const configData = await configApi.getConfig();
      setSystemConfig({
        current_market_type: configData.current_market_type || 'crypto',
        exchange: configData.exchange || 'binance',
        crypto_trading_mode: configData.crypto_trading_mode || 'spot'
      });
    } catch (error) {
      console.error('加载系统配置失败:', error);
      // 使用默认配置
      setSystemConfig({
        current_market_type: 'crypto',
        exchange: 'binance',
        crypto_trading_mode: 'spot'
      });
    }
  };

  // 加载资产池数据
  useEffect(() => {
    // 先加载系统配置，然后获取资产池数据
    const loadData = async () => {
      await loadSystemConfig();
      fetchAssetPools();
    };
    
    loadData();
  }, []);

  const fetchAssetPools = async () => {
    try {
      setLoading(true);
      const data = await assetPoolApi.getAssetPools(systemConfig.current_market_type);
      setAssetPools(data || []);
    } catch (error) {
      console.error('加载资产池数据失败:', error);
      message.error('加载资产池数据失败');
    } finally {
      setLoading(false);
    }
  };

  /**
   * 处理创建资产池
   * @param data 资产池数据
   */
  const handleCreatePool = async (data: {
    name: string;
    description: string;
    assets: string[];
  }) => {
    try {
      // 添加 type 字段，使用系统配置中的 current_market_type，默认值为 'crypto'
      const newPoolData = {
        ...data,
        type: systemConfig.current_market_type || 'crypto'
      };
      await assetPoolApi.createAssetPool(newPoolData);
      setModalVisible(false);
      message.success('资产池创建成功');
      fetchAssetPools(); // 重新获取资产池数据，确保资产数量正确
    } catch (error) {
      console.error('创建资产池失败:', error);
      message.error('创建资产池失败');
    }
  };

  /**
   * 处理编辑资产池
   * @param data 资产池数据
   */
  const handleEditPool = async (data: {
    id?: string;
    name: string;
    description: string;
    assets: string[];
  }) => {
    if (!data.id) return;
    try {
      // 添加 type 字段，使用系统配置中的 current_market_type，默认值为 'crypto'
      const updateData = {
        ...data,
        type: systemConfig.current_market_type || 'crypto'
      };
      await assetPoolApi.updateAssetPool(data.id, updateData);
      
      // 更新资产池资产
      await assetPoolApi.addPoolAssets(data.id, {
        assets: data.assets,
        asset_type: systemConfig.current_market_type
      });
      
      setModalVisible(false);
      setCurrentPool(null);
      message.success('资产池更新成功');
      fetchAssetPools(); // 重新获取资产池数据，确保资产数量正确
    } catch (error) {
      console.error('更新资产池失败:', error);
      message.error('更新资产池失败');
    }
  };

  /**
   * 处理删除资产池
   * @param id 资产池ID
   */
  const handleDeletePool = async (id: string) => {
    try {
      await assetPoolApi.deleteAssetPool(id, systemConfig.current_market_type);
      setAssetPools(prev => prev.filter(pool => pool.id !== id));
      message.success('资产池删除成功');
    } catch (error) {
      console.error('删除资产池失败:', error);
      message.error('删除资产池失败');
    }
  };

  /**
   * 打开创建资产池模态框
   */
  const openCreateModal = async () => {
    setModalTitle('创建资产池');
    setCurrentPool(null);
    setModalVisible(true);
    // 初始化资产数据
    setPage(1);
    setSearchKeyword('');
    setAvailableSymbols([]);
    setSelectedSymbols([]);
    await fetchCryptoSymbols(false, '');
  };

  /**
   * 打开编辑资产池模态框
   * @param pool 资产池数据
   */
  const openEditModal = async (pool: AssetPool) => {
    setModalTitle('编辑资产池');
    setCurrentPool(pool);
    setModalVisible(true);
    // 初始化分页和搜索状态
    setPage(1);
    setSearchKeyword('');
    
    try {
      // 获取资产池已有资产
      const poolAssetsResponse = await assetPoolApi.getPoolAssets(pool.id);
      const existingAssets = poolAssetsResponse.assets || [];
      
      // 直接设置selectedSymbols和availableSymbols，确保所有已选择资产显示在右侧
      setSelectedSymbols(existingAssets);
      
      // 先获取可用资产列表
      await fetchCryptoSymbols(false, '');
      
      // 然后将已选择的资产添加到可用符号列表中
      setAvailableSymbols(prev => [...new Set([...prev, ...existingAssets])]);
    } catch (error) {
      console.error('获取资产池资产失败:', error);
      message.error('获取资产池资产失败');
    }
  };

  /**
   * 获取加密货币符号列表
   */
  const fetchCryptoSymbols = async (isLoadMore = false, keyword = '') => {
    try {
      setSymbolsLoading(true);
      
      // 计算偏移量
      const offset = isLoadMore ? (page - 1) * pageSize : 0;
      
      // 构建请求参数
      const params: any = {
        // 当市场类型为加密货币时，使用具体的交易模式作为 type 参数
        type: systemConfig.current_market_type === 'crypto' 
          ? systemConfig.crypto_trading_mode 
          : systemConfig.current_market_type,
        exchange: systemConfig.exchange,
        limit: pageSize,
        offset: offset
      };
      
      // 只有当keyword或searchKeyword不为空时，才添加filter参数
      const searchFilter = keyword || searchKeyword;
      if (searchFilter && searchFilter.trim()) {
        params.filter = searchFilter;
      }
      
      // 调用API
      const response = await dataApi.getCryptoSymbols(params);
      
      // 正确解析后端返回的数据格式
      const symbolsArray = response.symbols || [];
      const total = response.total || 0;
      
      // 提取symbol字段并转换为字符串数组
      const symbolsList = symbolsArray.map((item: any) => item.symbol);
      
      // 更新状态，确保在任何情况下都包含已选择的符号
      if (isLoadMore) {
        // 加载更多，追加数据
        setAvailableSymbols(prev => [...new Set([...prev, ...symbolsList, ...selectedSymbols])]);
        setPage(prev => prev + 1);
      } else {
        // 重新加载，替换数据并合并已选择的符号
        // 确保 availableSymbols 始终包含所有已选择的符号
        const mergedSymbols = [...new Set([...symbolsList, ...selectedSymbols])];
        setAvailableSymbols(mergedSymbols);
        setPage(2); // 下一页从2开始
      }
      
      // 更新总数和是否还有更多数据
      setTotalSymbols(total);
      setHasMore(availableSymbols.length + symbolsList.length < total);
    } catch (error) {
      console.error('获取加密货币符号失败:', error);
      message.error('获取加密货币符号失败');
      if (!isLoadMore) {
        setAvailableSymbols([]);
      }
    } finally {
      setSymbolsLoading(false);
    }
  };



  // 表格列配置
  const columns: TableColumnsType<AssetPool> =[
    {
      title: '资产池名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '资产池描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: {
        showTitle: false,
      },
      width: 300,
      render: (description) => (
        <Tooltip placement="topLeft" title={description}>
          {description}
        </Tooltip>
      ),
      // ellipsis: {
      //   rows: 2,
      //   showTitle: true,
      //   textWrap: 'word-break',
      // },
      // width: 300,
    },
    {
      title: '资产数量',
      dataIndex: 'asset_count',
      key: 'asset_count',
      width: 120,
      align: 'center' as const,
    },
    {
      title: '操作',
      key: 'action',
      // width: 100,
      align: 'center' as const,
      render: (_: any, record: AssetPool) => (
        <Space size="small">
          <Button
            size="small"
            type="link"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个资产池吗？"
            onConfirm={() => handleDeletePool(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              size="small"
              type="link"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="asset-pool-manager">
      <div className="asset-pool-header">
        <h2>资产池管理</h2>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openCreateModal}
        >
          创建资产池
        </Button>
      </div>

      {/* 资产池列表 */}
      <Spin spinning={loading} tip="加载中...">
        <Table
          columns={columns}
          dataSource={assetPools}
          rowKey="id"
          bordered
          pagination={false}
          scroll={{ y: 55 * 5 }}
          locale={{ emptyText: '暂无资产池，请点击"创建资产池"按钮添加' }}
          style={{ marginTop: 16 }}
        />
      </Spin>

      {/* 创建/编辑模态框 */}
      <Modal
        title={modalTitle}
        open={modalVisible}
        footer={null}
        onCancel={() => setModalVisible(false)}
        width={1000}
      >
        <AssetPoolForm
          initialData={currentPool || { name: '', description: '' }}
          onSubmit={currentPool ? handleEditPool : handleCreatePool}
          onCancel={() => setModalVisible(false)}
          // 资产池名称列表，用于前端校验
          assetPoolNames={assetPools.map(pool => pool.name)}
          // 资产相关属性
          availableAssets={availableSymbols}
          selectedAssets={selectedSymbols}
          onAssetsChange={setSelectedSymbols}
          symbolsLoading={symbolsLoading}
          onSearchSymbols={async (direction, value) => {
            // 只有左侧搜索时才调用API
            if (direction === 'left') {
              setSearchKeyword(value);
              setPage(1);
              setAvailableSymbols([]);
              await fetchCryptoSymbols(false, value);
            }
            // 右侧搜索时不调用API，只在本地过滤
          }}
          hasMore={hasMore}
          onLoadMore={() => fetchCryptoSymbols(true)}
        />
      </Modal>
    </div>
  );
};

export default AssetPoolManager;
