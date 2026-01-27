#!/usr/bin/env python3
# 测试合并资金曲线功能

import json
import sys
from pathlib import Path

def test_merge_equity_curves():
    """测试合并资金曲线功能"""
    print("=== 测试合并资金曲线功能 ===")
    
    # 模拟多货币对回测结果
    mock_results = {
        "BTCUSDT": {
            "status": "success",
            "equity_curve": [
                {"datetime": "2023-01-01", "Equity": 10000},
                {"datetime": "2023-01-02", "Equity": 10100},
                {"datetime": "2023-01-03", "Equity": 10200},
            ]
        },
        "ETHUSDT": {
            "status": "success",
            "equity_curve": [
                {"datetime": "2023-01-01", "Equity": 10000},
                {"datetime": "2023-01-02", "Equity": 10150},
                {"datetime": "2023-01-03", "Equity": 10300},
            ]
        }
    }
    
    print("模拟回测结果:")
    print(json.dumps(mock_results, indent=2, ensure_ascii=False))
    
    # 测试合并资金曲线
    def merge_equity_curves(currency_results):
        """复制自 BacktestService.merge_backtest_results 中的合并逻辑"""
        try:
            # 收集所有时间戳和对应权益值
            time_equity_map = {}
            
            for symbol, result in currency_results.items():
                if result.get("status") == "success" and "equity_curve" in result:
                    equity_curve = result["equity_curve"]
                    for equity_data in equity_curve:
                        # 提取时间戳
                        timestamp = equity_data.get("datetime") or equity_data.get("time") or equity_data.get("timestamp")
                        if timestamp:
                            # 提取权益值
                            equity = equity_data.get("Equity") or equity_data.get("equity") or 0
                            if timestamp not in time_equity_map:
                                time_equity_map[timestamp] = 0
                            time_equity_map[timestamp] += equity
            
            # 按时间戳排序并构建合并后的资金曲线
            merged_curve = []
            for timestamp in sorted(time_equity_map.keys()):
                merged_curve.append({
                    "datetime": timestamp,
                    "Equity": time_equity_map[timestamp]
                })
            
            print(f"资金曲线合并完成，共 {len(merged_curve)} 个时间点")
            return merged_curve
        except Exception as e:
            print(f"合并资金曲线失败: {e}")
            return []
    
    # 执行测试
    merged_curve = merge_equity_curves(mock_results)
    
    print("合并后的资金曲线:")
    print(json.dumps(merged_curve, indent=2, ensure_ascii=False))
    
    # 验证结果
    if not merged_curve:
        print("❌ 测试失败: 合并后的资金曲线为空")
        return False
    elif len(merged_curve) != 3:
        print(f"❌ 测试失败: 合并后的资金曲线长度不正确，期望3，实际{len(merged_curve)}")
        return False
    elif merged_curve[0]["Equity"] != 20000:
        print(f"❌ 测试失败: 第一个时间点的权益值不正确，期望20000，实际{merged_curve[0]['Equity']}")
        return False
    elif merged_curve[1]["Equity"] != 20250:
        print(f"❌ 测试失败: 第二个时间点的权益值不正确，期望20250，实际{merged_curve[1]['Equity']}")
        return False
    elif merged_curve[2]["Equity"] != 20500:
        print(f"❌ 测试失败: 第三个时间点的权益值不正确，期望20500，实际{merged_curve[2]['Equity']}")
        return False
    else:
        print("✅ 测试成功: 合并资金曲线功能正常")
        return True

