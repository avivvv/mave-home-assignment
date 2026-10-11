"""The single entry point for every LLM call of the project.

chat() adds three things to the OpenAI client: a cache on disk, spacing between calls, and one clear error.
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "models.yaml"
CACHE_DIR = ROOT / "runs" / "llm_cache"
KEY_NAME = "NVIDIA_API_KEY"


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class Reply:
    # the assistant message as a dict: role, content and, when the model calls tools, tool_calls
    message: dict
    tokens_in: int
    tokens_out: int
    latency_ms: int
    # True when the reply was read from the cache; tokens and latency are then those of the original call
    cached: bool
    model: str


def load_config(path=CONFIG_PATH):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def make_client(config):
    load_dotenv(ROOT / ".env")
    key = os.environ.get(KEY_NAME)
    if not key:
        raise LLMError(f"{KEY_NAME} is not set. Put it in {ROOT / '.env'} as {KEY_NAME}=...")
    return OpenAI(base_url=config["base_url"], api_key=key, max_retries=config["max_retries"], timeout=config["timeout_seconds"])


class LLM:
    def __init__(self, config=None, client=None, cache_dir=CACHE_DIR, clock=time.monotonic, sleep=time.sleep):
        self.config = config or load_config()
        # made on the first call that reaches the network, so a run served from the cache needs no key
        self._client = client
        self.cache_dir = Path(cache_dir)
        self._clock, self._sleep = clock, sleep
        self._last_call = None

    def chat(self, role, messages, tools=None, tool_choice=None, temperature=0, cache_tag="") -> Reply:
        """One chat call with the model of `role`. The same request is answered from the cache.

        `cache_tag` is part of the cache key and nothing else: a new tag gets a fresh answer to the same request.
        """
        model = self.config["models"].get(role)
        if not model:
            raise LLMError(f"no model is set for the role {role!r} in {CONFIG_PATH}")
        request = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            request["tools"] = tools
        if tool_choice:
            request["tool_choice"] = tool_choice
        # extra request fields the config sets for this role, such as turning the model's hidden thinking off
        request.update((self.config.get("options") or {}).get(role) or {})

        key =hashlib.sha256(json.dumps({**request, "cache_tag": cache_tag}, sort_keys=True).encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))["reply"]
            return Reply(**{**stored, "cached": True})

        self._wait_for_turn()
        started = time.perf_counter()
        try:
            if self._client is None:
                self._client = make_client(self.config)
            completion = self._client.chat.completions.create(**request)
        except OpenAIError as error:
            raise LLMError(f"the call to {model} failed: {error}") from error
        latency_ms = round((time.perf_counter() - started) * 1000)

        # keep only what goes back into the conversation; content is None when the model only calls tools
        raw = completion.choices[0].message.model_dump(exclude_none=True)
        message = {"role": "assistant", "content": raw.get("content")}
        if raw.get("tool_calls"):
            message["tool_calls"] = raw["tool_calls"]
        usage = completion.usage
        reply = Reply(message, usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0, latency_ms, False, model)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        stored = {"request": {**request, "cache_tag": cache_tag}, "reply": reply.__dict__}
        path.write_text(json.dumps(stored, indent=1, ensure_ascii=False), encoding="utf-8")
        return reply

    def _wait_for_turn(self):
        # keep at least 60 / requests_per_minute seconds between two calls that reach the network
        gap = 60 / self.config["requests_per_minute"]
        if self._last_call is not None:
            since = self._clock() - self._last_call
            if since < gap:
                self._sleep(gap - since)
        self._last_call = self._clock()
