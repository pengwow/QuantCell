#!/usr/bin/env python3
"""
批量翻译脚本：将 nautilus_trader 示例文件中的英文注释翻译为中文
格式：# 中文翻译 / Original English
"""

import os
import re
from pathlib import Path

# 需要翻译的目录
TARGET_DIR = Path("/Users/liupeng/workspace/quant/nautilus_trader/examples/live")

# 版权头注释（多行）
COPYRIGHT_PATTERNS = [
    r"^#\s*Copyright \(C\) .* Nautech Systems Pty Ltd\. All rights reserved\.$",
    r"^#\s*https://nautechsystems\.io$",
    r"^#\s*Licensed under the GNU Lesser General Public License Version 3\.0.*$",
    r"^#\s*You may not use this file except in compliance with the License\.$",
    r"^#\s*You may obtain a copy of the License at https://www\.gnu\.org/licenses/lgpl-3\.0\.en\.html$",
    r"^#\s*Unless required by applicable law or agreed to in writing, software$",
    r"^#\s*distributed under the License is distributed on an \"AS IS\" BASIS,$",
    r"^#\s*WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied\.$",
    r"^#\s*See the License for the specific language governing permissions and$",
    r"^#\s*limitations under the License\.$",
]

# 翻译映射表
TRANSLATIONS = {
    # 版权头
    "Copyright (C)": "版权所有 (C)",
    "All rights reserved.": "保留所有权利。",
    "Licensed under the GNU Lesser General Public License Version 3.0 (the \"License\");": "根据 GNU 宽通用公共许可证第 3.0 版（\"许可证\"）获得许可；",
    "You may not use this file except in compliance with the License.": "除非遵守许可证，否则您不得使用此文件。",
    "You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html": "您可以在以下网址获取许可证副本：https://www.gnu.org/licenses/lgpl-3.0.en.html",
    "Unless required by applicable law or agreed to in writing, software": "除非适用法律要求或书面同意，否则根据许可证分发的软件",
    "distributed under the License is distributed on an \"AS IS\" BASIS,": "按\"原样\"分发，不提供任何明示或暗示的保证或条件。",
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.": "不提供任何明示或暗示的保证或条件。",
    "See the License for the specific language governing permissions and": "请参阅许可证以了解管理权限和限制的特定语言。",
    "limitations under the License.": "限制。",
    
    # 常见注释
    "THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER.": "这是一个没有任何阿尔法优势的测试策略。",
    "IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY.": "它不适用于使用真实资金进行实时交易。",
    "Configuration": "配置",
    "Configure the trading node": "配置交易节点",
    "Instantiate the node with a configuration": "使用配置实例化节点",
    "Stop and dispose of the node with SIGINT/CTRL+C": "使用 SIGINT/CTRL+C 停止并释放节点",
    "env var": "环境变量",
    "Not applicable": "不适用",
    "Data only, no execution": "仅数据，无执行",
    "No API key required for public market data": "公共市场数据不需要 API 密钥",
    "If client uses the testnet API": "如果客户端使用测试网 API",
    "If clients use the testnet API": "如果客户端使用测试网 API",
    "Override with custom endpoint": "使用自定义端点覆盖",
    "Example of purging closed orders for HFT": "高频交易清除已关闭订单的示例",
    "Purged orders closed for at least an hour": "清除已关闭至少一小时的订单",
    "Example of purging closed positions for HFT": "高频交易清除已关闭仓位的示例",
    "Purge positions closed for at least an hour": "清除已关闭至少一小时的仓位",
    "Example of purging account events for HFT": "高频交易清除账户事件的示例",
    "Purge account events occurring more than an hour ago": "清除发生在一小时前的账户事件",
    "Set True with caution": "谨慎设置为 True",
    "Register your client factories with the node (can take user-defined factories)": "向节点注册客户端工厂（可以使用用户定义的工厂）",
    "Add your strategies and modules": "添加你的策略和模块",
    "Configure your strategy": "配置你的策略",
    "Instantiate your strategy": "实例化你的策略",
    "Run the node (stop with SIGINT/CTRL+C)": "运行节点（使用 SIGINT/CTRL+C 停止）",
    "Toggle between SPOT and FUTURES": "在 SPOT 和 FUTURES 之间切换",
    "Strategy config params": "策略配置参数",
    "Will use opening time as `ts_event` (same like IB)": "将使用开盘时间作为 `ts_event`（与 IB 相同）",
    "Will make sure DataEngine discards any Bars received out of sequence": "将确保 DataEngine 丢弃任何乱序接收的 K 线",
    "This must match with the IB Gateway/TWS node is connecting to": "这必须与 IB Gateway/TWS 节点连接到的账户匹配",
    "Keep a reference to the log guard to prevent it from being immediately garbage collected": "保留对日志守卫的引用以防止其被立即垃圾回收",
    "Connect to Betfair client early to load instruments and account currency": "提前连接到 Betfair 客户端以加载工具和账户货币",
    "Determine account currency - used in execution client": "确定账户货币 - 在执行客户端中使用",
    "Ensures no stream conflation": "确保没有流合并",
    "Found instruments": "找到的工具",
    "Update the market ID with something coming up in `Next Races` from": "使用 https://www.betfair.com.au/exchange/plus/ 上 `Next Races` 中的市场 ID 进行更新",
    "The market ID will appear in the browser query string.": "市场 ID 将显示在浏览器查询字符串中。",
    "Pass here or will source from the": "在此处传递或从",
    "Instrument provider config": "工具提供者配置",
    "Build slugs for": "构建 slug 用于",
    "UpDown markets follow the pattern": "UpDown 市场遵循模式",
    "Where timestamp is the START of the 15-minute window.": "其中时间戳是 15 分钟窗口的开始。",
    "Returns": "返回",
    "List of event slugs for": "事件 slug 列表用于",
    "Round down to nearest 15-minute interval": "向下舍入到最近的 15 分钟间隔",
    "Generate slugs for the next": "生成接下来",
    "intervals": "间隔",
    "hours)": "小时)",
    "per crypto": "每种加密货币",
    "Returns known active event slugs from Polymarket.": "返回来自 Polymarket 的已知活跃事件 slug。",
    "List of sample event slugs.": "样本事件 slug 列表。",
    "For correct subscription operation, you must specify all instruments to be immediately": "为了正确的订阅操作，您必须指定所有要立即",
    "subscribed for as part of the data client configuration": "订阅的工具作为数据客户端配置的一部分",
    "To find active markets run": "要查找活跃市场，请运行",
    "Note on pagination": "关于分页的说明",
    "The py_clob_client library handles pagination internally": "py_clob_client 库在内部处理分页",
    "for both get_orders() and get_trades() methods. It automatically fetches all": "对于 get_orders() 和 get_trades() 方法。它会自动获取所有",
    "pages and returns the complete dataset, so no manual pagination is needed.": "页面并返回完整的数据集，因此不需要手动分页。",
    "Configure instrument provider to only load the specific instrument we're testing": "配置工具提供者以仅加载我们正在测试的特定工具",
    "This avoids walking the entire Polymarket market space unnecessarily": "这避免不必要地遍历整个 Polymarket 市场空间",
    "Order configuration": "订单配置",
    "Number of shares for limit orders, or notional value for market BUY": "限价单的股数，或市价买单的名义价值",
    "Required for submitting market BUY orders": "提交市价买单所需",
    "Polymarket does not support post-only orders": "Polymarket 不支持仅挂单订单",
    "Polymarket does not support reduce-only orders": "Polymarket 不支持仅减仓订单",
    "Polymarket does not support unsubscribing from ws streams": "Polymarket 不支持取消订阅 ws 流",
    "Use if trading via Polymarket Proxy (enables UI verification, requires funder address)": "如果通过 Polymarket 代理交易（启用 UI 验证，需要资助者地址）",
    "Uncomment if you're using the proxy wallet (Polymarket UI)": "如果您使用代理钱包（Polymarket UI），请取消注释",
    "Refresh every 15 mins for UpDown markets": "每 15 分钟刷新一次 UpDown 市场",
    "Example TradingNode script demonstrating the event_slug_builder feature.": "演示 event_slug_builder 功能的示例 TradingNode 脚本。",
    "This script shows how to efficiently load niche Polymarket markets using": "此脚本展示如何高效加载利基 Polymarket 市场",
    "dynamically generated event slugs instead of downloading all 151k+ markets.": "使用动态生成的事件 slug 而不是下载所有 15 万+ 市场。",
    "The event_slug_builder takes a fully qualified path to a callable that returns": "event_slug_builder 接受一个返回",
    "a list of event slugs. The provider fetches only those specific events from": "事件 slug 列表的可调用对象的完全限定路径。提供者仅从",
    "the Gamma API.": "Gamma API 获取这些特定事件。",
    "Environment variables required (set these before running):": "需要的环境变量（在运行前设置）：",
    "To get Polymarket API credentials:": "获取 Polymarket API 凭证：",
    "Go to https://polymarket.com and connect your wallet": "访问 https://polymarket.com 并连接您的钱包",
    "Navigate to Settings -> API Keys": "导航到设置 -> API 密钥",
    "Create new API credentials": "创建新的 API 凭证",
    "Alternative slug builders you can try:": "您可以尝试的其他 slug 构建器：",
    "Static sample slugs": "静态样本 slug",
    "Configure the instrument provider with event_slug_builder": "使用 event_slug_builder 配置工具提供者",
    "Example slug builder functions for Polymarket event_slug_builder feature.": "Polymarket event_slug_builder 功能的示例 slug 构建器函数。",
    "These functions dynamically generate event slugs for niche markets with": "这些函数为具有",
    "predictable naming patterns, allowing efficient loading without downloading": "可预测命名模式的利基市场动态生成事件 slug，允许高效加载而无需下载",
    "all 151k+ markets.": "所有 15 万+ 市场。",
    "In your PolymarketInstrumentProviderConfig:": "在您的 PolymarketInstrumentProviderConfig 中：",
    "Run the following to start the tardis-machine server:": "运行以下命令启动 tardis-machine 服务器：",
    "The TM_API_KEY environment variable should be set": "应设置 TM_API_KEY 环境变量",
    "The TARDIS_MACHINE_WS_URL environment variable should be set to ws://localhost:8001": "TARDIS_MACHINE_WS_URL 环境变量应设置为 ws://localhost:8001",
    "See supported venues": "查看支持的交易所",
    "Demonstrates streaming public market data from Binance without API keys.": "演示如何在不需 API 密钥的情况下使用 Binance 数据客户端获取公共市场数据。",
    "This example shows how to use the Binance data client for public market data without": "此示例展示如何在不需身份验证的情况下使用 Binance 数据客户端获取公共市场数据。",
    "requiring authentication. No API key or secret is needed.": "不需要 API 密钥或密钥。",
    "Example symbols for different BitMEX products": "不同 BitMEX 产品的示例代码",
    "Perpetual swap: XBTUSD (Bitcoin perpetual)": "永续合约：XBTUSD（比特币永续）",
    "Futures: XBTH25 (Bitcoin futures expiring March 2025)": "期货：XBTH25（2025年3月到期的比特币期货）",
    "Alt perpetuals: ETHUSD, SOLUSD, etc.": "其他永续合约：ETHUSD、SOLUSD 等",
    "Bitcoin perpetual swap": "比特币永续合约",
    "Bitcoin futures expiring December 2025": "2025年12月到期的比特币期货",
    "Ether perpetual swap": "以太坊永续合约",
    "Solana quoted in USDT spot": "以 USDT 计价的 Solana 现货",
    "Fractional size": "小数大小",
    "Contract size in USD": "以 USD 计价的合约大小",
    "Must be zero (hidden) or a positive multiple of lot size 100": "必须为零（隐藏）或手数 100 的正倍数",
    "Only reconcile this instrument": "仅对账此工具",
    "Market orders must be IOC": "市价单必须是 IOC",
    "configure appropriate interval": "配置适当的间隔",
    "Change to False to submit new orders": "更改为 False 以提交新订单",
    "Handle order submitted events.": "处理订单提交事件。",
    "Handle order accepted events.": "处理订单接受事件。",
    "Handle order rejected events.": "处理订单拒绝事件。",
    "Handle order filled events - KEY for understanding ratio spread execution.": "处理订单成交事件 - 理解比率价差执行的关键。",
    "Handle strategy stop and provide final analysis.": "处理策略停止并提供最终分析。",
    "Display current portfolio information.": "显示当前投资组合信息。",
    "Handle strategy start event.": "处理策略启动事件。",
    "Handle instrument response and place order.": "处理工具响应并下单。",
    "Place a market order for the futures calendar spread.": "为期货日历价差下市价单。",
    "Handle quote tick events for the spread instrument.": "处理价差工具的报价 tick 事件。",
    "Analyze what the fill represents.": "分析成交代表什么。",
    "Check current portfolio positions.": "检查当前投资组合仓位。",
    "Strategy to test 1x2 ratio spread execution with quantity 3.": "测试数量为 3 的 1x2 比率价差执行的策略。",
    "Automatically stop the node after a delay.": "延迟后自动停止节点。",
    "Handle new bar event.": "处理新 K 线事件。",
    "Handle position opened event.": "处理仓位开仓事件。",
    "Handle strategy stop event.": "处理策略停止事件。",
    "Create BUY MARKET order with PT and SL (both 10 ticks)": "创建市价买单，止盈和止损（均为 10 个 tick）",
    "Trade size: 1 contract": "交易大小：1 个合约",
    "Submit order and remember it": "提交订单并记住它",
    "Tested instrument id": "测试的工具 ID",
    "Note: Use the jupytext python package to be able to open this python file in jupyter as a notebook.": "注意：使用 jupytext python 包能够在 jupyter 中将此 python 文件作为笔记本打开。",
    "Also run `jupytext-config set-default-viewer` to open jupytext python files as notebooks by default.": "还运行 `jupytext-config set-default-viewer` 以默认将 jupytext python 文件作为笔记本打开。",
    "Test a simple limit order with price condition.": "测试带有价格条件的简单限价单。",
    "Get the actual contract ID from the instrument": "从工具获取实际合约 ID",
    "Price condition: trigger when ES goes above 6000": "价格条件：当 ES 超过 6000 时触发",
    "Transmit order when condition is met": "条件满足时传输订单",
    "Test a simple limit order with time condition.": "测试带有时间条件的简单限价单。",
    "Time condition: trigger 5 minutes from now": "时间条件：从现在起 5 分钟后触发",
    "IB accepts two formats:": "IB 接受两种格式：",
    "with timezone)": "带时区）",
    "UTC with dash)": "带破折号的 UTC）",
    "Try UTC format with dash (as mentioned in IB error message)": "尝试带破折号的 UTC 格式（如 IB 错误消息中所述）",
    "Test a simple limit order with volume condition.": "测试带有成交量条件的简单限价单。",
    "Volume condition: trigger when volume exceeds 100,000": "成交量条件：当成交量超过 100,000 时触发",
    "Cancel order when condition is met": "条件满足时取消订单",
    "Test a simple limit order with execution condition.": "测试带有执行条件的简单限价单。",
    "Execution condition: trigger when another symbol executes": "执行条件：当另一个代码执行时触发",
    "Test a simple limit order with margin condition.": "测试带有保证金条件的简单限价单。",
    "Margin condition: trigger when margin cushion is greater than 75%": "保证金条件：当保证金缓冲大于 75% 时触发",
    "Test a simple limit order with percent change condition.": "测试带有百分比变化条件的简单限价单。",
    "Percent change condition: trigger when contract increases by 5%": "百分比变化条件：当合约上涨 5% 时触发",
    "Test explicit OCA groups - create two separate orders with explicit OCA group": "测试显式 OCA 组 - 创建两个具有显式 OCA 组的单独订单",
    "Create two separate orders with explicit OCA group to test OCA functionality.": "创建两个具有显式 OCA 组的单独订单以测试 OCA 功能。",
    "Create explicit OCA group name": "创建显式 OCA 组名称",
    "Create first order with explicit OCA group": "创建第一个具有显式 OCA 组的订单",
    "ocaType=1 means cancel all others": "ocaType=1 表示取消所有其他订单",
    "Create second order with same OCA group": "创建具有相同 OCA 组的第二个订单",
    "Test if we can modify orders that are part of explicit OCA groups.": "测试我们是否可以修改属于显式 OCA 组的订单。",
    "Find the stop order to modify": "查找要修改的止损订单",
    "Attempting to modify OCA stop order from": "尝试修改 OCA 止损订单从",
    "to": "到",
    "OCA order modification command sent successfully": "OCA 订单修改命令发送成功",
    "Failed to modify OCA order": "修改 OCA 订单失败",
    "No stop order found to modify": "未找到要修改的止损订单",
    "Long leg fill": "多头腿成交",
    "contracts": "合约",
    "Expected: 1 contract per spread unit": "预期：每个价差单位 1 个合约",
    "Short leg fill": "空头腿成交",
    "Expected: 1 contract per spread unit (ESH6)": "预期：每个价差单位 1 个合约 (ESH6)",
    "SPREAD-LEVEL FILL": "价差级别成交",
    "LEG-LEVEL FILL": "腿级别成交",
    "Dynamic loading analysis": "动态加载分析",
    "Instrument loaded dynamically": "工具动态加载",
    "Quote ticks received": "收到的报价 tick",
    "Order and execution analysis": "订单和执行分析",
    "Total fills received": "收到的总成交数",
    "Total order events": "总订单事件数",
    "BUY fills": "买入成交",
    "total qty": "总数量",
    "SELL fills": "卖出成交",
    "Expected for 3 spread units: 3 long (ESZ5), 3 short (ESH6)": "3 个价差单位的预期：3 个多头 (ESZ5)，3 个空头 (ESH6)",
    "EXECUTION MATCHES EXPECTED RATIOS": "执行符合预期比率",
    "EXECUTION PATTERN UNCLEAR": "执行模式不明确",
    "No fills received": "未收到成交",
    "No positions in portfolio": "投资组合中没有仓位",
    "Starting Futures Spread Test (Dynamic Loading + Quote Ticks)...": "开始期货价差测试（动态加载 + 报价 tick）...",
    "This will:": "这将：",
    "Connect to Interactive Brokers": "连接到 Interactive Brokers",
    "Dynamically request the futures calendar spread instrument (not pre-loaded)": "动态请求期货日历价差工具（非预加载）",
    "Request market data to get tick size from tickReqParams (for futures spreads)": "请求市场数据以从 tickReqParams 获取 tick 大小（用于期货价差）",
    "Subscribe to quote ticks for the spread": "订阅价差的报价 tick",
    "Place a market order for 3 spread units": "为 3 个价差单位下市价单",
    "Monitor execution events and quote ticks for 60 seconds": "监控执行事件和报价 tick 60 秒",
    "Auto-stop and analyze results": "自动停止并分析结果",
    "IMPORTANT: Make sure TWS/IB Gateway is running!": "重要：确保 TWS/IB Gateway 正在运行！",
    "IMPORTANT: This will place a REAL market order in paper trading!": "重要：这将在模拟交易中下真实的市价单！",
    "Different client ID to avoid conflicts": "不同的客户端 ID 以避免冲突",
    "Use if trading via Polymarket Proxy": "如果通过 Polymarket 代理交易则使用",
    "enables UI verification, requires funder address": "启用 UI 验证，需要资助者地址",
    "Build futures chain": "构建期货链",
    "Build options chain": "构建期权链",
    "Min expiry days": "最小到期天数",
    "Max expiry days": "最大到期天数",
    "Removed - testing dynamic loading": "已移除 - 测试动态加载",
    "Testing spread": "测试价差",
    "Order: 3 spread units": "订单：3 个价差单位",
    "Expected execution: Long 3 ESZ5, Short 3 ESH6": "预期执行：多头 3 ESZ5，空头 3 ESH6",
    "THIS INTEGRATION IS STILL UNDER CONSTRUCTION.": "此集成仍在开发中。",
    "CONSIDER IT TO BE IN AN UNSTABLE BETA PHASE AND EXERCISE CAUTION.": "请将其视为不稳定的测试版并谨慎使用。",
    "If unset default is REALTIME": "如果未设置，默认为实时",
    "DAY required for combo orders by IB": "IB 要求组合订单使用 DAY",
    "Buy the spread": "买入价差",
    "spread units": "价差单位",
    "Below current market": "低于当前市场",
    "Above current market": "高于当前市场",
    "Same OCA group": "相同的 OCA 组",
    "Creating OCA orders with group": "创建 OCA 订单，组为",
}

