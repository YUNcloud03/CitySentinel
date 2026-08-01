"""LLM client：provider 自動偵測 + structured output。

**新增一家 provider = 在 PROVIDERS 加一列，流程碼零改動。**
關鍵在於分流依據是 protocol（呼叫協定）而非廠牌——Google、DeepSeek、Groq、
xAI、OpenRouter 等都提供 OpenAI 相容端點，共用同一條 openai 路徑，
差別只在 base_url 與 model。真正需要獨立實作的只有協定不同的（如 anthropic）。

選用順序＝PROVIDERS 的宣告順序，取第一個有金鑰的。可用環境變數調整：
    CITY_LLM_PROVIDER  指定廠牌（如 google），跳過自動偵測
    CITY_LLM_MODEL     覆寫模型
    CITY_LLM_BASE_URL  覆寫端點；搭配 CITY_LLM_API_KEY 可接任何 OpenAI 相容服務
    CITY_LLM_DISABLED  設 1 強制停用（測試用）

呼叫端拿到 None 一律走確定性 fallback——LLM 失敗不可讓事件流程失敗（技術文件 20.3）。

Guardrails 由 schema 驗證（Pydantic）+ 呼叫端的內容驗證共同把關；
本模組只負責「把自然語言變成通過 schema 的結構化物件」。
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime
from typing import NamedTuple, TypeVar

from pydantic import BaseModel

TIMEOUT_S = 15.0

T = TypeVar("T", bound=BaseModel)


class Provider(NamedTuple):
    """一家 LLM 供應商的接法。protocol 決定用哪套 SDK 與訊息格式。"""

    name: str
    protocol: str  # "openai" | "anthropic"
    key_envs: tuple[str, ...]  # 任一有值即視為可用
    model: str
    base_url: str | None = None  # None＝用該 SDK 的預設端點


# 註冊表：順序即優先序。model 為預設值，可由 CITY_LLM_MODEL 覆寫，
# 故廠商更新模型代號時不必動這裡。
PROVIDERS: tuple[Provider, ...] = (
    Provider("anthropic", "anthropic", ("ANTHROPIC_API_KEY",), "claude-opus-4-8"),
    Provider("openai", "openai", ("OPENAI_API_KEY",), "gpt-4o-mini"),
    Provider("google", "openai", ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
             "gemini-2.5-flash",
             "https://generativelanguage.googleapis.com/v1beta/openai/"),
    Provider("deepseek", "openai", ("DEEPSEEK_API_KEY",), "deepseek-chat",
             "https://api.deepseek.com/v1"),
    Provider("groq", "openai", ("GROQ_API_KEY",), "llama-3.3-70b-versatile",
             "https://api.groq.com/openai/v1"),
    Provider("xai", "openai", ("XAI_API_KEY",), "grok-3-mini",
             "https://api.x.ai/v1"),
    Provider("openrouter", "openai", ("OPENROUTER_API_KEY",), "openai/gpt-4o-mini",
             "https://openrouter.ai/api/v1"),
)

_cached: tuple[str | None, object | None] | None = None
_active: Provider | None = None

# LLM 呼叫留痕（稽核用）：目的、provider、延遲、成敗。內容不含原始 prompt 全文
# （避免 log 爆量），但足以回答「哪次生成用了 LLM、花多久、有沒有失敗」。
CALL_LOG: deque[dict] = deque(maxlen=200)


def _resolve() -> Provider | None:
    """依環境變數挑出要用的 provider；都沒設定時回 None。"""
    forced = (os.environ.get("CITY_LLM_PROVIDER") or "").strip().lower()
    for p in PROVIDERS:
        if forced and p.name != forced:
            continue
        if any(os.environ.get(e) for e in p.key_envs):
            return p._replace(
                model=os.environ.get("CITY_LLM_MODEL") or p.model,
                base_url=os.environ.get("CITY_LLM_BASE_URL") or p.base_url,
            )
    # 未登記的服務：給 base_url + 金鑰即可接，不必改程式碼。
    if os.environ.get("CITY_LLM_BASE_URL") and os.environ.get("CITY_LLM_API_KEY"):
        return Provider(forced or "custom", "openai", ("CITY_LLM_API_KEY",),
                        os.environ.get("CITY_LLM_MODEL") or "",
                        os.environ["CITY_LLM_BASE_URL"])
    return None


def _build_client(p: Provider) -> object:
    key = next(os.environ[e] for e in p.key_envs if os.environ.get(e))
    if p.protocol == "anthropic":
        import anthropic

        return anthropic.Anthropic(api_key=key, timeout=TIMEOUT_S, base_url=p.base_url)
    import openai

    # base_url=None 時 SDK 自動使用官方端點
    return openai.OpenAI(api_key=key, timeout=TIMEOUT_S, base_url=p.base_url)


def get_provider() -> tuple[str | None, object | None]:
    """回傳 (provider_name, client)；沒有可用 key 時回 (None, None)。

    設 CITY_LLM_DISABLED=1 可強制停用（測試環境用，確保確定性）。
    """
    global _cached, _active
    if os.environ.get("CITY_LLM_DISABLED"):
        return (None, None)
    if _cached is not None:
        return _cached
    _active = _resolve()
    _cached = (None, None) if _active is None else (_active.name, _build_client(_active))
    return _cached


def active_provider() -> Provider | None:
    """回傳當前 provider 的完整設定（protocol / model / base_url）。"""
    get_provider()
    return None if os.environ.get("CITY_LLM_DISABLED") else _active


def model_for(provider_name: str | None) -> str | None:
    """provider 名稱 → 實際模型 ID（留痕用）。"""
    p = active_provider()
    return p.model if p and p.name == provider_name else None


def reset_provider_cache() -> None:
    """測試用：重置 provider 偵測。"""
    global _cached, _active
    _cached = None
    _active = None


def structured_completion(
    system: str, user: str, schema: type[T], max_tokens: int = 1500,
    purpose: str = "general",
) -> T | None:
    """呼叫 LLM 並以 Pydantic schema 驗證輸出；任何失敗回傳 None（走 fallback）。

    每次呼叫記入 CALL_LOG 供稽核（purpose 標明用途）。
    """
    provider, client = get_provider()
    if provider is None:
        return None
    prov = active_provider()
    started = time.monotonic()

    def _log(ok: bool, note: str = "") -> None:
        CALL_LOG.append({
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "purpose": purpose,
            "provider": provider,
            "model": prov.model,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "ok": ok,
            "note": note,
        })

    try:
        if prov.protocol == "anthropic":
            response = client.messages.parse(
                model=prov.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
            _log(True)
            return response.parsed_output
        # openai 相容：JSON mode + 客戶端 schema 驗證（跨版本、跨廠商相容）。
        # json_object 模式不強制 schema，故把 schema 注入 system prompt 要求遵循。
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        response = client.chat.completions.create(
            model=prov.model,
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
        parsed = schema.model_validate(json.loads(raw))
        _log(True)
        return parsed
    except Exception as exc:  # noqa: BLE001 - LLM 任何失敗都不可拖垮主流程
        _log(False, type(exc).__name__)
        return None
