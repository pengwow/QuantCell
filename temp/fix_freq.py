import sys
from pathlib import Path

# 修改Freq类的__str__方法
freq_module_path = Path("~/workspace/quantcell/.venv/lib/python3.12/site-packages/qlib/utils/time.py").expanduser()

# 读取原始代码
with open(freq_module_path, 'r') as f:
    code = f.read()

# 修改__str__方法
new_code = code.replace(
    "    def __str__(self):
        # trying to align to the filename of Qlib: day, 30min, 5min, 1min...
        return f"{self.count if self.count != 1 or self.base != 'day' else ''}{self.base}""",
    "    def __str__(self):
        # trying to align to the filename of Qlib: day, 30min, 5min, 1min...
        # Fix: return '1day' instead of 'day' for crypto data
        if self.base == 'day':
            return '1day'
        return f"{self.count if self.count != 1 else ''}{self.base}"