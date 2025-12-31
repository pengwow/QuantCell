# 在应用启动时导入
# 添加项目根目录到Python路径
# import sys
# from pathlib import Path
# project_root = Path(__file__).parent.parent.parent  # /Users/liupeng/workspace/qbot
# sys.path.append(str(project_root))
# from backend.qlib_integration.custom_freq import CustomFreq

# from qlib_integration.custom_freq import CustomFreq #.qlib_integration.custom_freq import CustomFreq  #qlib_integration.custom_freq import CustomFreq
import qlib
qlib.init()
# qlib.init(provider_uri='~/.qlib/crypto_data/qlib_data')

# from qlib.data import D
import qlib
qlib.init()
from qlib.data import D
ddd = D.calendar(start_time="2010-01-01", end_time="2017-12-31", freq="day")
print(ddd[:2])  # calendar data
# ddd = D.calendar(start_time="2025-11-01", end_time="2025-11-30", freq="day")
# print(ddd[:2])  # calendar data
