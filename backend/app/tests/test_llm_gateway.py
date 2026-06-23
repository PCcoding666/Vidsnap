"""LLM 网关 token 统计测试：记账、作用域隔离、字段容错。"""
import asyncio

import pytest

from app.services import llm_gateway_service as gw_module
from app.services.llm_gateway_service import LLMGateway


class _FakeUsage(dict):
    """模拟 dashscope 的 DictMixin usage（支持 .get）。"""


class _FakeResp:
    def __init__(self, usage):
        self.status_code = 200
        self.usage = usage


def _patch_sdk(monkeypatch, gateway, usage_by_call):
    """让网关的 Generation.call / MultiModalConversation.call 返回预设 usage。"""
    calls = {"n": 0}

    def fake_call(**kwargs):
        usage = usage_by_call[calls["n"]]
        calls["n"] += 1
        return _FakeResp(usage)

    monkeypatch.setattr(gw_module.Generation, "call", staticmethod(fake_call))
    monkeypatch.setattr(gw_module.MultiModalConversation, "call", staticmethod(fake_call))


@pytest.mark.asyncio
async def test_generation_records_tokens(monkeypatch):
    gateway = LLMGateway()
    _patch_sdk(monkeypatch, gateway, [_FakeUsage(input_tokens=100, output_tokens=20)])

    await gateway.call_generation(model="qwen3.7-max", prompt="hi")

    g = gateway.global_stats()
    assert g.input_tokens == 100
    assert g.output_tokens == 20
    assert g.total_tokens == 120
    assert g.calls == 1
    assert g.by_model["qwen3.7-max"].total_tokens == 120


@pytest.mark.asyncio
async def test_multimodal_image_tokens_not_double_counted(monkeypatch):
    """qwen-vl 的 image_tokens 是 input_tokens 的子项（明细），不重复计入总数。"""
    gateway = LLMGateway()
    _patch_sdk(
        monkeypatch, gateway,
        # 真实 qwen-vl：input_tokens 已含图像，image_tokens 只是其中图像部分的明细
        [_FakeUsage(input_tokens=2248, output_tokens=1604, image_tokens=2042)],
    )

    await gateway.call_multimodal(model="qwen3.7-plus", messages=[])

    g = gateway.global_stats()
    assert g.image_tokens == 2042              # 图像明细单独保留
    assert g.total_tokens == 2248 + 1604       # 总数=input+output，image 不重复加
    assert g.by_model["qwen3.7-plus"].total_tokens == 2248 + 1604


@pytest.mark.asyncio
async def test_scope_isolated_from_global_and_each_other(monkeypatch):
    gateway = LLMGateway()
    _patch_sdk(
        monkeypatch, gateway,
        [
            _FakeUsage(input_tokens=10, output_tokens=1),   # scope A
            _FakeUsage(input_tokens=20, output_tokens=2),   # scope B
            _FakeUsage(input_tokens=40, output_tokens=4),   # no scope
        ],
    )

    with gateway.scope("jobA") as a:
        await gateway.call_generation(model="m", prompt="a")
    with gateway.scope("jobB") as b:
        await gateway.call_generation(model="m", prompt="b")
    await gateway.call_generation(model="m", prompt="c")  # 作用域外

    assert a.total_tokens == 11
    assert b.total_tokens == 22
    assert a.label == "jobA" and b.label == "jobB"
    # 全局累加了全部三次
    assert gateway.global_stats().total_tokens == 11 + 22 + 44
    assert gateway.global_stats().calls == 3


@pytest.mark.asyncio
async def test_concurrent_scopes_do_not_cross_contaminate(monkeypatch):
    """并发 job 各自的 scope 通过 contextvars 隔离，不串账。"""
    gateway = LLMGateway()

    async def fake_call(**kwargs):
        await asyncio.sleep(0.01)
        return _FakeResp(_FakeUsage(input_tokens=kwargs["max_tokens"], output_tokens=0))

    # 直接替换异步入口，模拟真实并发时序
    async def run(label, tok):
        with gateway.scope(label) as s:
            resp = await fake_call(max_tokens=tok)
            gateway._record("m", resp, "generation")
            await asyncio.sleep(0.01)  # 让出，验证 contextvar 不被别的协程覆盖
            return s.total_tokens

    a, b = await asyncio.gather(run("A", 100), run("B", 7))
    assert a == 100
    assert b == 7


@pytest.mark.asyncio
async def test_missing_usage_does_not_crash(monkeypatch):
    gateway = LLMGateway()

    def fake_call(**kwargs):
        resp = _FakeResp(None)
        return resp

    monkeypatch.setattr(gw_module.Generation, "call", staticmethod(fake_call))
    await gateway.call_generation(model="m", prompt="x")
    assert gateway.global_stats().calls == 0  # 无 usage 不记账，也不报错
