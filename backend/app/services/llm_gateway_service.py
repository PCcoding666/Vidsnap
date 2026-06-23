"""
LLM 网关：所有 DashScope 模型调用的统一中间层，集中统计 token 消耗。

为什么要这层网关：
- 之前 llm_service 直接调用 dashscope 的 Generation.call / MultiModalConversation.call，
  token 消耗散落各处、无法汇总。
- 网关把这两个入口收口，从每次响应的 response.usage 读取 token 数并累加，
  既维护进程级全局累计，也支持基于 contextvars 的作用域累计
  （每个 workspace job 一个 scope，并发互不干扰）。

用法：
    # 统计某个作用域（如单个 job）的消耗
    with llm_gateway.scope(job_id) as usage:
        await llm_service.compose_illustrated_note(...)
    print(usage.to_dict())   # 该作用域内所有 LLM 调用的 token 汇总

    # 进程启动以来的全局累计
    llm_gateway.global_stats().to_dict()
"""
import asyncio
import contextlib
import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

from dashscope import Generation, MultiModalConversation

from ..core.logging import logger


@dataclass
class ModelUsage:
    """单个模型在某作用域内的 token 汇总。"""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    image_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        # image_tokens 是 input_tokens 的子项（明细），不重复计入总数
        return self.input_tokens + self.output_tokens


@dataclass
class UsageStats:
    """一个统计作用域（全局或单个 job）的 token 汇总。"""
    label: str = "global"
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    image_tokens: int = 0
    by_model: Dict[str, ModelUsage] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        # image_tokens 是 input_tokens 的子项（明细），不重复计入总数
        return self.input_tokens + self.output_tokens

    def add(self, model: str, input_tokens: int, output_tokens: int, image_tokens: int = 0) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.image_tokens += image_tokens
        m = self.by_model.setdefault(model, ModelUsage())
        m.calls += 1
        m.input_tokens += input_tokens
        m.output_tokens += output_tokens
        m.image_tokens += image_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "image_tokens": self.image_tokens,
            "total_tokens": self.total_tokens,
            "by_model": {
                name: {
                    "calls": u.calls,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "image_tokens": u.image_tokens,
                    "total_tokens": u.total_tokens,
                }
                for name, u in self.by_model.items()
            },
        }


# 当前作用域：在 scope() 内设置，_record 调用时读取并归账到对应作用域。
# 用 ContextVar 保证并发 job 之间互不串账（每个 asyncio.Task 有独立的上下文）。
_current_scope: contextvars.ContextVar[Optional[UsageStats]] = contextvars.ContextVar(
    "llm_usage_scope", default=None
)


class LLMGateway:
    """DashScope 调用的统一入口 + token 统计中间层。"""

    def __init__(self) -> None:
        self._global = UsageStats(label="global")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # 作用域管理
    # ------------------------------------------------------------------ #
    @contextlib.contextmanager
    def scope(self, label: str) -> Iterator[UsageStats]:
        """开一个统计作用域，块内所有 LLM 调用都归账到返回的 UsageStats。

        作用域之间互相独立；同时也会照常累加进全局统计。
        """
        stats = UsageStats(label=label)
        token = _current_scope.set(stats)
        try:
            yield stats
        finally:
            _current_scope.reset(token)

    # ------------------------------------------------------------------ #
    # 调用入口（包装 dashscope 同步 SDK 到线程池）
    # ------------------------------------------------------------------ #
    async def call_generation(self, **kwargs: Any):
        """纯文本生成（Generation.call），自动统计 token。"""
        response = await asyncio.to_thread(Generation.call, **kwargs)
        self._record(kwargs.get("model"), response, "generation")
        return response

    async def call_multimodal(self, **kwargs: Any):
        """多模态对话（MultiModalConversation.call），自动统计 token。"""
        response = await asyncio.to_thread(MultiModalConversation.call, **kwargs)
        self._record(kwargs.get("model"), response, "multimodal")
        return response

    # ------------------------------------------------------------------ #
    # 统计记账
    # ------------------------------------------------------------------ #
    def _record(self, model: Optional[str], response: Any, api_type: str) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        # usage 是 DictMixin，可像 dict 一样 .get；不同模型字段略有差异，全部容错取值。
        in_tok = self._as_int(usage.get("input_tokens"))
        out_tok = self._as_int(usage.get("output_tokens"))
        # qwen-vl 的 image_tokens 是 input_tokens 中图像部分的明细拆分（已含在 input_tokens 内），
        # 仅作 breakdown 记录，不重复计入总数。
        img_tok = self._as_int(usage.get("image_tokens"))
        model = model or "unknown"
        # 原始 usage 结构因模型而异，DEBUG 级别留痕便于核对字段语义。
        logger.debug(f"[LLM网关] 原始 usage={dict(usage)}")

        with self._lock:
            self._global.add(model, in_tok, out_tok, img_tok)
            global_total = self._global.total_tokens

        scope = _current_scope.get()
        if scope is not None:
            scope.add(model, in_tok, out_tok, img_tok)

        logger.info(
            f"[LLM网关] {api_type} model={model} "
            f"in={in_tok} out={out_tok} img={img_tok} "
            f"call_total={in_tok + out_tok} 全局累计={global_total}"
        )

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------ #
    # 读取 / 重置
    # ------------------------------------------------------------------ #
    def global_stats(self) -> UsageStats:
        return self._global

    def reset(self) -> None:
        """清零全局累计（主要用于测试）。"""
        with self._lock:
            self._global = UsageStats(label="global")


# 单例：全应用共用一个网关
llm_gateway = LLMGateway()
