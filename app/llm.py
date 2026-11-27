"""LLM 호출을 한곳에 모은 모듈. .env의 LLM_PROVIDER로 OpenAI / Anthropic(Claude)을 고른다.

.env 예시 (OpenAI)
  LLM_PROVIDER=openai
  OPENAI_API_KEY=...
  LLM_MODEL=<OpenAI 콘솔에 표시된 모델 ID>
  LLM_REASONING_EFFORT=        # 추론 모델이면 low/medium/high, 아니면 비워 둠

.env 예시 (Claude)
  LLM_PROVIDER=anthropic
  ANTHROPIC_API_KEY=...
  LLM_MODEL=claude-opus-5-5
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
MODEL = os.getenv("LLM_MODEL", "").strip()
REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()  # OpenAI 추론 모델 전용(선택)
MAX_OUTPUT_TOKENS = 16000

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """kind: config | auth | rate | connection | refusal | error"""

    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


_client = None


def describe() -> str:
    return f"{PROVIDER}/{MODEL or '(모델 미설정)'}"


def _model() -> str:
    if MODEL:
        return MODEL
    if PROVIDER == "anthropic":
        return "claude-opus-5-5"
    raise LLMError(".env의 LLM_MODEL에 사용할 모델 ID를 입력하세요.", "config")


def _get_client():
    global _client
    if _client is not None:
        return _client
    if PROVIDER == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError(".env에 OPENAI_API_KEY를 입력하세요.", "auth")
        from openai import OpenAI
        _client = OpenAI()
    elif PROVIDER == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMError(".env에 ANTHROPIC_API_KEY를 입력하세요.", "auth")
        import anthropic
        _client = anthropic.Anthropic()
    else:
        raise LLMError(f"지원하지 않는 LLM_PROVIDER: {PROVIDER} (openai 또는 anthropic)", "config")
    return _client


def _translate(e: Exception) -> LLMError:
    """두 SDK의 예외를 같은 형태로 바꾼다 (두 SDK 모두 같은 예외 이름을 씀)."""
    names = {cls.__name__ for cls in type(e).__mro__}
    if names & {"AuthenticationError", "PermissionDeniedError"}:
        return LLMError("API 키가 올바르지 않거나 권한이 없습니다. .env 설정을 확인하세요.", "auth")
    if "RateLimitError" in names:
        return LLMError("요청이 많거나 사용 한도를 넘었습니다. 잠시 후 다시 시도하세요.", "rate")
    if "APIConnectionError" in names:
        return LLMError("LLM 서버에 연결하지 못했습니다. 네트워크를 확인하세요.", "connection")
    if "NotFoundError" in names:
        return LLMError(f"모델을 찾을 수 없습니다: {MODEL}. .env의 LLM_MODEL을 확인하세요.", "config")
    if "APIError" in names or "APIStatusError" in names:
        return LLMError(f"LLM 호출 중 오류가 발생했습니다: {e}", "error")
    return LLMError(f"알 수 없는 오류: {e}", "error")


def _openai_extra() -> dict:
    return {"reasoning_effort": REASONING_EFFORT} if REASONING_EFFORT else {}


# ---------------------------------------------------------------------------
def generate_json(system: str, user: str, schema: type[T], effort: str | None = None) -> T:
    """구조화된 JSON 응답을 받아 pydantic 모델로 검증해서 돌려준다."""
    client = _get_client()
    model = _model()
    try:
        if PROVIDER == "openai":
            schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"{system}\n\n반드시 다음 JSON 스키마에 맞는 JSON 객체 하나만 출력하세요.\n{schema_hint}"},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                **_openai_extra(),
            )
            choice = resp.choices[0]
            if choice.finish_reason == "length":
                raise LLMError("응답이 너무 길어 잘렸습니다.", "error")
            if not choice.message.content:
                raise LLMError("모델이 응답을 거부했습니다.", "refusal")
            return schema.model_validate_json(choice.message.content)

        # anthropic
        kwargs = {"output_config": {"effort": effort}} if effort else {}
        resp = client.messages.parse(
            model=model, max_tokens=MAX_OUTPUT_TOKENS, system=system,
            messages=[{"role": "user", "content": user}], output_format=schema, **kwargs,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise LLMError("모델이 응답을 거부했습니다.", "refusal")
        return resp.parsed_output
    except (LLMError, ValidationError):
        raise
    except Exception as e:
        raise _translate(e) from e


def stream_text(system: str, messages: list[dict], effort: str | None = None) -> Iterator[str]:
    """답변을 조각(text delta) 단위로 내보낸다. messages: [{"role": "user"|"assistant", "content": str}]"""
    client = _get_client()
    model = _model()
    try:
        if PROVIDER == "openai":
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}] + messages,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                stream=True,
                **_openai_extra(),
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            return

        # anthropic
        kwargs = {"output_config": {"effort": effort}} if effort else {}
        with client.messages.stream(
            model=model, max_tokens=MAX_OUTPUT_TOKENS, system=system, messages=messages, **kwargs,
        ) as stream:
            yield from stream.text_stream
            if stream.get_final_message().stop_reason == "refusal":
                yield "\n\n(이 질문에는 답변할 수 없습니다. 질문을 바꿔 다시 시도해 주세요.)"
    except LLMError:
        raise
    except Exception as e:
        raise _translate(e) from e
