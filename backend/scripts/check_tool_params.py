#!/usr/bin/env python3
"""检查数据库中工具参数数据状态"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.db.database import init_database_config, SessionLocal
from collector.db.models import SystemConfig

init_database_config()
db = SessionLocal()

# 查询所有 agent.tools 开头的配置
configs = db.query(SystemConfig).filter(
    SystemConfig.key.like('agent.tools.%')
).all()

print('=' * 60)
print('📊 数据库中工具参数数据检查')
print('=' * 60)

if configs:
    print(f'\n✅ 找到 {len(configs)} 条工具参数记录:\n')
    for c in configs:
        value_display = c.value[:20] + '...' if len(c.value) > 20 else c.value
        if c.is_sensitive:
            value_display = '***敏感信息***'
        print(f'  🔑 {c.key}')
        print(f'     值: {value_display}')
        print(f'     描述: {c.description or "无"}')
        print(f'     工具: {c.name}')
        print()
else:
    print('\n❌ 未找到任何工具参数数据!')
    print('   数据库中没有 agent.tools.* 相关的配置记录')
    print('   这就是接口返回空数据的根本原因')

db.close()
