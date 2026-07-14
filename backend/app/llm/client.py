"""LLM client：provider 自動偵測 + structured output。

優先序：ANTHROPIC_API_KEY（Claude claude-opus-4-8）→ OPENAI_API_KEY → 無（回 None）。
呼叫端拿到 None 一律走確定性 fallback——LLM 失敗不可讓事件流程失敗（技術文件 20.3）。

Guardrails 由 schema 驗證（Pydantic）+ 呼叫端的內容驗證共同把關；
本模組只負責「把自然語言變成通過 schema 的結構化物件」。
"""
from __future__ import annotations

import json
import os
from typing import TypeVar

from pydantic import BaseModel

ANTHROPIC_MODEL = "claude-opus-4-8"
OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 15.0

T = TypeVar("T", bound=BaseModel)

_cached: tuple[str | None, object | None] | None = None


def get_provider() -> tuple[str | None, object | None]:
    """回傳 (provider_name, client)；沒有可用 key 時回 (None, None)。"""
    global _cached
    if _cached is not None:
        return _cached
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        _cached = ("anthropic", anthropic.Anthropic(timeout=TIMEOUT_S))
    elif os.environ.get("OPENAI_API_KEY"):
        import openai

        _cached = ("openai", openai.OpenAI(timeout=TIMEOUT_S))
    else:
        _cached = (None, None)
    return _cached


def reset_provider_cache() -> None:
    """測試用：重置 provider 偵測。"""
    global _cached
    _cached = None


def structured_completion(
    system: str, user: str, schema: type[T], max_tokens: int = 1500
) -> T | None:
    """呼叫 LLM 並以 Pydantic schema 驗證輸出；任何失敗回傳 None（走 fallback）。"""
    provider, client = get_provider()
    if provider is None:
        return None
    try:
        if provider == "anthropic":
            response = client.messages.parse(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
            return response.parsed_output
        # openai：JSON mode + 客戶端 schema 驗證（跨版本相容）。
        # json_object 模式不強制 schema，故把 schema 注入 system prompt 要求遵循。
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    system
                    + "\n輸出必須是單一 JSON 物件，且嚴格符合以下 JSON Schema"
                    + "（欄位型別必須完全一致，例如整數欄位不得輸出字串）：\n"
                    + schema_json
                )},
                {"role": "user", "content": user},
            ],
        )
        raw = response.choices[0].message.content
        return schema.model_validate(json.loads(raw))
    except Exception:  # noqa: BLE001 - LLM 任何失敗都不可拖垮主流程
        return None