def test_merge_backtest_results_logic():
    """测试合并回测结果的核心逻辑"""
    print("\n=== 测试合并回测结果核心逻辑 ===")
    
    # 模拟多货币对回测结果
    mock_results = {
        "BTCUSDT": {
            "status": "success",
            "strategy_name": "TestStrategy",
            "backtest_config": {"initial_cash": 10000},
            "metrics": [
                {"name": "Return [%]", "value": 10},
                {"name": "Max. Drawdown [%]", "value": 5},
                {"name": "Sharpe Ratio", "value": 2},
                {"name": "Equity Final [$]", "value": 11000}
            ],
            "trades": [],
            "equity_curve": [
                {"datetime": "2023-01-01", "Equity": 10000},
                {"datetime": "2023-01-02", "Equity": 10100},
                {"datetime": "2023-01-03", "Equity": 11000},
            ]
        },
        "ETHUSDT": {
            "status": "success",
            "strategy_name": "TestStrategy",
            "backtest_config": {"initial_cash": 10000},
            "metrics": [
                {"name": "Return [%]", "value": 20},
                {"name": "Max. Drawdown [%]", "value": 8},
                {"name": "Sharpe Ratio", "value": 1.5},
                {"name": "Equity Final [$]", "value": 12000}
            ],
            "trades": [],
            "equity_curve": [
                {"datetime": "2023-01-01", "Equity": 10000},
                {"datetime": "2023-01-02", "Equity": 10500},
                {"datetime": "2023-01-03", "Equity": 12000},
            ]
        }
    }
    
    # 模拟合并回测结果的核心逻辑
    def merge_backtest_results(results):
        """复制自 BacktestService.merge_backtest_results 中的核心逻辑"""
        try:
            print(f"开始合并回测结果，共 {len(results)} 个货币对")
            
            # 提取第一个成功的回测结果作为基础
            base_result = None
            for symbol, result in results.items():
                if result["status"] == "success":
                    base_result = result
                    break
            
            if not base_result:
                print("所有货币对回测失败，无法合并结果")
                return {
                    "status": "failed",
                    "message": "所有货币对回测失败",
                    "currencies": results
                }
            
            # 计算整体统计指标
            total_trades = 0
            successful_currencies = []
            returns = []
            max_drawdowns = []
            sharpe_ratios = []
            sortino_ratios = []
            calmar_ratios = []
            win_rates = []
            profit_factors = []
            total_equity = 0
            total_initial_cash = 0
            
            # 收集所有成功回测的结果
            successful_results = {}
            for symbol, result in results.items():
                if result["status"] == "success":
                    successful_currencies.append(symbol)
                    successful_results[symbol] = result
                    
                    # 统计交易次数
                    trade_count = len(result["trades"])
                    total_trades += trade_count
                    print(f"货币对 {symbol} 交易次数: {trade_count}")
                    
                    # 提取关键指标
                    for metric in result["metrics"]:
                        if metric["name"] == "Return [%]":
                            returns.append(metric["value"])
                            print(f"货币对 {symbol} 收益率: {metric['value']}%")
                        elif metric["name"] == "Max. Drawdown [%]":
                            max_drawdowns.append(metric["value"])
                            print(f"货币对 {symbol} 最大回撤: {metric['value']}%")
                        elif metric["name"] == "Sharpe Ratio":
                            sharpe_ratios.append(metric["value"])
                            print(f"货币对 {symbol} 夏普比率: {metric['value']}")
                        elif metric["name"] == "Sortino Ratio":
                            sortino_ratios.append(metric["value"])
                            print(f"货币对 {symbol} 索提诺比率: {metric['value']}")
                        elif metric["name"] == "Calmar Ratio":
                            calmar_ratios.append(metric["value"])
                            print(f"货币对 {symbol} 卡尔玛比率: {metric['value']}")
                        elif metric["name"] == "Win Rate [%]":
                            win_rates.append(metric["value"])
                            print(f"货币对 {symbol} 胜率: {metric['value']}%")
                        elif metric["name"] == "Profit Factor":
                            profit_factors.append(metric["value"])
                            print(f"货币对 {symbol} 盈利因子: {metric['value']}")
                        elif metric["name"] == "Equity Final [$]":
                            total_equity += metric["value"]
                            print(f"货币对 {symbol} 最终权益: ${metric['value']}")
                    
                    # 统计初始资金
                    initial_cash = result.get("backtest_config", {}).get("initial_cash", 10000)
                    total_initial_cash += initial_cash
                    print(f"货币对 {symbol} 初始资金: ${initial_cash}")
            
            print(f"成功回测的货币对数量: {len(successful_currencies)}/{len(results)}")
            
            # 计算平均值
            avg_return = sum(returns) / len(returns) if returns else 0
            avg_max_drawdown = sum(max_drawdowns) / len(max_drawdowns) if max_drawdowns else 0
            avg_sharpe = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0
            avg_sortino = sum(sortino_ratios) / len(sortino_ratios) if sortino_ratios else 0
            avg_calmar = sum(calmar_ratios) / len(calmar_ratios) if calmar_ratios else 0
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
            avg_profit_factor = sum(profit_factors) / len(profit_factors) if profit_factors else 0
            
            # 计算总收益率
            total_return = ((total_equity - total_initial_cash) / total_initial_cash) * 100 if total_initial_cash > 0 else 0
            
            # 合并资金曲线
            def merge_equity_curves(currency_results):
                """合并多个货币对的资金曲线"""
                try:
                    # 收集所有时间戳和对应权益值
                    time_equity_map = {}
                    
                    for symbol, result in currency_results.items():
                        if result.get("status") == "success" and "equity_curve" in result:
                            equity_curve = result["equity_curve"]
                            for equity_data in equity_curve:
                                # 提取时间戳
                                timestamp = equity_data.get("datetime") or equity_data.get("time") or equity_data.get("timestamp")
                                if timestamp:
                                    # 提取权益值
                                    equity = equity_data.get("Equity") or equity_data.get("equity") or 0
                                    if timestamp not in time_equity_map:
                                        time_equity_map[timestamp] = 0
                                    time_equity_map[timestamp] += equity
                    
                    # 按时间戳排序并构建合并后的资金曲线
                    merged_curve = []
                    for timestamp in sorted(time_equity_map.keys()):
                        merged_curve.append({
                            "datetime": timestamp,
                            "Equity": time_equity_map[timestamp]
                        })
                    
                    print(f"资金曲线合并完成，共 {len(merged_curve)} 个时间点")
                    return merged_curve
                except Exception as e:
                    print(f"合并资金曲线失败: {e}")
                    return []
            
            # 执行资金曲线合并
            merged_equity_curve = merge_equity_curves(successful_results)
            
            # 构建合并后的回测结果
            merged_result = {
                "status": "success",
                "message": "多货币对回测完成",
                "strategy_name": base_result.get("strategy_name", "Unknown"),
                "backtest_config": base_result.get("backtest_config", {}),
                "summary": {
                    "total_currencies": len(results),
                    "successful_currencies": len(successful_currencies),
                    "failed_currencies": len(results) - len(successful_currencies),
                    "total_trades": total_trades,
                    "average_trades_per_currency": round(total_trades / len(successful_currencies), 2) if successful_currencies else 0,
                    "total_initial_cash": round(total_initial_cash, 2),
                    "total_equity": round(total_equity, 2),
                    "total_return": round(total_return, 2),
                    "average_return": round(avg_return, 2),
                    "average_max_drawdown": round(avg_max_drawdown, 2),
                    "average_sharpe_ratio": round(avg_sharpe, 2),
                    "average_sortino_ratio": round(avg_sortino, 2),
                    "average_calmar_ratio": round(avg_calmar, 2),
                    "average_win_rate": round(avg_win_rate, 2),
                    "average_profit_factor": round(avg_profit_factor, 2)
                },
                "currencies": results,
                "merged_equity_curve": merged_equity_curve,  # 合并后的资金曲线
                "successful_currencies": successful_currencies,
                "failed_currencies": [symbol for symbol, result in results.items() if result["status"] != "success"]
            }
            
            print(f"回测结果合并完成，共 {len(successful_currencies)} 个货币对回测成功")
            print(f"合并后总收益率: {round(total_return, 2)}%，总交易次数: {total_trades}")
            return merged_result
        except Exception as e:
            print(f"合并回测结果失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "failed",
                "message": f"合并回测结果失败: {str(e)}",
                "currencies": results
            }
    
    # 执行测试
    merged_result = merge_backtest_results(mock_results)
    
    print("合并后的回测结果:")
    print(f"状态: {merged_result.get('status')}")
    print(f"成功货币对数量: {len(merged_result.get('successful_currencies', []))}")
    print(f"合并资金曲线长度: {len(merged_result.get('merged_equity_curve', []))}")
    
    # 验证结果
    merged_equity_curve = merged_result.get('merged_equity_curve', [])
    if not merged_equity_curve:
        print("❌ 测试失败: 合并后的资金曲线为空")
        return False
    elif len(merged_equity_curve) != 3:
        print(f"❌ 测试失败: 合并后的资金曲线长度不正确，期望3，实际{len(merged_equity_curve)}")
        return False
    elif merged_equity_curve[0]["Equity"] != 20000:
        print(f"❌ 测试失败: 第一个时间点的权益值不正确，期望20000，实际{merged_equity_curve[0]['Equity']}")
        return False
    elif merged_equity_curve[1]["Equity"] != 20600:
        print(f"❌ 测试失败: 第二个时间点的权益值不正确，期望20600，实际{merged_equity_curve[1]['Equity']}")
        return False
    elif merged_equity_curve[2]["Equity"] != 23000:
        print(f"❌ 测试失败: 第三个时间点的权益值不正确，期望23000，实际{merged_equity_curve[2]['Equity']}")
        return False
    else:
        print("✅ 测试成功: 合并回测结果功能正常")
        return True

if __name__ == "__main__":
    # 运行测试
    test1_passed = test_merge_equity_curves()
    test2_passed = test_merge_backtest_results_logic()
    
    if test1_passed and test2_passed:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败！")
        sys.exit(1)
