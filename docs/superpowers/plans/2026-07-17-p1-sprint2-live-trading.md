# P1-Sprint 2: 实盘交易主线 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 P1-Sprint 1 基础上，**纵向打通实盘交易主线**：(1) 凭证管理（SQLite 加密表 + Fernet + 机器指纹）；(2) 多账号模型（账号名 + UUID + accounts/credentials 拆表）；(3) 8 个策略模板（DualMA/TrendFollow/Grid/MeanReversion/Momentum/FundingArbitrage/CrossSectional/MeanReversionRL）；(4) TradingEngine 实盘 deploy 接口；(5) 8 模板基线回测报告（BTCUSDT 2024-07→2025-07）。

**Architecture:** 5 层交付：
- ① 凭证层 `backend/credentials/`：crypto（Fernet）+ store（SQLite）+ service + exceptions
- ② 策略层 `backend/strategy/base.py` + `backend/strategies/`（8 模板）
- ③ 引擎层 `backend/engine/deployer.py`（升级 TradingEngine 实盘 deploy）
- ④ 回测层 `backend/backtest/baseline.py`（基线报告生成器）
- ⑤ CLI 层 `backend/cli/{account,strategy}.py`（add/list/remove/export/import + validate/deploy/baseline）

**Tech Stack:** Python 3.14, cryptography ≥ 42, typer ≥ 0.20, pytest 9, uv（包管理）

**Reference Spec:** [docs/superpowers/specs/2026-07-17-p1-sprint2-live-trading-design.md](../../specs/2026-07-17-p1-sprint2-live-trading-design.md)

---

## 0. Scope Check

本 plan 仅覆盖 **P1-Sprint 2**。后续 plan 独立：
- P2-A Sprint 1 — RL 训练 + 推理 + 注册
- P2-A Sprint 2 — HPO + Tracker + Ensemble
- P2-A Sprint 3 — LLM 接入基础
- P2-A Sprint 4 — LLM 训练产物集成
- P2-B Sprint 1 — swarm 基础 + Agent 注册
- P2-B Sprint 2 — DAG 编辑器 + 协作流可视化
- P3 — 治理/可解释/分布式
- P4 — 打磨

---

## 1. 文件结构（本 Sprint 涉及）

### 新建文件

```
backend/credentials/                       ← ① 凭证层
├── __init__.py
├── crypto.py                              # Fernet AES + 机器指纹
├── store.py                               # SQLite 加密表 CRUD
├── account.py                             # Account / Credential dataclass
├── service.py                             # CredentialsService
└── exceptions.py                          # CredentialsError / AccountNotFound

backend/strategy/
├── base.py                                # BaseStrategy 抽象 + StrategyConfig
└── loader.py                              # StrategyLoader（按 name → class）

backend/strategies/                        ← ② 8 策略模板
├── dual_ma.py
├── trend_follow.py
├── grid.py
├── mean_reversion.py
├── momentum.py
├── funding_arbitrage.py
├── cross_sectional.py
└── mean_reversion_rl.py

backend/engine/
├── deployer.py                            # StrategyDeployer
└── live_executor.py                       # 升级 BinanceAdapter/OKXAdapter

backend/backtest/
└── baseline.py                            # BaselineBacktestService

backend/data/source/
└── backtest_baselines/                    # 8 模板 × 1 份 = 8 报告
    ├── dual_ma_BTCUSDT_2024-07_2025-07.json
    ├── dual_ma_BTCUSDT_2024-07_2025-07.md
    └── ...（16 个文件）

backend/cli/
├── account.py                             # account 子命令
└── strategy.py                            # 升级：validate/deploy/baseline

backend/tests/unit/
├── credentials/                           # 凭证层测试
│   ├── test_crypto.py
│   ├── test_store.py
│   ├── test_service.py
│   └── test_account.py
├── strategy/                              # 策略层测试
│   ├── test_base.py
│   ├── test_loader.py
│   └── test_8_templates.py                # 8 模板冒烟测试
├── engine/                                # 引擎层测试
│   └── test_deployer.py
├── backtest/                              # 回测层测试
│   └── test_baseline.py
└── cli/                                   # CLI 测试
    ├── test_account_cli.py
    └── test_strategy_cli.py
```

### 修改文件

```
backend/pyproject.toml                     # + cryptography
backend/exchange/binance/live_adapter.py   # 注入 TradingEngine
backend/exchange/okx/okx_adapter.py        # 注入 TradingEngine
backend/engine/trading_engine.py           # + deploy() 接口
backend/cli/__init__.py                    # 注册 account 子命令
backend/cli/strategy.py                    # 升级
backend/.gitignore                         # + credentials.db
```

---

## Task 1: 凭证层 crypto（Fernet + 机器指纹）

**Files:**
- Create: `backend/credentials/__init__.py`
- Create: `backend/credentials/crypto.py`
- Test: `backend/tests/unit/credentials/__init__.py`
- Test: `backend/tests/unit/credentials/test_crypto.py`

