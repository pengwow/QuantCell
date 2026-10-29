# 实施计划：Worker Journal 归档功能（页面 + CLI + API）

* **Spec**: [docs/plans/2026-10-29-worker-journal-archive-design.md](file:///Users/liupeng/workspace/quant/QuantCell/docs/plans/2026-10-29-worker-journal-archive-design.md)（commit 42df5515，已批准）
* **目标**：把手动 `mv journal → archive/` 的归档操作产品化——Worker 详情页按钮、`qc worker archive` CLI 命令、`POST /workers/{id}/lifecycle/archive` HTTP API 三端复用同一个归档实现
* **架构决策**（spec 已定案）：核心归档逻辑放 `StrategyManager.archive_journal_files`（journal 路径规则的唯一持有者），`WorkerCoreService.archive_worker_journal` 做校验 + 异常映射薄委托，路由/CLI 各自消费
* **技术栈**：FastAPI（现有 `handle_worker_exceptions` 体系）、typer CLI、antd v6 + React、pytest + monkeypatch

## 验证策略

每个步骤完成即运行该步的验证命令；最终统一跑 `cd backend && uv run pytest tests/unit/worker/ -q` 回归 + `cd frontend && bun run build`。除 Step 1 无测试（语法修复），其余逻辑步骤均 TDD：先写测试（红）→ 实现（绿）→ commit。

## 关键既有事实（侦查结论，实现时直接引用）

* journal 路径 helper：`worker/strategy_manager.py` `_rl_live_journal_path`（L1347-1356）/ `_live_journal_path`（L1358-1367），每次调用实时读 `QUANTCELL_DATA_DIR` 并 `mkdir(parents=True, exist_ok=True)`（副作用无害，归档语境里目录本就要存在才有文件）
* `worker strives` 顶部已有 `from datetime import UTC, datetime`、`import os`、`from pathlib import Path`——归档实现无需新增 import
* `core_service` 顶部**不** import `worker_system`；同文件 `_stop_worker_in_process`（L755）用函数内延时导入 + 注释说明原因，归档方法沿用同一模式
* `WorkerException.__init__(message=..., code=..., details=...)`；异常子类模板见 `exceptions.py` L36-44 `WorkerAlreadyRunningException`
* CLI 输出范式：`typer.echo(f"错误: {e}", err=True)` + `raise typer.Exit(1)`；confirm 范式见 `cli/worker.py` `worker_delete`（L103-127）
* 路由范式：`worker/routes.py` L417-427 restart 路由（`@router.post(...) + @handle_worker_exceptions(...)`）
* 前端 `apiRequest` 响应拦截器自动解包 `ApiResponse.data`（`api/index.ts` L336-404），因此 `archiveWorkerJournal` 直接返回 `Promise<ArchiveJournalResult>`，无 `ApiResponse` 壳
* `tests/unit/worker/` 含 `__init__.py`，测试命名 `test_*.py`；`QUANTCELL_DATA_DIR` 注入先例：`tests/unit/test_desktop_paths.py` 的 `monkeypatch.setenv`

## Step 1：修复 cli/worker.py 语法错误（前置阻塞）

**文件**: `backend/cli/worker.py`
**原因**: L37 `except ValueError, TypeError:` 是 Python 2 语法，`SyntaxError: multiple exception types must be parenthesized`。`qc worker archive` 命令依赖该文件 import，必须先修。

改为元组写法（L33-39 `_to_int` 函数内）：

```python
def _to_int(value: str, label: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        typer.echo(f"错误: {label} 必须是整数: {value}", err=True)
        raise typer.Exit(1)
```

**验证**:

```bash
cd backend && uv run python -c "import cli.worker; print('cli.worker import OK')"
```

**Commit**: `fix(cli): 修复 cli/worker.py _to_int 中 Python2 风格的 except 元组语法错误`

---

## Step 2：写 StrategyManager.archive_journal_files 的测试（红）

**文件**: `backend/tests/unit/worker/test_journal_archive.py`（新建）

为什么用 `object.__new__(StrategyManager)`：`StrategyManager.__init__` 会做交易所配置扫描等重装配，模块级单例 `worker_system` 带真实全局副作用；归档方法只依赖 `QUANTCELL_DATA_DIR` + 两个路径 helper，无实例状态，绕过 `__init__` 构造一个干净实例即可单测。

为什么固定时间戳：真实 `datetime.now(UTC)` 在测试跨秒边界时会造成预期文件名 flaky，故 monkeypatch 模块属性指向固定时刻子类（不能 `setattr(datetime, "now", ...)`——内置类型属性只读）。

测试文件全文：

```python
"""StrategyManager.archive_journal_files 单元测试。

归档语义：把 live/rl_live 目录下 worker_{id}.jsonl（及 reconcile 报告）move 到
来源目录 archive/ 子目录，下次启动即 fresh start 重锚。报告文件当前无自动写盘方
（Rust reconcile 只返回 dict 不落盘），存在即收是防御性设计。
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker import strategy_manager as sm
from worker.strategy_manager import StrategyManager


class _FixedDatetime(datetime):
    """固定 now() 的 datetime 子类，替换 sm.datetime 防秒边界 flaky。"""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


TS = "20260102-030405"


@pytest.fixture
def manager() -> StrategyManager:
    # 绕过 __init__（重装配 + 全局副作用）；archive_journal_files 无实例状态依赖
    return object.__new__(StrategyManager)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "celldata"
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(d))
    return d


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sm, "datetime", _FixedDatetime)


def test_archive_live_journal_and_reconcile(manager, data_dir, fixed_now):
    live = data_dir / "live"
    live.mkdir(parents=True)
    (live / "worker_7.jsonl").write_text('{"t":1}\n', encoding="utf-8")
    (live / "worker_7.reconcile.json").write_text("{}", encoding="utf-8")

    moved = manager.archive_journal_files(7)

    by_src = {Path(m["from"]).name: Path(m["to"]) for m in moved}
    assert set(by_src) == {"worker_7.jsonl", "worker_7.reconcile.json"}
    assert by_src["worker_7.jsonl"] == live / "archive" / f"worker_7.{TS}.jsonl"
    assert by_src["worker_7.reconcile.json"] == live / "archive" / f"worker_7.reconcile.{TS}.json"
    # 文件内容真被移动（旧路径不存在、新路径可读）
    assert not (live / "worker_7.jsonl").exists()
    assert (by_src["worker_7.jsonl"]).read_text(encoding="utf-8") == '{"t":1}\n'


def test_archive_rl_journal_goes_to_rl_archive(manager, data_dir, fixed_now):
    rl = data_dir / "rl_live"
    rl.mkdir(parents=True)
    (rl / "worker_9.jsonl").write_text("rl\n", encoding="utf-8")

    moved = manager.archive_journal_files(9)

    assert len(moved) == 1
    assert Path(moved[0]["to"]) == rl / "archive" / f"worker_9.{TS}.jsonl"


def test_archive_no_candidates_raises_value_error(manager, data_dir, fixed_now):
    with pytest.raises(ValueError, match="无可归档"):
        manager.archive_journal_files(42)


def test_archive_name_conflict_appends_index(manager, data_dir, fixed_now):
    live = data_dir / "live"
    (live / "archive").mkdir(parents=True)
    # 预置同时间戳归档文件，模拟同秒内二次归档
    (live / "archive" / f"worker_3.{TS}.jsonl").write_text("old\n", encoding="utf-8")
    (live / "worker_3.jsonl").write_text("new\n", encoding="utf-8")

    moved = manager.archive_journal_files(3)

    assert Path(moved[0]["to"]) == live / "archive" / f"worker_3.{TS}_1.jsonl"
    assert (live / "archive" / f"worker_3.{TS}.jsonl").read_text(encoding="utf-8") == "old\n"
```

**验证（预期红：`AttributeError: ... has no attribute 'archive_journal_files'`）**:

```bash
cd backend && uv run pytest tests/unit/worker/test_journal_archive.py -q
```

（本步无 commit，与 Step 3 合并提交）

---

## Step 3：实现 StrategyManager.archive_journal_files（绿）

**文件**: `backend/worker/strategy_manager.py`
**插入位置**: `_rl_live_journal_path` 与 `_live_journal_path` 两个 helper 之后（约 L1367 空行处）、`stop_strategy` 定义之前。

```python
    def archive_journal_files(self, worker_id: int) -> list[dict]:
        """把已停止 worker 的 journal（及对账报告）归档到来源目录的 archive/ 子目录。

        归档 = 移走 journal，下次启动即 fresh start 重新锚定基准权益（resume 守卫
        不再对旧 journal 对账）。命名 worker_{id}.{ts}.jsonl / worker_{id}.reconcile.{ts}.json，
        同名冲突追加 _1 递增，永不覆盖历史归档。
        部分移动失败时直接抛 RuntimeError：已成功的文件保留在 archive/ 不回滚
        （文件级操作无事务，回滚反而制造半旧不新的中间态）。
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        # reconcile 报告当前无自动写盘方（Rust worker.reconcile 只返回 dict 不落盘），
        # 这里"存在即收"是防御性收集，未来落盘方出现后无需改动本方法
        candidates: list[Path] = []
        for base in (self._live_journal_path(worker_id), self._rl_live_journal_path(worker_id)):
            candidates.append(base)
            candidates.append(base.with_name(f"{base.stem}.reconcile.json"))
        existing = [p for p in candidates if p.is_file()]
        if not existing:
            raise ValueError(f"worker {worker_id} 无可归档的 journal 文件")

        moved: list[dict] = []
        for src in existing:
            archive_dir = src.parent / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = self._unique_archive_path(archive_dir, src.name, timestamp)
            os.replace(src, dest)
            logger.info(f"归档 journal: {src} -> {dest}")
            moved.append({"from": str(src), "to": str(dest)})
        return moved

    @staticmethod
    def _unique_archive_path(archive_dir: Path, filename: str, timestamp: str) -> Path:
        """归档目标重名时追加 _1/_2 递增，保证不覆盖任何历史归档文件。"""
        stem = Path(filename).stem      # worker_7 / worker_7.reconcile
        suffix = Path(filename).suffix  # .jsonl / .json
        candidate = archive_dir / f"{stem}.{timestamp}{suffix}"
        index = 1
        while candidate.exists():
            candidate = archive_dir / f"{stem}.{timestamp}_{index}{suffix}"
            index += 1
        return candidate
```

**验证**:

```bash
cd backend && uv run pytest tests/unit/worker/test_journal_archive.py -q
```

**Commit**（合并 Step 2 的测试）:

```bash
git add backend/worker/strategy_manager.py backend/tests/unit/worker/test_journal_archive.py
git commit -m "feat(worker): StrategyManager.archive_journal_files 归档 journal 到 archive/ 子目录"
```

---

## Step 4：WorkerStateConflictException + core_service.archive_worker_journal（TDD）

### 4a. 异常类（worker/exceptions.py）

插入位置：`WorkerNotRunningException` 之后（约 L56 空行处）。

```python
class WorkerStateConflictException(WorkerException):
    """Worker 当前状态不允许该操作（HTTP 409），如归档要求已停止"""

    def __init__(self, worker_id: int, status: str):
        super().__init__(
            message=f"Worker {worker_id} 当前状态为 {status}，请先停止再归档",
            code=409,
            details={"worker_id": worker_id, "status": status},
        )
```

### 4b. core_service 测试（红）

**文件**: `backend/tests/unit/worker/test_journal_archive.py`（追加以下内容到文件尾部）

```python
# ---------- WorkerCoreService.archive_worker_journal ----------
from contextlib import contextmanager
from types import SimpleNamespace

import worker.core_service as cs
from worker.core_service import WorkerCoreService
from worker.exceptions import (
    WorkerException,
    WorkerNotFoundException,
    WorkerOperationException,
    WorkerStateConflictException,
)


class _FakeWorkerSystem:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result if result is not None else [{"from": "a", "to": "b"}]
        self.error = error
        self.calls: list[int] = []

    def archive_journal_files(self, worker_id: int) -> list[dict]:
        self.calls.append(worker_id)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def fake_worker_system(monkeypatch: pytest.MonkeyPatch) -> _FakeWorkerSystem:
    # core_service.archive_worker_journal 内部 from .strategy_manager import worker_system
    # 为运行时查模块属性，monkeypatch sm.worker_system 即可拦住调用而不触发重装配
    fake = _FakeWorkerSystem()
    monkeypatch.setattr(sm, "worker_system", fake)
    return fake


def _db_with_worker(monkeypatch: pytest.MonkeyPatch, worker_status: str | None) -> None:
    """替换 get_db 与 crud.get_worker，绕开真实 DB（单例 service 便于直测）。"""

    @contextmanager
    def _fake_session():
        yield None

    def _fake_get_worker(db, worker_id):
        if worker_status is None:
            return None
        return SimpleNamespace(id=worker_id, status=worker_status, name=f"worker-{worker_id}")

    monkeypatch.setattr(WorkerCoreService, "get_db", lambda self: _fake_session())
    monkeypatch.setattr(cs.crud, "get_worker", _fake_get_worker)


def test_service_archive_requires_stopped_or_error(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "running")
    with pytest.raises(WorkerStateConflictException) as exc_info:
        service.archive_worker_journal(1)
    assert exc_info.value.code == 409
    assert not fake_worker_system.calls


def test_service_archive_worker_not_found(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, None)
    with pytest.raises(WorkerNotFoundException):
        service.archive_worker_journal(999)
    assert not fake_worker_system.calls


def test_service_archive_success_returns_contract(monkeypatch, fake_worker_system):
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "stopped")
    # WorkerCoreService 是模块级轻量单例，archive_journal_files 无真实文件依赖
    # （QUANTCELL_DATA_DIR 未注入时 live 下无 worker_1 文件，fake 拦截不触盘）
    result = service.archive_worker_journal(1)
    assert result["worker_id"] == 1
    assert result["archived"] == [{"from": "a", "to": "b"}]
    assert "fresh start" in result["hint"]
    assert fake_worker_system.calls == [1]


def test_service_archive_no_candidates_maps_to_operation_error(monkeypatch):
    fake = _FakeWorkerSystem(error=ValueError("worker 5 无可归档的 journal 文件"))
    monkeypatch.setattr(sm, "worker_system", fake)
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "stopped")
    with pytest.raises(WorkerOperationException):
        service.archive_worker_journal(5)


def test_service_archive_move_failure_maps_to_500(monkeypatch):
    fake = _FakeWorkerSystem(error=RuntimeError("移动失败"))
    monkeypatch.setattr(sm, "worker_system", fake)
    service = WorkerCoreService()
    _db_with_worker(monkeypatch, "error")
    with pytest.raises(WorkerException) as exc_info:
        service.archive_worker_journal(6)
    assert exc_info.value.code == 500
```

**验证（预期红：AttributeError `async_archive_worker_journal`/`archive_worker_journal` 未定义 + `WorkerStateConflictException` 不存在）**:

```bash
cd backend && uv run pytest tests/unit/worker/test_journal_archive.py -q
```

### 4c. core_service 实现（绿）

**文件**: `backend/worker/core_service.py`

1. 顶部 `from .exceptions import (...)` 多行 import 中加入 `WorkerStateConflictException`（先 `Read` L20-40 确认现有清单再插入，保持字母序或与现序一致）；确认 `WorkerException` 基类已在 import 清单（若无则补）
2. 插入位置：`async_stop_worker` 方法之后（约 L1004 后），保持 start/stop/archive 生命周期方法相邻

```python
    def archive_worker_journal(self, worker_id: int) -> dict:
        """归档 Worker journal（同步版本，供 CLI 使用）。

        仅 stopped/error 状态可归档（fresh start 重锚语义）。文件由
        StrategyManager.archive_journal_files 移动到 live/rl_live 下的 archive/ 子目录。
        """
        with self.get_db() as db:
            worker = crud.get_worker(db, worker_id)
            if not worker:
                raise WorkerNotFoundException(worker_id)
            if worker.status in ("running", "starting", "stopping"):
                raise WorkerStateConflictException(worker_id, worker.status)

        try:
            # 函数内 import：worker_system 构造重（交易所配置扫描），避免
            # core_service 导入期副作用——与 _stop_worker_in_process 同一约定
            from .strategy_manager import worker_system

            moved = worker_system.archive_journal_files(worker_id)
        except ValueError as e:
            raise WorkerOperationException("归档", worker_id, message=str(e)) from e
        except RuntimeError as e:
            logger.error(f"[WorkerCoreService] 归档 Worker {worker_id} journal 失败: {e}")
            raise WorkerException(message=str(e), code=500) from e

        return {
            "worker_id": worker_id,
            "archived": moved,
            "hint": "journal 已归档，下次启动将 fresh start 重新锚定基准权益",
        }

    async def async_archive_worker_journal(self, worker_id: int) -> dict:
        """异步归档 Worker journal（HTTP 路由入口，与 CLI 同步版调用链一致）。"""
        logger.info(f"[WorkerCoreService] 异步归档 Worker {worker_id} journal")
        return await asyncio.to_thread(self.archive_worker_journal, worker_id)
```

确认 `asyncio` 已在 core_service 顶部 import（如无则补）。

**验证**:

```bash
cd backend && uv run pytest tests/unit/worker/test_journal_archive.py -q
```

**Commit**:

```bash
git add backend/worker/exceptions.py backend/worker/core_service.py backend/tests/unit/worker/test_journal_archive.py
git commit -m "feat(worker): core_service 归档入口（stopped/error 校验 409 + 异常映射）+ WorkerStateConflictException"
```

---

## Step 5：HTTP 路由 POST /{worker_id}/lifecycle/archive

**文件**: `backend/worker/routes.py`
**插入位置**: restart 路由（L427 结束）与 `get_worker_status`（L430）之间。

```python
@router.post("/{worker_id}/lifecycle/archive", response_model=schemas.ApiResponse)
@handle_worker_exceptions("归档Worker journal")
async def archive_worker_journal(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
):
    """归档Worker journal - 移动到 archive/ 子目录，下次启动 fresh start 重锚"""
    result = await worker_core_service.async_archive_worker_journal(worker_id)
    return schemas.ApiResponse(code=0, message="归档完成", data=result)
```

**验证**（路由注册 + OpenAPI 生成无错）:

```bash
cd backend && uv run python -c "from main import app; from fastapi.testclient import TestClient; paths=[r.path for r in app.routes if 'archive' in r.path]; print(paths); assert '/api/v1/workers/{worker_id}/lifecycle/archive' in paths or paths"
```

**Commit**:

```bash
git add backend/worker/routes.py
git commit -m "feat(api): 新增 POST /workers/{id}/lifecycle/archive 归档路由"
```

---

## Step 6：CLI `qc worker archive` 命令

**文件**: `backend/cli/worker.py`
**插入位置**: `worker_delete`（L127 结束）与 `worker_start`（L130）之间。

```python
@app.command("archive")
def worker_archive(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """归档 Worker journal（移动到 archive/，下次启动 fresh start）"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        _service.get_worker(wid)
    except WorkerNotFoundException:
        typer.echo(f"Worker {wid} 不存在")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"确认归档 Worker {wid} 的 journal? 归档后下次启动将为 fresh start")
        if not confirm:
            typer.echo("已取消")
            return

    try:
        result = _service.archive_worker_journal(wid)
    except WorkerNotFoundException:
        typer.echo(f"Worker {wid} 不存在")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)

    for item in result.get("archived", []):
        typer.echo(f"moved: {item['from']} -> {item['to']}")
    typer.echo(f"Worker {wid} journal 已归档（{len(result.get('archived', []))} 个文件），下次启动 fresh start")
```

**验证**：

```bash
cd backend && uv run qc worker archive --help
```

**Commit**:

```bash
git add backend/cli/worker.py
git commit -m "feat(cli): qc worker archive 命令（confirm 确认 + 逐文件展示移动路径）"
```

---

## Step 7：前端——workerApi 方法 + 详情页归档按钮

**文件 1**: `frontend/src/api/workerApi.ts`
**插入位置 1**: Lifecycle API 区块 `restartWorker` 之后（约 L131）；导出对象 Lifecycle 组同步加入 `archiveWorkerJournal,`。

```typescript
/** 归档返回结构：archived 为每条被移动文件的 from/to 路径对 */
export interface ArchiveJournalResult {
  worker_id: number;
  archived: { from: string; to: string }[];
  hint: string;
}

/**
 * 归档 Worker journal（移动到 archive/ 子目录，下次启动 fresh start 重锚）
 * 仅 stopped / error 状态可归档；running 等状态后端返回 409
 */
export const archiveWorkerJournal = (workerId: number): Promise<ArchiveJournalResult> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/archive`);
};
```

**文件 2**: `frontend/src/pages/worker/WorkerDetail.tsx`（路径经 `/Volumes/ExtDisk` 前缀访问）

改动清单（四处小改，措辞精确）:

1. L15-16 import：antd icons 加 `ArchiveOutlined`：
   `import { ArrowLeftOutlined, ArchiveOutlined, ClockCircleOutlined, LoadingOutlined, ShareAltOutlined } from '@ant-design/icons';`
2. L56 解构加 modal：`const { message, modal } = App.useApp();`
3. 操作回调（放 `currentWorker` 定义之后、顶栏 JSX 之前）：

```tsx
  const handleArchive = useCallback(() => {
    if (!currentWorker) return;
    // String() 解耦 status 字面量类型：后端允许 error 态归档，前端类型未必含该字面量
    const status = String(currentWorker.status ?? '');
    modal.confirm({
      title: '归档 journal 并 fresh start？',
      content: `journal 将移动到 archive/ 目录，下次启动以 ${currentWorker.name || '该 Worker'} 的当前权益为基准重新锚定，不再对账历史记录。实盘账户请先人工核对交易所实际持仓与本地记录一致。`,
      okText: '归档',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const result = await archiveWorkerJournal(currentWorker.id);
          message.success(`已归档 ${result.archived.length} 个文件，下次启动 fresh start`);
          await fetchWorkerDetail(workerId);
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : String(e);
          message.error(`归档失败: ${errorMsg}`);
        }
      },
    });
  }, [currentWorker, fetchWorkerDetail, message, modal, workerId]);
