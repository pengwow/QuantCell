import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import DataQuality from '../DataQuality';
import { dataApi } from '../../api';

// 模拟API调用
jest.mock('../../api', () => ({
  dataApi: {
    checkKlineQuality: jest.fn(),
    getCryptoSymbols: jest.fn()
  }
}));

// 模拟系统配置
const mockSystemConfig = {
  current_market_type: 'crypto',
  exchange: 'binance',
  crypto_trading_mode: 'spot'
};

// 模拟成功的API返回结果
const mockSuccessResponse = {
  code: 0,
  data: {
    symbol: 'BTCUSDT',
    interval: '1d',
    overall_status: 'pass',
    checks: {
      integrity: {
        status: 'pass',
        missing_columns: [],
        missing_values: {},
        total_records: 1000
      },
      continuity: {
        status: 'pass',
        expected_records: 1000,
        actual_records: 1000,
        missing_records: 0,
        missing_periods: [],
        coverage_ratio: 1.0,
        missing_time_ranges: []
      },
      validity: {
        status: 'pass',
        negative_prices: [],
        negative_volumes: [],
        invalid_high_low: [],
        invalid_price_logic: [],
        abnormal_price_changes: [],
        abnormal_volumes: [],
        price_gaps: [],
        total_invalid_records: 0
      },
      consistency: {
        status: 'pass',
        time_format_issues: [],
        duplicate_codes: [],
        code_name_mismatches: [],
        inconsistent_adj_factors: []
      },
      logic: {
        status: 'pass',
        trading_time_issues: [],
        suspension_issues: [],
        price_limit_issues: []
      },
      uniqueness: {
        status: 'pass',
        duplicate_records: 0,
        duplicate_periods: [],
        duplicate_code_timestamp: []
      },
      coverage: {
        status: 'pass',
        data_start_date: '2023-01-01T00:00:00',
        data_end_date: '2023-12-31T00:00:00',
        expected_start_date: '2023-01-01T00:00:00',
        expected_end_date: '2023-12-31T00:00:00',
        missing_historical_data: false,
        missing_future_data: false,
        historical_gap_days: 0,
        future_gap_days: 0
      }
    },
    total_records: 1000
  },
  message: 'success'
};

// 模拟失败的API返回结果
const mockFailureResponse = {
  code: 1,
  data: null,
  message: '获取数据质量报告失败'
};

// 模拟货币对列表
const mockSymbolsResponse = {
  code: 0,
  data: {
    symbols: ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
  }
};

