---
title: REST API
description: Overview of /api/v1 route groups and interface conventions
---

# REST API

All business routes are mounted under the **`/api/v1`** prefix. For full
parameters, schemas and response models, refer to the Swagger docs — this
page only provides the route-group map.

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health check**: `http://localhost:8000/health`
- **Prometheus metrics**: `/metrics` (when the capability flag is enabled)

## Route group map

| Route group | Responsibility |
|--------|------|
| `/api/v1/strategy` | Strategy CRUD, generation, listing |
| `/api/v1/backtest` | Backtest job submission, result queries |
| `/api/v1/factor` | Factor analysis, snapshots |
| `/api/v1/rl` | RL training, evaluation, lifecycle |
| `/api/v1/data` | Data download, import, quality |
| `/api/v1/marketdata` | Market data queries |
| `/api/v1/agent` | AI Agent sessions |
| `/api/v1/account` | Accounts and credentials |
| `/api/v1/plugin` | Plugin management |
| `/api/v1/research` | Research modules (snapshots, etc.) |
| `/api/v1/worker` | Worker status and management |
| `/api/v1/credentials` | Exchange credentials |
| `/api/v1/capabilities` | Capability flag queries |
| `/api/v1/scheduled-tasks` | Scheduled tasks |
| `/api/v1/extensions` | System extensions / capability flag management |
| `/ws/research` | Research realtime channel (see [WebSocket](websocket.md)) |

## Common conventions

### Error handling

Errors are raised uniformly via FastAPI `HTTPException`, carrying a status
code and a readable message:

```json
{
  "detail": "strategy 'dual_ma' not found"
}
```

Common status codes: `400` bad request, `404` resource not found,
`422` Pydantic validation failure, `500` server error.

### Parameter validation

All request bodies / query parameters are validated by Pydantic schemas;
invalid input fails immediately with `422`.

### Layering constraint

The route layer only receives parameters and calls services — business
logic lives in the service layer. As a result, REST responses stay
consistent with internal contracts such as the backtest `BacktestResult`.

## Versioning

The `/api/v1` prefix reserves room for upgrades; future breaking changes
will ship as a parallel `/api/v2`. All current frontend / desktop / MCP
clients are built on `/api/v1`.

## MCP Server

`backend/mcp_server/` exposes an MCP (Model Context Protocol) server whose
capabilities mirror the REST API, callable from MCP clients such as
Claude Desktop.