def translate_line(line: str) -> str:
    """翻译单行注释"""
    if not line.strip().startswith("#"):
        return line
    
    # 保留原始行
    original = line.rstrip()
    
    # 检查是否已经是双语格式
    if " / " in original:
        return line
    
    # 提取注释内容（去掉 # 和前面的空格）
    comment_match = re.match(r"^(\s*#\s*)(.*)$", original)
    if not comment_match:
        return line
    
    prefix = comment_match.group(1)
    content = comment_match.group(2).strip()
    
    # 如果内容为空或者是 shebang，跳过
    if not content or content.startswith("!"):
        return line
    
    # 查找翻译
    translated = None
    for eng, chn in TRANSLATIONS.items():
        if eng in content:
            translated = content.replace(eng, chn)
            break
    
    # 如果没有找到精确匹配，尝试部分匹配
    if not translated:
        # 尝试翻译常见的短语
        for eng, chn in TRANSLATIONS.items():
            if eng.lower() in content.lower():
                translated = content.replace(eng, chn)
                break
    
    if translated and translated != content:
        # 创建双语格式
        return f"{prefix}{translated} / {content}\n"
    
    return line


def process_file(filepath: Path) -> bool:
    """处理单个文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        modified = False
        
        for line in lines:
            new_line = translate_line(line)
            if new_line != line:
                modified = True
            new_lines.append(new_line)
        
        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"✓ 已翻译: {filepath.relative_to(TARGET_DIR)}")
            return True
        else:
            print(f"- 无变化: {filepath.relative_to(TARGET_DIR)}")
            return False
            
    except Exception as e:
        print(f"✗ 错误: {filepath.relative_to(TARGET_DIR)} - {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("开始翻译 nautilus_trader 示例文件")
    print("=" * 60)
    
    translated_count = 0
    error_count = 0
    
    # 遍历所有 Python 文件
    for py_file in sorted(TARGET_DIR.rglob("*.py")):
        if process_file(py_file):
            translated_count += 1
    
    print("=" * 60)
    print(f"翻译完成！成功翻译 {translated_count} 个文件")
    print("=" * 60)


if __name__ == "__main__":
    main()
