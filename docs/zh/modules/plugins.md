---
title: 插件系统
description: 插件生命周期、事件总线、CLI 管理与安全沙箱
---

# 插件系统

## 概念

QuantCell 插件是遵循 `PluginBase` 协议的 Python 包，可订阅系统事件、扩展能力。
插件基座位于 `backend/plugins/`，包含插件加载器、事件总线与运行沙箱。

## 插件结构

```text
my-plugin/
└── plugin.py          # 至少一个 PluginBase 子类
```

最小实现：

```python
from plugins.plugin_base import PluginBase

class MyPlugin(PluginBase):
    name = "my-plugin"
    version = "1.0.0"

    def on_load(self):
        self.event_bus.subscribe("strategy:created", self.handle_strategy_created)

    def handle_strategy_created(self, event):
        ...
```

## 事件总线

插件间与系统内通过统一事件总线通信，常见事件如
`strategy:created`。订阅回调在事件发生时被调用，事件体为结构化 dict。

## CLI 管理

```bash
quantcell plugin install my-plugin.zip   # 安装插件包
quantcell plugin pack ./my-plugin        # 打包为 zip
quantcell plugin list                    # 查看已安装插件
```

## 安全沙箱

- 插件运行在受限沙箱中，与主进程隔离，异常不会拖垮主机
- 沙箱限制插件对文件系统与网络的越权访问
- 方向性建议：仅安装来源可信的插件

## 与 extensions 的关系

`backend/extensions/` 是**系统能力开关**（如 Prometheus 指标端点的启用），
属于内置功能配置；插件系统面向**外部扩展**。两者互不依赖。