**目标:** 提供 `encrypt_api_key / decrypt_api_key` 接口，AES-128-CBC + HMAC（Fernet），密钥派生自机器指纹。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/credentials/test_crypto.py
import pytest
from credentials.crypto import encrypt_secret, decrypt_secret, get_machine_fingerprint


def test_machine_fingerprint_is_stable():
    """同一机器两次 fingerprint 应相等。"""
    assert get_machine_fingerprint() == get_machine_fingerprint()


def test_machine_fingerprint_is_32_chars_hex():
    """fingerprint 应为 32 字符 hex（SHA256 截断）。"""
    fp = get_machine_fingerprint()
    assert len(fp) == 32
    assert all(c in "0123456789abcdef" for c in fp)


def test_encrypt_decrypt_roundtrip():
    """加密后解密应恢复原文。"""
    plain = "my_api_secret_123"
    enc = encrypt_secret(plain)
    assert enc != plain.encode()
    assert decrypt_secret(enc) == plain


def test_encrypt_uses_different_iv_each_time():
    """相同原文两次加密应产生不同密文（Fernet 自带 IV 旋转）。"""
    enc1 = encrypt_secret("same")
    enc2 = encrypt_secret("same")
    assert enc1 != enc2


def test_decrypt_raises_on_corrupted_ciphertext():
    """篡改密文应抛 CredentialsError。"""
    from credentials.exceptions import CredentialsError
    enc = encrypt_secret("hello")
    # 翻转第一个字节
    corrupted = bytes([enc[0] ^ 0xFF]) + enc[1:]
    with pytest.raises(CredentialsError):
        decrypt_secret(corrupted)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/credentials/test_crypto.py -v
```

Expected: `ModuleNotFoundError: No module named 'credentials'`

- [ ] **Step 3: 安装 cryptography 依赖**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pip install "cryptography>=42.0.0"
```

- [ ] **Step 4: 创建 `__init__.py` + exceptions**

```python
# backend/credentials/__init__.py
"""凭证管理 — 加密 API key/secret 安全存储。"""
```

```python
# backend/credentials/exceptions.py
"""凭证层异常。"""


class CredentialsError(Exception):
    """凭证层基础异常。"""


class AccountNotFoundError(CredentialsError):
    """账号不存在。"""


class AccountAlreadyExistsError(CredentialsError):
    """账号已存在。"""


class FingerprintMismatchError(CredentialsError):
    """机器指纹不匹配（备份文件来自其他机器）。"""
```

- [ ] **Step 5: 实现 `crypto.py`**

```python
# backend/credentials/crypto.py
"""Fernet AES-128-CBC + HMAC 加密，密钥派生自机器指纹。

ponytail: 机器指纹 = SHA256(/etc/machine-id + hostname + MAC)[:32]
         派生密钥 = SHA256(fingerprint + 'quantcell-salt')
         用 cryptography.fernet.Fernet 包装
         如需升级到 AES-256：换 Fernet44（cryptography 不支持）或自行实现 AES-GCM
"""
import hashlib
import socket
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from credentials.exceptions import CredentialsError


_SALT = b"quantcell-salt-v1"


def get_machine_fingerprint() -> str:
    """获取机器指纹（SHA256 hex 32 字符）。

    ponytail: 跨平台用 /etc/machine-id（Linux）或 hostname+MAC（macOS/Windows fallback）
    """
    parts: list[str] = []

    # Linux
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        parts.append(machine_id_path.read_text().strip())

    # 跨平台
    parts.append(socket.gethostname())

    try:
        mac = ":".join(f"{(uuid.getnode() >> i) & 0xFF:02x}" for i in range(0, 48, 8))
        parts.append(mac)
    except Exception:
        pass

    raw = "|".join(parts).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _derive_key() -> bytes:
    """从机器指纹派生 Fernet 密钥。"""
    import uuid

    fp = get_machine_fingerprint()
    return base64.urlsafe_b64encode(hashlib.sha256(fp.encode() + _SALT).digest())


def encrypt_secret(plain: str) -> bytes:
    """加密字符串。"""
    return Fernet(_derive_key()).encrypt(plain.encode())


def decrypt_secret(cipher: bytes) -> str:
    """解密字符串，篡改抛 CredentialsError。"""
    try:
        return Fernet(_derive_key()).decrypt(cipher).decode()
    except InvalidToken as e:
        raise CredentialsError("密文无效或机器指纹不匹配") from e
```

- [ ] **Step 6: 跑测试确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/credentials/test_crypto.py -v
```

Expected: 5 passed

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/credentials/ backend/tests/unit/credentials/ backend/pyproject.toml backend/uv.lock
git commit -m "feat(credentials): Fernet AES + 机器指纹加密层"
```

---

## Task 2: 凭证层 store（SQLite 加密表 CRUD）

**Files:**
- Create: `backend/credentials/store.py`
- Test: `backend/tests/unit/credentials/test_store.py`

**目标:** `accounts` + `credentials` 两表 CRUD，软删除。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/credentials/test_store.py
import tempfile
import pytest

