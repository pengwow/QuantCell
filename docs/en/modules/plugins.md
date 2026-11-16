---
title: Plugin System
description: Plugin lifecycle, event bus, CLI management, and the security sandbox
---

# Plugin System

## Concepts

A QuantCell plugin is a Python package following the `PluginBase` protocol
that can subscribe to system events and extend capabilities. The plugin
foundation lives in `backend/plugins/` and includes the loader, event bus,
and runtime sandbox.

## Plugin structure

```text
my-plugin/
└── plugin.py          # at least one PluginBase subclass
```

Minimal implementation:

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

## Event bus

Plugins and the system communicate through a unified event bus; typical
events include `strategy:created`. Subscription callbacks receive a
structured dict when the event fires.

## CLI management

```bash
quantcell plugin install my-plugin.zip   # install a plugin package
quantcell plugin pack ./my-plugin        # pack into a zip
quantcell plugin list                    # list installed plugins
```

## Security sandbox

- Plugins run inside a restricted sandbox isolated from the main process —
  plugin exceptions cannot take down the host
- The sandbox limits unauthorized filesystem and network access
- Rule of thumb: only install plugins from trusted sources

## Relationship with extensions

`backend/extensions/` are **system capability switches** (e.g. enabling the
Prometheus metrics endpoint) — built-in configuration. The plugin system
targets **external extensions**. The two are independent.
