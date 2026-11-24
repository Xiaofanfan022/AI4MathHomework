"""智能体的运行轨迹记录。

每一步写一行 JSON，包含输入、输出、决策与结果。
轨迹有三个用途：复现、分析、汇报。

字段说明见报告表 4。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Trace:
    """一次运行的轨迹，落盘为一个 JSONL 文件。"""

    def __init__(self, run_dir: Path, round_id: int = 0,
                 name: str = "trace.jsonl"):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / name
        self.round = round_id
        self._seq = 0

    def write(self, stage: str, **fields: Any) -> dict:
        """追加一条记录，返回写入的内容。"""
        self._seq += 1
        rec = {
            "seq": self._seq,
            "round": self.round,
            "stage": stage,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        rec.update(fields)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    def next_round(self) -> int:
        self.round += 1
        return self.round

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]
