"""run_agent_dream_job job 体直调测试（stub agent，不依赖真实 LLM）。"""


class _FakeDream:
    def __init__(self, result: bool):
        self.result = result
        self.calls = 0

    async def run(self) -> bool:
        self.calls += 1
        return self.result


class _FakeAgent:
    def __init__(self, result: bool):
        self.dream = _FakeDream(result)


def test_dream_job_runs_singleton_dream(monkeypatch):
    from agent.core import factory
    from core.scheduler import run_agent_dream_job

    fake = _FakeAgent(True)
    monkeypatch.setattr(factory, "get_agent", lambda: fake)

    assert run_agent_dream_job() is True
    assert fake.dream.calls == 1


def test_dream_job_noop_returns_false(monkeypatch):
    from agent.core import factory
    from core.scheduler import run_agent_dream_job

    fake = _FakeAgent(False)
    monkeypatch.setattr(factory, "get_agent", lambda: fake)

    assert run_agent_dream_job() is False
    assert fake.dream.calls == 1
