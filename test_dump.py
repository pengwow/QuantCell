import sys
import os
# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

from qlib.scripts.dump_bin import DumpDataAll

# 创建DumpDataAll实例并运行转换
dumper = DumpDataAll(
    data_path='.',
    qlib_dir='./test_qlib_data',
    freq='day',
    date_field_name='date',
    file_suffix='.csv',
    symbol_field_name='symbol',
    include_fields='date,open,high,low,close,volume',
    limit_nums=2
)

dumper.dump()
