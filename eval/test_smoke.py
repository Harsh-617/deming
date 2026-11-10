"""Smoke test: the SDK imports and supports structured JSON output config. No network."""


def test_google_genai_imports_and_supports_structured_output():
    from google import genai
    from google.genai import types

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema={"type": "OBJECT", "properties": {"lane": {"type": "STRING"}}},
    )
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is not None
    assert hasattr(genai, "Client")