describe('DataQuality Component', () => {
  beforeEach(() => {
    // 清除所有模拟调用
    jest.clearAllMocks();
    
    // 模拟获取货币对列表成功
    (dataApi.getCryptoSymbols as jest.Mock).mockResolvedValue(mockSymbolsResponse);
  });

  test('should render correctly', () => {
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    expect(screen.getByText('数据质量检查')).toBeInTheDocument();
    expect(screen.getByText('查询条件')).toBeInTheDocument();
    expect(screen.getByText('选择货币对')).toBeInTheDocument();
    expect(screen.getByText('选择时间周期')).toBeInTheDocument();
    expect(screen.getByText('检查数据质量')).toBeInTheDocument();
  });

  test('should display data quality report when API returns successfully', async () => {
    // 模拟检查数据质量成功
    (dataApi.checkKlineQuality as jest.Mock).mockResolvedValue(mockSuccessResponse);
    
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    // 点击检查数据质量按钮
    const checkButton = screen.getByText('检查数据质量');
    fireEvent.click(checkButton);
    
    // 等待API调用完成和结果展示
    await waitFor(() => {
      expect(dataApi.checkKlineQuality).toHaveBeenCalled();
    });
    
    await waitFor(() => {
      expect(screen.getByText('数据质量概览')).toBeInTheDocument();
    });
    
    // 检查报告内容
    expect(screen.getByText('总体状态:')).toBeInTheDocument();
    expect(screen.getByText('通过')).toBeInTheDocument();
    expect(screen.getByText('质量评分:')).toBeInTheDocument();
    expect(screen.getByText('货币对:')).toBeInTheDocument();
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('时间周期:')).toBeInTheDocument();
    expect(screen.getByText('1d')).toBeInTheDocument();
    expect(screen.getByText('总记录数:')).toBeInTheDocument();
    expect(screen.getByText('1000')).toBeInTheDocument();
  });

  test('should display error message when API returns failure', async () => {
    // 模拟检查数据质量失败
    (dataApi.checkKlineQuality as jest.Mock).mockResolvedValue(mockFailureResponse);
    
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    // 点击检查数据质量按钮
    const checkButton = screen.getByText('检查数据质量');
    fireEvent.click(checkButton);
    
    // 等待API调用完成和结果展示
    await waitFor(() => {
      expect(dataApi.checkKlineQuality).toHaveBeenCalled();
    });
    
    // 检查错误信息
    await waitFor(() => {
      expect(screen.getByText('获取数据质量报告失败: 获取数据质量报告失败')).toBeInTheDocument();
    });
  });

  test('should display error message when API throws exception', async () => {
    // 模拟API调用抛出异常
    (dataApi.checkKlineQuality as jest.Mock).mockRejectedValue(new Error('Network error'));
    
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    // 点击检查数据质量按钮
    const checkButton = screen.getByText('检查数据质量');
    fireEvent.click(checkButton);
    
    // 等待API调用完成和结果展示
    await waitFor(() => {
      expect(dataApi.checkKlineQuality).toHaveBeenCalled();
    });
    
    // 检查错误信息
    await waitFor(() => {
      expect(screen.getByText('获取数据质量报告失败')).toBeInTheDocument();
    });
  });

  test('should display loading spinner when checking data quality', async () => {
    // 模拟API调用延迟返回
    (dataApi.checkKlineQuality as jest.Mock).mockImplementation(() => {
      return new Promise(resolve => {
        setTimeout(() => resolve(mockSuccessResponse), 1000);
      });
    });
    
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    // 点击检查数据质量按钮
    const checkButton = screen.getByText('检查数据质量');
    fireEvent.click(checkButton);
    
    // 检查加载状态
    expect(screen.getByText('正在生成数据质量报告...')).toBeInTheDocument();
    
    // 等待API调用完成
    await waitFor(() => {
      expect(dataApi.checkKlineQuality).toHaveBeenCalled();
    });
    
    // 检查加载状态消失
    await waitFor(() => {
      expect(screen.queryByText('正在生成数据质量报告...')).not.toBeInTheDocument();
    });
  });

  test('should change symbol and interval when selected', async () => {
    render(<DataQuality systemConfig={mockSystemConfig} />);
    
    // 等待货币对列表加载完成
    await waitFor(() => {
      expect(dataApi.getCryptoSymbols).toHaveBeenCalled();
    });
    
    // 选择不同的货币对
    const symbolSelect = screen.getByRole('combobox', { name: /选择货币对/i });
    fireEvent.mouseDown(symbolSelect);
    
    await waitFor(() => {
      const ethOption = screen.getByText('ETHUSDT');
      fireEvent.click(ethOption);
    });
    
    // 选择不同的时间周期
    const intervalSelect = screen.getByRole('combobox', { name: /选择时间周期/i });
    fireEvent.mouseDown(intervalSelect);
    
    await waitFor(() => {
      const hourOption = screen.getByText('1小时');
      fireEvent.click(hourOption);
    });
    
    // 点击检查数据质量按钮
    (dataApi.checkKlineQuality as jest.Mock).mockResolvedValue(mockSuccessResponse);
    const checkButton = screen.getByText('检查数据质量');
    fireEvent.click(checkButton);
    
    // 检查API调用参数
    await waitFor(() => {
      expect(dataApi.checkKlineQuality).toHaveBeenCalledWith({
        symbol: 'ETHUSDT',
        interval: '1h'
      });
    });
  });
});