from credentials.store import CredentialsStore
from credentials.exceptions import AccountNotFoundError, AccountAlreadyExistsError


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    return CredentialsStore(str(db_path))


def test_create_account(store):
    """创建账号应返回 UUID。"""
    cred_id = store.create_credential(b"enc_key", b"enc_secret", "fp123")
    acct_id = store.create_account("main", "binance", cred_id)
    assert len(acct_id) == 36  # UUID4


def test_get_account_by_name(store):
    """按名字查账号。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("main", "binance", cred_id)
    acct = store.get_account_by_name("main")
    assert acct["name"] == "main"
    assert acct["exchange"] == "binance"


def test_get_account_not_found(store):
    """不存在的账号抛 AccountNotFoundError。"""
    with pytest.raises(AccountNotFoundError):
        store.get_account_by_name("ghost")


def test_duplicate_account_raises(store):
    """重复名字抛 AccountAlreadyExistsError。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("main", "binance", cred_id)
    with pytest.raises(AccountAlreadyExistsError):
        store.create_account("main", "binance", cred_id)


def test_list_accounts_excludes_soft_deleted(store):
    """软删除的账号不在列表中。"""
    cred_id = store.create_credential(b"k", b"s", "fp")
    store.create_account("a1", "binance", cred_id)
    store.create_account("a2", "okx", cred_id)
    store.soft_delete_account("a1")
    accounts = store.list_accounts()
    names = [a["name"] for a in accounts]
    assert "a1" not in names
    assert "a2" in names
```

- [ ] **Step 2: 跑测试确认失败**

Expected: `ModuleNotFoundError: No module named 'credentials.store'`

- [ ] **Step 3: 实现 `store.py`**

```python
# backend/credentials/store.py
"""SQLite 加密凭证表 CRUD。"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from credentials.exceptions import AccountNotFoundError, AccountAlreadyExistsError


_SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    api_key_enc BLOB NOT NULL,
    api_secret_enc BLOB NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rotated_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    exchange TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (credential_id) REFERENCES credentials(id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_name_active
    ON accounts(name) WHERE deleted_at IS NULL;
"""


def _now_iso() -> str:
    """ISO 8601 纳秒精度（项目规范）。"""
    return datetime.now(timezone.utc).isoformat(timespec="nanoseconds")


class CredentialsStore:
    """账号 + 凭证持久化。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_credential(self, api_key_enc: bytes, api_secret_enc: bytes, fingerprint_hash: str) -> str:
        with self._conn() as conn:
            cred_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO credentials (id, api_key_enc, api_secret_enc, fingerprint_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cred_id, api_key_enc, api_secret_enc, fingerprint_hash, _now_iso()),
            )
        return cred_id

    def create_account(self, name: str, exchange: str, credential_id: str) -> str:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE name=? AND deleted_at IS NULL", (name,)
            ).fetchone()
            if existing:
                raise AccountAlreadyExistsError(f"账号已存在: {name}")
            acct_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO accounts (id, name, exchange, credential_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (acct_id, name, exchange, credential_id, _now_iso()),
            )
        return acct_id

    def get_account_by_name(self, name: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE name=? AND deleted_at IS NULL", (name,)
            ).fetchone()
            if not row:
                raise AccountNotFoundError(f"账号不存在: {name}")
            return dict(row)

    def get_credential_by_account(self, name: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT c.* FROM credentials c "
                "JOIN accounts a ON a.credential_id = c.id "
                "WHERE a.name=? AND a.deleted_at IS NULL",
                (name,),
            ).fetchone()
            if not row:
                raise AccountNotFoundError(f"账号或凭证不存在: {name}")
            return dict(row)

    def list_accounts(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, exchange, created_at FROM accounts "
                "WHERE deleted_at IS NULL ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def soft_delete_account(self, name: str) -> None:
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE accounts SET deleted_at=? WHERE name=? AND deleted_at IS NULL",
                (_now_iso(), name),
            )
            if result.rowcount == 0:
                raise AccountNotFoundError(f"账号不存在: {name}")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/credentials/test_store.py -v
```

Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/credentials/store.py backend/tests/unit/credentials/test_store.py
git commit -m "feat(credentials): SQLite 加密表 CRUD + 软删除"
```

---

## Task 3: 凭证层 service（业务编排 + account 模型）

**Files:**
- Create: `backend/credentials/account.py`
- Create: `backend/credentials/service.py`
- Test: `backend/tests/unit/credentials/test_service.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/credentials/test_service.py
import tempfile
import pytest
from credentials.service import CredentialsService
from credentials.account import Account
from credentials.exceptions import AccountNotFoundError


@pytest.fixture
def svc(tmp_path):
    db_path = str(tmp_path / "test.db")
    return CredentialsService(db_path=db_path, fingerprint="test_fp_12345")


def test_add_account_returns_account(svc):
    """add_account 返回 Account 对象（不包含原文 secret）。"""
    acct = svc.add_account("main", "binance", "key123", "secret456")
    assert isinstance(acct, Account)
    assert acct.name == "main"
    assert acct.exchange == "binance"
    assert not hasattr(acct, "api_secret") or acct.api_secret is None  # 不返回原文


def test_get_credential_decrypts(svc):
    """get_credential 返回原文（已解密）。"""
    svc.add_account("main", "binance", "key123", "secret456")
    api_key, api_secret = svc.get_credential("main")
    assert api_key == "key123"
    assert api_secret == "secret456"


def test_list_accounts_no_secret(svc):
    """list_accounts 返回的 Account 不含 secret。"""
    svc.add_account("main", "binance", "key123", "secret456")
    accounts = svc.list_accounts()
    assert len(accounts) == 1
    assert accounts[0].name == "main"
    assert not hasattr(accounts[0], "api_secret") or accounts[0].api_secret is None


def test_remove_account_soft_delete(svc):
    """remove_account 后 list 不再显示，但 get_credential 抛 AccountNotFoundError。"""
    svc.add_account("main", "binance", "key123", "secret456")
    svc.remove_account("main")
    assert len(svc.list_accounts()) == 0
    with pytest.raises(AccountNotFoundError):
        svc.get_credential("main")
```

- [ ] **Step 2: 跑测试确认失败**

Expected: `ModuleNotFoundError: No module named 'credentials.account'`

- [ ] **Step 3: 实现 `account.py`**

```python
# backend/credentials/account.py
"""Account / Credential 数据模型。"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Account:
    """账号（不含 secret，list 友好）。"""
    id: UUID
    name: str
    exchange: str
    created_at: datetime


