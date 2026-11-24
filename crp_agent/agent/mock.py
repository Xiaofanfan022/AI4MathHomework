"""离线假模型，用于在不消耗词元的情况下测试长跑流程。

只实现 `chat_json`，返回结构与真实模型一致。它的输出是随机的，
因此**不能**用来评价智能体的质量——它唯一的作用是验证
断点续跑、账本持久化、预算降档、日报生成这些工程件是否工作。
"""

from __future__ import annotations

import random

from .prompts import (SYSTEM_EXPLAIN, SYSTEM_NOVELTY, SYSTEM_PROPOSE,
                      SYSTEM_STRATEGY)

STRATEGIES = ["random", "structured", "local"]


class MockLLM:
    """与 LLMClient 接口兼容的假模型。"""

    def __init__(self, pool: list[str], seed: int = 0, n_forms: int = 6):
        self.pool = list(pool)
        self.rng = random.Random(seed)
        self.n_forms = n_forms
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._strategy_i = 0
        self.cfg = type("Cfg", (), {"model": "mock",
                                    "base_url": "offline"})()

    def chat_json(self, system: str, user: str, **kw) -> dict:
        self.calls += 1
        # 粗略模拟用量，使预算逻辑可被测试
        self.prompt_tokens += max(1, len(user) // 3)
        self.completion_tokens += 120

        if system is SYSTEM_PROPOSE:
            return {"forms": self._forms()}
        if system is SYSTEM_STRATEGY:
            s = STRATEGIES[self._strategy_i % len(STRATEGIES)]
            self._strategy_i += 1
            return {"strategy": s, "budget": 600,
                    "reason": "mock"}
        if system is SYSTEM_EXPLAIN:
            return {"reason": "mock 认为该形式不成立",
                    "lesson": "换一个预测子", "suggested_fix": ""}
        if system is SYSTEM_NOVELTY:
            return {"verdict": "unknown", "matched": "",
                    "comment": "mock"}
        return {}

    def _forms(self) -> list[dict]:
        out = []
        for _ in range(self.n_forms):
            t = self.rng.choice(self.pool)
            k = self.rng.choice([1, 1, 2])
            cand = [p for p in self.pool if p != t]
            preds = self.rng.sample(cand, k)
            signs = [self.rng.choice([1, -1]) for _ in preds]
            out.append({
                "target": t,
                "direction": self.rng.choice(["le", "ge"]),
                "predictors": preds,
                "signs": signs,
                "reason": "mock",
            })
        return out

    @property
    def usage(self) -> dict:
        return {"calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens}
