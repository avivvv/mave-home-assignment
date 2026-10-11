import json
from types import SimpleNamespace

import httpx2
import pytest
from openai import RateLimitError
from openai.types.chat import ChatCompletion

from agent import llm as llm_module
from agent.llm import LLM, LLMError, load_config

CONFIG = {"base_url": "http://test", "requests_per_minute": 30, "max_retries": 0, "timeout_seconds": 5, "models": {"main": "fake-model", "judge": None}}
MESSAGES = [{"role": "user", "content": "hello"}]
TOOL = {"type": "function", "function": {"name": "get_node_status", "description": "The status of one node", "parameters": {"type": "object", "properties": {"node": {"type": "string"}}, "required": ["node"]}}}


def completion(content=None, tool_calls=None, tokens=(11, 7)):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": arguments}} for i, (name, arguments) in enumerate(tool_calls)
        ]
    return ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "fake-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1], "total_tokens": sum(tokens)},
    })


class FakeClient:
    """Stands in for the OpenAI client: records each request and answers with the next scripted completion."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeTime:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def make(tmp_path, *answers, config=CONFIG):
    client, fake_time = FakeClient(*answers), FakeTime()
    return LLM(config=config, client=client, cache_dir=tmp_path, clock=fake_time.clock, sleep=fake_time.sleep), client, fake_time


class TestChat:
    def test_returns_the_message_tokens_and_model(self, tmp_path):
        llm, client, _ = make(tmp_path, completion("hi there"))
        reply = llm.chat("main", MESSAGES)
        assert reply.message == {"role": "assistant", "content": "hi there"}
        assert (reply.tokens_in, reply.tokens_out, reply.cached, reply.model) == (11, 7, False, "fake-model")
        assert client.requests == [{"model": "fake-model", "messages": MESSAGES, "temperature": 0}]

    def test_a_tool_call_is_kept_in_the_message(self, tmp_path):
        llm, client, _ = make(tmp_path, completion(tool_calls=[("get_node_status", '{"node": "node-12"}')]))
        reply = llm.chat("main", MESSAGES, tools=[TOOL], tool_choice="auto")
        assert reply.message["content"] is None
        assert reply.message["tool_calls"][0]["function"] == {"name": "get_node_status", "arguments": '{"node": "node-12"}'}
        assert client.requests[0]["tools"] == [TOOL] and client.requests[0]["tool_choice"] == "auto"

    def test_a_role_with_no_model_is_an_error(self, tmp_path):
        llm, client, _ = make(tmp_path)
        with pytest.raises(LLMError, match="no model is set for the role 'judge'"):
            llm.chat("judge", MESSAGES)
        with pytest.raises(LLMError, match="no model is set for the role 'poet'"):
            llm.chat("poet", MESSAGES)
        assert client.requests == []

    def test_a_failed_call_is_one_clear_error_and_is_not_cached(self, tmp_path):
        response = httpx2.Response(429, request=httpx2.Request("POST", "http://test"))
        llm, client, _ = make(tmp_path, RateLimitError("slow down", response=response, body=None), completion("ok"))
        with pytest.raises(LLMError, match="the call to fake-model failed"):
            llm.chat("main", MESSAGES)
        assert llm.chat("main", MESSAGES).message["content"] == "ok"

    def test_a_missing_key_is_a_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(llm_module, "load_dotenv", lambda path: None)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(LLMError, match="NVIDIA_API_KEY is not set"):
            LLM(config=CONFIG, cache_dir=tmp_path).chat("main", MESSAGES)


class TestCache:
    def test_the_same_request_is_answered_from_the_cache_with_no_call(self, tmp_path):
        llm, client, _ = make(tmp_path, completion("first"))
        first = llm.chat("main", MESSAGES)
        second = llm.chat("main", MESSAGES)
        assert len(client.requests) == 1
        assert second.cached and second.message == first.message
        assert (second.tokens_in, second.tokens_out, second.latency_ms) == (first.tokens_in, first.tokens_out, first.latency_ms)

    def test_the_cache_is_on_disk_so_a_new_process_reads_it_and_needs_no_client(self, tmp_path):
        make(tmp_path, completion("first"))[0].chat("main", MESSAGES)
        again = LLM(config=CONFIG, client=None, cache_dir=tmp_path).chat("main", MESSAGES)
        assert again.cached and again.message["content"] == "first"

    def test_a_cache_file_holds_the_request_and_the_reply(self, tmp_path):
        make(tmp_path, completion("first"))[0].chat("main", MESSAGES, cache_tag="rep1")
        stored = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
        assert stored["request"] == {"model": "fake-model", "messages": MESSAGES, "temperature": 0, "cache_tag": "rep1"}
        assert stored["reply"]["message"]["content"] == "first"

    @pytest.mark.parametrize("change", [
        {"messages": [{"role": "user", "content": "goodbye"}]},
        {"tools": [TOOL]},
        {"tools": [TOOL], "tool_choice": "required"},
        {"temperature": 0.7},
        {"cache_tag": "rep2"},
    ])
    def test_any_change_to_the_request_is_a_new_call(self, tmp_path, change):
        llm, client, _ = make(tmp_path, completion("first"), completion("second"))
        llm.chat("main", MESSAGES)
        reply = llm.chat("main", **{"messages": MESSAGES, **change})
        assert len(client.requests) == 2 and not reply.cached

    def test_another_model_for_the_role_is_a_new_call(self, tmp_path):
        make(tmp_path, completion("first"))[0].chat("main", MESSAGES)
        other = {**CONFIG, "models": {"main": "other-model"}}
        llm, client, _ = make(tmp_path, completion("second"), config=other)
        assert llm.chat("main", MESSAGES).message["content"] == "second"


class TestPacing:
    def test_calls_that_reach_the_network_are_spaced(self, tmp_path):
        llm, _, fake_time = make(tmp_path, completion("a"), completion("b"))
        llm.chat("main", MESSAGES, cache_tag="1")
        llm.chat("main", MESSAGES, cache_tag="2")
        # 30 requests a minute is one every 2 seconds
        assert fake_time.slept == [2.0]

    def test_no_wait_when_enough_time_has_passed_or_the_cache_answers(self, tmp_path):
        llm, _, fake_time = make(tmp_path, completion("a"), completion("b"))
        llm.chat("main", MESSAGES, cache_tag="1")
        llm.chat("main", MESSAGES, cache_tag="1")
        fake_time.now += 5
        llm.chat("main", MESSAGES, cache_tag="2")
        assert fake_time.slept == []


def test_the_config_file_has_what_the_client_needs():
    config = load_config()
    assert config["base_url"].startswith("https://") and config["requests_per_minute"] > 0
    assert set(config["models"]) == {"small", "main", "judge"}
    assert config["candidates"]
