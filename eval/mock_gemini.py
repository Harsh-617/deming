"""A stand-in for google.genai.Client used by tests. Makes no network calls."""
from __future__ import annotations

import json
from types import SimpleNamespace


class FakeModels:
    def __init__(self, responder):
        # responder(agent_name, payload_dict, call_index) -> dict | str | Exception
        self.responder = responder
        self.calls = []

    def generate_content(self, *, model, contents, config):
        agent = _agent_from_prompt(config.system_instruction)
        payload = json.loads(contents.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config,
                                          agent=agent, payload=payload))
        out = self.responder(agent, payload, len(self.calls) - 1)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(text=out if isinstance(out, str) else json.dumps(out))


class FakeClient:
    def __init__(self, responder):
        self.models = FakeModels(responder)


def _agent_from_prompt(prompt: str) -> str:
    first = prompt.splitlines()[0].lower()
    for name in ("normalizer", "checker", "planner", "verifier"):
        if name in first:
            return name
    raise AssertionError(f"unrecognised prompt header: {first!r}")