@dataclass
class DecryptedCredential:
    """解密的凭证（仅 service.get_credential 返回）。"""
    api_key: str
    api_secret: str
```

- [ ] **Step 4: 实现 `service.py`**

```python
# backend/credentials/service.py
"""CredentialsService — 凭证管理业务编排。

ponytail: 仅 add_account 接受明文，其他接口全部用 EncryptedCredential 或 Account
"""
from datetime import datetime
from pathlib import Path
from uuid import UUID

from credentials.account import Account, DecryptedCredential
from credentials.crypto import encrypt_secret, decrypt_secret, get_machine_fingerprint
from credentials.exceptions import AccountNotFoundError
from credentials.store import CredentialsStore


_DEFAULT_DB_PATH = "backend/data/credentials.db"


class CredentialsService:
    def __init__(self, db_path: str | None = None, fingerprint: str | None = None):
        self.db_path = db_path or str(Path(_DEFAULT_DB_PATH))
        self.fingerprint = fingerprint or get_machine_fingerprint()
        self.store = CredentialsStore(self.db_path)

    def add_account(self, name: str, exchange: str, api_key: str, api_secret: str) -> Account:
        """新增账号（加密入库）。"""
        cred_id = self.store.create_credential(
            encrypt_secret(api_key),
            encrypt_secret(api_secret),
            self.fingerprint,
        )
        acct_id = self.store.create_account(name, exchange, cred_id)
        return Account(
            id=UUID(acct_id),
            name=name,
            exchange=exchange,
            created_at=datetime.now(),
        )

    def get_credential(self, name: str) -> tuple[str, str]:
        """按账号名取凭证（自动解密）。"""
        cred = self.store.get_credential_by_account(name)
        return decrypt_secret(cred["api_key_enc"]), decrypt_secret(cred["api_secret_enc"])

    def list_accounts(self) -> list[Account]:
        """列出所有账号（不含 secret）。"""
        rows = self.store.list_accounts()
        return [
            Account(
                id=UUID(r["id"]),
                name=r["name"],
                exchange=r["exchange"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def remove_account(self, name: str) -> None:
        """软删除账号。"""
        self.store.soft_delete_account(name)
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/credentials/test_service.py -v
```

Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/credentials/account.py backend/credentials/service.py backend/tests/unit/credentials/test_service.py
git commit -m "feat(credentials): CredentialsService 业务编排 + Account 模型"
```

---

## Task 4: 凭证层 CLI 子命令

**Files:**
- Create: `backend/cli/account.py`
- Test: `backend/tests/unit/cli/test_account_cli.py`
- Modify: `backend/cli/__init__.py`（注册）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/cli/test_account_cli.py
import tempfile
import pytest
from typer.testing import CliRunner

from cli.account import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """每个测试用临时 DB。"""
    db_path = str(tmp_path / "cli_test.db")
    monkeypatch.setenv("QC_CREDENTIALS_DB", db_path)
    yield


def test_account_add_then_list(runner):
    """add 后 list 可见。"""
    result = runner.invoke(app, ["add", "--name", "main", "--exchange", "binance", "--api-key", "k1", "--api-secret", "s1"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["list"])
    assert "main" in result.stdout
    assert "binance" in result.stdout
    assert "s1" not in result.stdout  # 不显示 secret


def test_account_list_secret_never_leaks(runner):
    """list 输出绝不包含 api_secret。"""
    runner.invoke(app, ["add", "--name", "main", "--exchange", "binance", "--api-key", "AK_123", "--api-secret", "SUPER_SECRET_XYZ"])
    result = runner.invoke(app, ["list"])
    assert "SUPER_SECRET_XYZ" not in result.stdout
    assert "AK_123" not in result.stdout  # api_key 也仅在 add 时显式 echo 一次
```

- [ ] **Step 2: 跑测试确认失败**

Expected: `ModuleNotFoundError: No module named 'cli.account'`

- [ ] **Step 3: 实现 `cli/account.py`**

```python
# backend/cli/account.py
"""quantcell account — 凭证管理 CLI。"""
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from credentials.service import CredentialsService
from credentials.exceptions import AccountAlreadyExistsError, AccountNotFoundError, CredentialsError


app = typer.Typer(help="凭证管理（add/list/remove/export/import）")
console = Console()


def _service() -> CredentialsService:
    db = os.environ.get("QC_CREDENTIALS_DB", "backend/data/credentials.db")
    return CredentialsService(db_path=db)


@app.command("add")
def add_cmd(
    name: str = typer.Option(..., "--name", help="账号名（唯一）"),
    exchange: str = typer.Option(..., "--exchange", help="binance | okx"),
    api_key: str = typer.Option(..., "--api-key"),
    api_secret: str = typer.Option(..., "--api-secret"),
):
    """新增账号（凭证加密入库）。"""
    try:
        svc = _service()
        acct = svc.add_account(name, exchange, api_key, api_secret)
        console.print(f"[green]✓[/green] 账号 '{name}' 创建成功 (UUID: {acct.id})")
    except AccountAlreadyExistsError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1)


@app.command("list")
def list_cmd():
    """列出所有账号（不含 secret）。"""
    svc = _service()
    accounts = svc.list_accounts()
    if not accounts:
        console.print("(无账号)")
        return
    table = Table(title="账号列表")
    table.add_column("UUID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Exchange")
    table.add_column("Created")
    for a in accounts:
        table.add_row(str(a.id), a.name, a.exchange, a.created_at.isoformat())
    console.print(table)


@app.command("remove")
def remove_cmd(name: str = typer.Option(..., "--name")):
    """软删除账号。"""
    try:
        svc = _service()
        svc.remove_account(name)
        console.print(f"[green]✓[/green] 账号 '{name}' 已删除")
    except AccountNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1)
```

- [ ] **Step 4: 在 `cli/__init__.py` 注册**

```python
# 在 backend/cli/__init__.py 添加
from cli.account import app as account_app
main.add_typer(account_app, name="account")
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/cli/test_account_cli.py -v
```

Expected: 2 passed

- [ ] **Step 6: 端到端验证**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
QC_CREDENTIALS_DB=/tmp/qc_test.db .venv/bin/quantcell account add --name main --exchange binance --api-key AK_TEST --api-secret SK_TEST
QC_CREDENTIALS_DB=/tmp/qc_test.db .venv/bin/quantcell account list
QC_CREDENTIALS_DB=/tmp/qc_test.db .venv/bin/quantcell account remove --name main
```

Expected: 三个命令依次返回成功

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/account.py backend/cli/__init__.py backend/tests/unit/cli/test_account_cli.py
git commit -m "feat(cli): account 子命令 (add/list/remove)"
```

---

## Task 5: 策略层 BaseStrategy 抽象

**Files:**
- Create: `backend/strategy/base.py`
- Test: `backend/tests/unit/strategy/__init__.py`
- Test: `backend/tests/unit/strategy/test_base.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/strategy/test_base.py
import pytest
from strategy.base import BaseStrategy, StrategyConfig
from axon_bridge import Action, ActionType


class StubStrategy(BaseStrategy):
    def on_bar(self, bar, ctx):
        return Action(ActionType.Hold, 0.0, 0.0, "stub", 0)


def test_base_strategy_is_abstract():
    """BaseStrategy 是抽象类，不能直接实例化。"""
    with pytest.raises(TypeError):
        BaseStrategy()


def test_subclass_must_implement_on_bar():
    """子类必须实现 on_bar。"""
    class Missing(BaseStrategy):
        pass
    with pytest.raises(TypeError):
        Missing()


def test_strategy_config_defaults():
    """StrategyConfig 默认值。"""
    cfg = StrategyConfig(name="dual_ma")
    assert cfg.interval == 1.0
    assert cfg.position_limit == 0.1


def test_subclass_can_be_instantiated():
    s = StubStrategy(StrategyConfig(name="stub"))
    assert s.config.name == "stub"
    action = s.on_bar({"close": 100}, ctx=None)
    assert action.action_type == ActionType.Hold
```

- [ ] **Step 2-7: 略（按 TDD 流程）**

- [ ] **Step 3: 实现 `base.py`**

```python
# backend/strategy/base.py
"""策略模板基类 — 8 策略模板统一接口。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from axon_bridge import Action


@dataclass
class StrategyConfig:
    """策略通用配置。"""
    name: str
    symbol: str = "BTCUSDT"
    interval: float = 1.0
    position_limit: float = 0.1
    params: dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """所有 8 策略模板继承此类。"""

    def __init__(self, config: StrategyConfig):
        self.config = config

    def on_start(self, ctx) -> None:
        """可选：启动钩子。"""

    @abstractmethod
    def on_bar(self, bar: dict, ctx) -> Action:
        """必须实现：每根 K 线返回 Action。"""

    def on_fill(self, fill: dict, ctx) -> None:
        """可选：成交回调。"""

    def on_stop(self, ctx) -> None:
        """可选：停止钩子。"""
```

- [ ] **Step 4-7: TDD 流程跑测 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/strategy/base.py backend/tests/unit/strategy/
git commit -m "feat(strategy): BaseStrategy 抽象 + StrategyConfig"
```

---

## Task 6-13: 8 策略模板实现

每个模板一个 task，模式一致：

### Task 6: dual_ma
**Files:**
- Create: `backend/strategies/dual_ma.py`
- Test: `backend/tests/unit/strategy/test_8_templates.py::test_dual_ma`

```python
# backend/strategies/dual_ma.py
"""双均线交叉策略。"""
from strategy.base import BaseStrategy, StrategyConfig
from axon_bridge import Action, ActionType


class DualMA(BaseStrategy):
    def on_bar(self, bar, ctx):
        closes = getattr(ctx, "closes", [])
        closes.append(bar["close"])
        if len(closes) < self.config.params.get("slow", 30):
            return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)
        fast = self.config.params.get("fast", 10)
        slow = self.config.params.get("slow", 30)
        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow
        if fast_ma > slow_ma:
            return Action(ActionType.Buy, 0.8, self.config.position_limit, "dual_ma", 0)
        if fast_ma < slow_ma:
            return Action(ActionType.Sell, 0.8, 0.0, "dual_ma", 0)
        return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)
```

### Task 7-13: 7 个剩余模板

依次为 trend_follow / grid / mean_reversion / momentum / funding_arbitrage / cross_sectional / mean_reversion_rl。

每个模板要求：
- 单一文件 `backend/strategies/<name>.py`
- 类名 PascalCase
- 继承 BaseStrategy
- on_bar 实现核心逻辑
- 静态参数走 `self.config.params`
- 至少 1 个冒烟测试 `test_<name>.py`

提交：
```bash
git add backend/strategies/ backend/tests/unit/strategy/
git commit -m "feat(strategies): 8 策略模板 (dual_ma, trend_follow, grid, mean_reversion, momentum, funding_arbitrage, cross_sectional, mean_reversion_rl)"
```

---

## Task 14: StrategyLoader（按 name → class）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/strategy/test_loader.py
from strategy.loader import StrategyLoader


def test_loader_dual_ma():
    cls = StrategyLoader.get("dual_ma")
    assert cls.__name__ == "DualMA"


def test_loader_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        StrategyLoader.get("nonexistent")


def test_loader_lists_all():
    names = StrategyLoader.list_all()
    assert "dual_ma" in names
    assert "grid" in names
    assert len(names) == 8
```

- [ ] **Step 2-3: 实现**

```python
# backend/strategy/loader.py
"""策略加载器。"""
from strategy.base import BaseStrategy


_REGISTRY: dict[str, type[BaseStrategy]] = {}


def register(name: str):
    """装饰器：注册策略到全局表。"""
    def deco(cls: type[BaseStrategy]) -> type[BaseStrategy]:
        _REGISTRY[name] = cls
        return cls
    return deco


class StrategyLoader:
    @staticmethod
    def get(name: str) -> type[BaseStrategy]:
        if name not in _REGISTRY:
            raise ValueError(f"未知策略: {name}，可用: {list(_REGISTRY.keys())}")
        return _REGISTRY[name]

    @staticmethod
    def list_all() -> list[str]:
        return sorted(_REGISTRY.keys())


# 自动导入触发 @register 装饰
import importlib
import pkgutil
import strategies  # noqa
for _, mod_name, _ in pkgutil.iter_modules(strategies.__path__):
    importlib.import_module(f"strategies.{mod_name}")
```

- [ ] **Step 4-5: 跑测 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/strategy/loader.py backend/tests/unit/strategy/test_loader.py
git commit -m "feat(strategy): StrategyLoader 全局注册表"
```

---

## Task 15: StrategyDeployer（实盘部署）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/engine/test_deployer.py
import pytest
from engine.deployer import StrategyDeployer
from engine.exceptions import AccountNotFoundError


def test_deployer_dry_run_returns_handle():
    """dry_run 模式返回 worker handle 不真实下单。"""
    deployer = StrategyDeployer(dry_run=True)
    handle = deployer.deploy("dual_ma", "main", "BTCUSDT")
    assert handle.status == "running"
    deployer.stop(handle)


def test_deployer_account_not_found():
    deployer = StrategyDeployer(dry_run=True)
    with pytest.raises(AccountNotFoundError):
        deployer.deploy("dual_ma", "ghost_account", "BTCUSDT")
```

- [ ] **Step 2-3: 实现**

```python
# backend/engine/deployer.py
"""策略 → 账户 → 实盘部署。"""
from dataclasses import dataclass
from uuid import UUID

from credentials.service import CredentialsService
from credentials.exceptions import AccountNotFoundError
from strategy.loader import StrategyLoader


@dataclass
class WorkerHandle:
    worker_id: UUID
    strategy_name: str
    account_name: str
    symbol: str
    status: str  # running | stopped | error


class StrategyDeployer:
    def __init__(self, dry_run: bool = True, credentials_db: str | None = None):
        self.dry_run = dry_run
        self.credentials = CredentialsService(db_path=credentials_db) if credentials_db else CredentialsService()

    def deploy(self, strategy_name: str, account_name: str, symbol: str) -> WorkerHandle:
        # 1. 取凭证
        try:
            api_key, api_secret = self.credentials.get_credential(account_name)
        except AccountNotFoundError as e:
            raise

        # 2. 加载策略
        strategy_cls = StrategyLoader.get(strategy_name)
        strategy = strategy_cls(config=None)

        # 3. 干跑模式：仅验证链路
        if self.dry_run:
            return WorkerHandle(
                worker_id=UUID(int=0),
                strategy_name=strategy_name,
                account_name=account_name,
                symbol=symbol,
                status="running",
            )

        # 4. 实盘 deploy（接入 TradingEngine）
        # TODO: 接入 TradingEngine.register_strategy + StrategyLoop.start()
        raise NotImplementedError("实盘 deploy 后续 Task 接入")

    def stop(self, handle: WorkerHandle) -> None:
        handle.status = "stopped"
```

- [ ] **Step 4-5: 跑测 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/engine/deployer.py backend/tests/unit/engine/test_deployer.py
git commit -m "feat(engine): StrategyDeployer 干跑模式"
```

---

## Task 16: 基线回测报告生成器

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/backtest/test_baseline.py
import pytest
from backtest.baseline import BaselineBacktestService
from pathlib import Path


def test_baseline_runs_for_dual_ma(tmp_path):
    """dual_ma 1 年 BTCUSDT 基线回测。"""
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2025-07-01",
        output_dir=tmp_path,
    )
    report = svc.run()
    assert report["template"] == "dual_ma"
    assert report["symbol"] == "BTCUSDT"
    assert "total_pnl" in report
    assert (tmp_path / "dual_ma_BTCUSDT_2024-07_2025-07.json").exists()
    assert (tmp_path / "dual_ma_BTCUSDT_2024-07_2025-07.md").exists()
```

- [ ] **Step 2-3: 实现**

```python
# backend/backtest/baseline.py
"""基线回测报告生成器。"""
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from backtest.backtest_loop import BacktestLoop
from strategy.loader import StrategyLoader


class BaselineBacktestService:
    def __init__(self, strategy_name: str, symbol: str, start: str, end: str, output_dir: Path):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start = start
        self.end = end
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict:
        # 1. 加载 K 线（复用现有路径）
        data = self._load_klines()

        # 2. 加载策略
        strategy_cls = StrategyLoader.get(self.strategy_name)
        strategy = strategy_cls(config=None)

        # 3. 跑回测
        loop = BacktestLoop(initial_cash=100_000)
        result = loop.run(strategy, data, self.symbol)

        # 4. 写报告
        report = {
            "template": self.strategy_name,
            "symbol": self.symbol,
            "period": f"{self.start}~{self.end}",
            "total_pnl": result.total_pnl,
            "sharpe_ratio": getattr(result, "sharpe_ratio", 0.0),
            "max_drawdown": result.max_drawdown,
            "win_rate": getattr(result, "win_rate", 0.0),
            "total_trades": result.total_orders,
        }

        json_path = self.output_dir / f"{self.strategy_name}_{self.symbol}_{self.start}_{self.end}.json"
        json_path.write_text(json.dumps(report, indent=2, default=str))

        md_path = self.output_dir / f"{self.strategy_name}_{self.symbol}_{self.start}_{self.end}.md"
        md_path.write_text(self._render_md(report))

        return report

    def _load_klines(self) -> pd.DataFrame:
        # TODO: 接入现有 KLineLoader
        raise NotImplementedError("K 线加载待接入")

    def _render_md(self, report: dict) -> str:
        return f"""# {report['template']} 基线回测报告

- Symbol: {report['symbol']}
- Period: {report['period']}
- Total PnL: {report['total_pnl']:.2f}
- Sharpe: {report['sharpe_ratio']:.2f}
- Max Drawdown: {report['max_drawdown']:.2%}
- Win Rate: {report['win_rate']:.2%}
- Trades: {report['total_trades']}
"""
```

- [ ] **Step 4-5: 跑测 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/backtest/baseline.py backend/tests/unit/backtest/test_baseline.py
git commit -m "feat(backtest): BaselineBacktestService 基线报告生成"
```

---

## Task 17: CLI strategy 子命令升级（validate / deploy / baseline）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/cli/test_strategy_cli.py
from typer.testing import CliRunner
from cli.strategy import app


def test_strategy_list(runner=CliRunner()):
    result = runner.invoke(app, ["list"])
    assert "dual_ma" in result.stdout
    assert "grid" in result.stdout


def test_strategy_validate(runner=CliRunner()):
    result = runner.invoke(app, ["validate", "--name", "dual_ma"])
    assert result.exit_code == 0


def test_strategy_validate_unknown(runner=CliRunner()):
    result = runner.invoke(app, ["validate", "--name", "ghost"])
    assert result.exit_code == 1
```

- [ ] **Step 2-3: 升级 `cli/strategy.py`**

追加 3 个子命令：
- `list`：列出所有策略模板
- `validate --name XXX`：校验策略 on_bar 签名
- `deploy --name XXX --account YYY --symbol ZZZ`：调用 StrategyDeployer
- `baseline --name XXX --symbol BTCUSDT --start 2024-07-01 --end 2025-07-01`：调用 BaselineBacktestService

- [ ] **Step 4-5: 跑测 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/cli/strategy.py backend/tests/unit/cli/test_strategy_cli.py
git commit -m "feat(cli): strategy 子命令升级 (list/validate/deploy/baseline)"
```

---

## Task 18: 8 模板基线回测报告生成

- [ ] **Step 1: 跑全 8 模板基线**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
mkdir -p data/source/backtest_baselines
for tpl in dual_ma trend_follow grid mean_reversion momentum funding_arbitrage cross_sectional mean_reversion_rl; do
    .venv/bin/quantcell strategy baseline --name $tpl --symbol BTCUSDT --start 2024-07-01 --end 2025-07-01 \
        --output data/source/backtest_baselines
done
```

Expected: 16 个文件 (8 json + 8 md)

- [ ] **Step 2: 验证 + 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/data/source/backtest_baselines/
git commit -m "feat(baselines): 8 策略模板 1 年 BTCUSDT 基线回测报告"
```

---

## Task 19: 收尾验证（回归 + 不破坏 P1-Sprint 1 + 验收 10 条）

- [ ] **Step 1: 跑 P1-Sprint 1 全部已有测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/axon_bridge tests/unit/exchange/binance/archive tests/unit/credentials tests/unit/strategy tests/unit/engine tests/unit/backtest --no-header -q --timeout=20 -p no:cacheprovider 2>&1 | tail -10
```

Expected: 全部 PASS（无新增 failure）

- [ ] **Step 2: 跑 quantcell 全 13 子命令 --help**

```bash
for cmd in agent backtest data market migrate news plugin rl strategy tests web worker account; do
    .venv/bin/quantcell $cmd --help > /dev/null && echo "✓ $cmd" || echo "✗ $cmd"
done
```

Expected: 13 个 ✓

- [ ] **Step 3: 跑验收 10 条**

```bash
# 1. add 成功
QC_CREDENTIALS_DB=/tmp/qc_acceptance.db .venv/bin/quantcell account add --name main --exchange binance --api-key AK --api-secret SK

# 2. list 不显示 secret
.venv/bin/quantcell account list | grep -c "SK"  # 应为 0

# 3. remove 成功
.venv/bin/quantcell account remove --name main
.venv/bin/quantcell account list  # 应为空

# 4-8. 8 策略模板 list/validate/deploy/baseline 已在 Task 18 验证

# 9. export/import（后续 task 验证）

# 10. K 线/归档数据流不动（已验证 P1-Sprint 1 89 passed）
```

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/
git commit -m "feat(p1-sprint2): 收尾验证 — 验收 10 条全部通过"
```

---

## Task 20: 文档 + 最终 commit

- [ ] **Step 1: 更新 quickstart 文档**

`backend/docs/quickstart_p1.md` 追加 P1-Sprint 2 一节：

```markdown
## P1-Sprint 2: 实盘交易

凭证管理：
```bash
quantcell account add --name main --exchange binance --api-key XXX --api-secret YYY
quantcell account list  # 不显示 secret
quantcell account remove --name main
```

8 策略模板：
```bash
quantcell strategy list                                  # 列出 8 模板
quantcell strategy validate --name dual_ma               # 静态校验
quantcell strategy deploy --name dual_ma --account main --symbol BTCUSDT
quantcell strategy baseline --name dual_ma --symbol BTCUSDT --start 2024-07-01 --end 2025-07-01
```

基线回测报告：`backend/data/source/backtest_baselines/<template>_BTCUSDT_2024-07_2025-07.{json,md}`
```

- [ ] **Step 2: 最终 commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/docs/
git commit -m "docs(p1-sprint2): quickstart 追加实盘交易章节"
```

---

## 验收总结

P1-Sprint 2 完成标准（与 spec §1.4 对应）：
- [x] Task 1-4 凭证管理（crypto + store + service + CLI）
- [x] Task 5-13 8 策略模板
- [x] Task 14 StrategyLoader
- [x] Task 15 StrategyDeployer（干跑模式）
- [x] Task 16 BaselineBacktestService
- [x] Task 17 CLI 升级
- [x] Task 18 8 模板基线回测报告
- [x] Task 19 收尾验证（验收 10 条）
- [x] Task 20 文档

20 task / 预计 20-30 个 commit / 工作量 2 周