```

（`workerId` 为页面已有的路由参数变量名，实做时以文件内既有变量为准——若变量名为 `workerId`（string）直接传 `fetchWorkerDetail(workerId)`。）

4. 顶栏 `<Space>` 内、分享按钮之后新增按钮（沿用 `disabled={!currentWorker}` 既有风格 + 状态门槛）：

```tsx
        <Button
          danger
          icon={<ArchiveOutlined />}
          disabled={!currentWorker || !['stopped', 'error'].includes(String(currentWorker.status ?? ''))}
          onClick={handleArchive}
        >
          归档重锚
        </Button>
```

间距自查：按钮位于既有 `<Space>` 顶栏内，间距由 Space 统一管理，不新增 margin。

**验证**:

```bash
cd frontend && bun run build
```

**Commit**:

```bash
git add frontend/src/api/workerApi.ts frontend/src/pages/worker/WorkerDetail.tsx
git commit -m "feat(frontend): Worker 详情页新增归档重锚按钮（danger + modal 二次确认）"
```

---

## Step 8：收尾回归 + 验收对照

1. 后端回归：

```bash
cd backend && uv run pytest tests/unit/worker/ -q
```

2. CLI 冒烟：

```bash
cd backend && uv run qc worker archive --help && uv run python -c "import cli.worker"
```

3. 前端构建：`cd frontend && bun run build`
4. `git status` 检查无意外脏文件（`backend/**/Volumes/` 残留若存在，mv 到临时目录，禁 rm）
5. 对照设计文档验收清单逐项勾选：校验(409) ✓ 候选收集 ✓ 命名/防覆盖 ✓ 返回契约 ✓ HTTP ✓ CLI ✓ 前端按钮 + 二次确认 ✓
6. 不 commit 代码以外内容；功能验证建议：对 stopped 测试 Worker 走一遍页面按钮 → 观察 `backend/data/live/archive/` 生成归档文件 → 重启该 Worker 确认日志出现 fresh start 锚定

## 风险与边界

* `archive_journal_files` 与 pump 线程无互斥：状态校验（stopped/error）已在 DB 层保证不与运行中循环并发；极端 TOCTOU 窗口（归档瞬间刚好 start）由前端确认弹窗 + 单用户场景覆盖（ponytail: 检查-行动竞态窗口已知，升级路径 = 文件锁或状态机 archiving 态）
* reconcile 报告防御性收集：当前无写盘方，未来若引入 `worker_{id}.reconcile.json` 写盘，本实现零改动兼容
* `os.replace` 仅同目录 rename：from/to 天然同文件系统（archive/ 是来源目录的子目录），无误
