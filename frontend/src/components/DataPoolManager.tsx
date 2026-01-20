/**
 * 数据池管理组件
 * 功能：管理数据池的组件，包括列表展示、创建、编辑和删除功能
 */
import { useState, useEffect } from 'react';
import { Table, Modal, Button, Space, message, Popconfirm, Spin, Tooltip } from 'antd';
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
import { dataPoolApi, configApi, dataApi } from '../api';
import DataPoolForm from './DataPoolForm';
import { useTranslation } from 'react-i18next';



interface DataPool {
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

const DataPoolManager = () => {
  // 数据池列表数据
  const [dataPools, setDataPools] = useState<DataPool[]>([]);
  // 加载状态
  const [loading, setLoading] = useState(false);
  // 模态框可见性
  const [modalVisible, setModalVisible] = useState(false);
  // 当前编辑的数据池数据
  const [currentPool, setCurrentPool] = useState<DataPool | null>(null);
  // 模态框标题
  const [modalTitle, setModalTitle] = useState('创建数据池');
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
  const [pageSize] = useState(10000); // 设置为很大的值，一次读取全部数据
  const [, setTotalSymbols] = useState(0);
  // 翻译函数
  const { t } = useTranslation(); 


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

  // 加载数据池数据
  useEffect(() => {
    // 先加载系统配置，然后获取数据池数据
    const loadData = async () => {
      await loadSystemConfig();
      fetchDataPools();
    };
    
    loadData();
  }, []);

  const fetchDataPools = async () => {
    try {
      setLoading(true);
      const data = await dataPoolApi.getDataPools(systemConfig.current_market_type);
      setDataPools(data || []);
    } catch (error) {
      console.error('加载数据池数据失败:', error);
      message.error('加载数据池数据失败');
    } finally {
      setLoading(false);
    }
  };

  /**
   * 处理创建数据池
   * @param data 数据池数据
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
      
      // 创建数据池并获取返回的池ID
      const createdPool = await dataPoolApi.createDataPool(newPoolData);
      // 处理后端返回的不同ID字段名，包括pool_id
      const poolId = createdPool.id || createdPool._id || createdPool.pool_id;
      
      // 添加数据池资产
      if (poolId) {
        await dataPoolApi.addPoolAssets(poolId, {
          assets: data.assets,
          asset_type: systemConfig.current_market_type
        });
      }
      
      setModalVisible(false);
      message.success('数据池创建成功');
      fetchDataPools(); // 重新获取数据池数据，确保资产数量正确
    } catch (error) {
      console.error('创建数据池失败:', error);
      message.error('创建数据池失败');
    }
  };

  /**
   * 处理编辑数据池
   * @param data 数据池数据
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
      await dataPoolApi.updateDataPool(data.id, updateData);
      
      // 更新数据池资产
      await dataPoolApi.addPoolAssets(data.id, {
        assets: data.assets,
        asset_type: systemConfig.current_market_type
      });
      
      setModalVisible(false);
      setCurrentPool(null);
      message.success('数据池更新成功');
      fetchDataPools(); // 重新获取数据池数据，确保资产数量正确
    } catch (error) {
      console.error('更新数据池失败:', error);
      message.error('更新数据池失败');
    }
  };

  /**
   * 处理删除数据池
   * @param id 数据池ID
   */
  const handleDeletePool = async (id: string) => {
    try {
      await dataPoolApi.deleteDataPool(id, systemConfig.current_market_type);
      setDataPools(prev => prev.filter(pool => pool.id !== id));
      message.success('数据池删除成功');
    } catch (error) {
      console.error('删除数据池失败:', error);
      message.error('删除数据池失败');
    }
  };

  /**
   * 打开创建数据池模态框
   */
  const openCreateModal = async () => {
    setModalTitle('创建数据池');
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
   * 打开编辑数据池模态框
   * @param pool 数据池数据
   */
  const openEditModal = async (pool: DataPool) => {
    setModalTitle('编辑数据池');
    setCurrentPool(pool);
    setModalVisible(true);
    // 初始化分页和搜索状态
    setPage(1);
    setSearchKeyword('');
    
    try {
      // 获取数据池已有资产
      const poolAssetsResponse = await dataPoolApi.getPoolAssets(pool.id);
      const existingAssets = poolAssetsResponse.assets || [];
      
      // 直接设置selectedSymbols和availableSymbols，确保所有已选择资产显示在右侧
      setSelectedSymbols(existingAssets);
      
      // 先获取可用资产列表
      await fetchCryptoSymbols(false, '');
      
      // 然后将已选择的资产添加到可用符号列表中
      setAvailableSymbols(prev => [...new Set([...prev, ...existingAssets])]);
    } catch (error) {
      console.error('获取数据池资产失败:', error);
      message.error('获取数据池资产失败');
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
        // 当市场类型为加密货币时，使用具体的交易模式作为 crypto_type 参数
        crypto_type: systemConfig.current_market_type === 'crypto' 
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
      
      // 更新总数
      setTotalSymbols(total);
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
  const columns: TableColumnsType<DataPool> =[
    {
      title: '数据池名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '数据池描述',
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
      align: 'center' as const,
      render: (_: any, record: DataPool) => (
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
            title="确定要删除这个数据池吗？"
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

  // 处理模态框关闭
  const handleModalCancel = () => {
    setModalVisible(false);
    setCurrentPool(null);
    setSelectedSymbols([]);
  };

  return (
    <div className="data-pool-manager">
      <div className="data-pool-header">
        <h2>{t('data_pool_management')}</h2>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={openCreateModal}
        >
          创建数据池
        </Button>
      </div>

      {/* 数据池列表 */}
      <Spin spinning={loading} tip="加载中...">
        <Table
          columns={columns}
          dataSource={dataPools}
          rowKey="id"
          bordered
          pagination={false}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: '暂无数据池，请点击"创建数据池"按钮添加' }}
          style={{ marginTop: 16 }}
        />
      </Spin>

      {/* 创建/编辑模态框 */}
      <Modal
        title={modalTitle}
        open={modalVisible}
        footer={null}
        onCancel={handleModalCancel}
        width={1000}
      >

        <DataPoolForm
          initialData={currentPool || { name: '', description: '' }}
          onSubmit={currentPool ? handleEditPool : handleCreatePool}
          onCancel={handleModalCancel}
          // 数据池名称列表，用于前端校验
          dataPoolNames={dataPools.map(pool => pool.name)}
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
        />

      </Modal>
    </div>
  );
};

export default DataPoolManager;