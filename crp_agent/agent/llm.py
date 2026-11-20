"""大语言模型客户端。

只依赖 openai 官方 SDK，任何兼容 OpenAI 接口的服务都能用
（aihubmix、DeepSeek、通义、智谱等），差别只在 base_url 与模型名。

密钥一律从环境变量读取，不写入代码。
缺少密钥时抛出明确的错误，而不是静默失败。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 从仓库根目录的 .env 读取（本文件位于 <root>/crp_agent/agent/llm.py）
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)


class MissingKeyError(RuntimeError):
    pass


def _require(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v or v.startswith("your_"):
        raise MissingKeyError(
            f"环境变量 {name} 未设置。请在 {_ROOT / '.env'} 中填入真实值，"
            f"可参考 .env.example。"
        )
    return v


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.7
    max_retries: int = 3
    thinking: bool = False
    timeout: float = 900.0

    @classmethod
    def from_env(cls) -> "LLMConfig":
        raw_think = os.getenv("LLM_THINKING", "0").strip().lower()
        return cls(
            api_key=_require("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("MODEL_NAME", "").strip() or "DeepSeek-V4.1-Flash",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            thinking=raw_think in ("1", "true", "yes", "on"),
            timeout=float(os.getenv("LLM_TIMEOUT", "900")),
        )


class LLMClient:
    """带重试与用量统计的薄封装。"""

    def __init__(self, cfg: LLMConfig | None = None):
        from openai import OpenAI

        self.cfg = cfg or LLMConfig.from_env()
        self._client = OpenAI(api_key=self.cfg.api_key,
                              base_url=self.cfg.base_url,
                              timeout=self.cfg.timeout)
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def chat(self, system: str, user: str, *, json_mode: bool = False,
             temperature: float | None = None) -> str:
        last_err: Exception | None = None

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                kwargs = {
                    "model": self.cfg.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": (self.cfg.temperature
                                    if temperature is None else temperature),
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                if not self.cfg.thinking:
                    # 该模型默认会进行长时间内部推理，可能耗尽 token 预算后
                    # 返回空内容。关闭后响应从分钟级降到秒级。
                    kwargs["extra_body"] = {
                        "chat_template_kwargs": {"thinking": False}
                    }

                resp = self._client.chat.completions.create(**kwargs)
                self.calls += 1
                if resp.usage:
                    self.prompt_tokens += resp.usage.prompt_tokens
                    self.completion_tokens += resp.usage.completion_tokens
                return resp.choices[0].message.content or ""
            except Exception as e:                      # noqa: BLE001
                last_err = e
                if attempt < self.cfg.max_retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"模型调用失败（已重试 {self.cfg.max_retries} 次）："
                           f"{last_err}")

    def chat_json(self, system: str, user: str, **kw) -> dict:
        """要求模型返回 JSON，并解析。解析失败时抛错，由上层处理。"""
        raw = self.chat(system, user, json_mode=True, **kw)
        if not raw.strip():
            raise RuntimeError("模型返回空内容（可能思考耗尽 token 预算）")
        try:
            return json.loads(_strip_fence(raw))
        except json.JSONDecodeError:
            obj = _extract_json_object(raw)
            if obj is None:
                raise
            return json.loads(obj)

    @property
    def usage(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


def _strip_fence(s: str) -> str:
    """去掉模型可能加的 ```json 围栏。"""
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        s = "\n".join(lines).strip()
    return s


def _extract_json_object(s: str) -> str | None:
    """从夹杂解释文字的输出中截出最外层的 {...}。"""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None
