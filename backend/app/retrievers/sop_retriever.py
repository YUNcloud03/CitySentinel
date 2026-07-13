"""SOP 檢索：以程式已觸發的 rule_id 精準取回原文，不靠 embedding 決定適用條款。"""
from __future__ import annotations

from ..data_loader import load_sop_rules


class SOPRetriever:
    def __init__(self, rules: dict[int, dict] | None = None):
        self.rules = rules if rules is not None else load_sop_rules()

    def get(self, rule_id: int) -> dict:
        return self.rules[rule_id]

    def retrieve(self, rule_ids: list[int]) -> list[dict]:
        """依觸發的 rule_id 取回 SOP 原文（去重、保序）。"""
        seen = []
        for rid in rule_ids:
            if rid in self.rules and rid not in seen:
                seen.append(rid)
        return [self.rules[rid] for rid in seen]
