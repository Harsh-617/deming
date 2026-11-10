"""Live smoke test for the Gemini API key and candidate models.

Run from the repo root:  python eval/smoke_test.py

- Reads GEMINI_API_KEY from .env (python-dotenv). The key is NEVER printed or logged;
  any error text is redacted before printing.
- Lists available models, then calls each candidate 3 times with structured JSON output
  (response_mime_type + response_schema, temperature 0) and reports parsed JSON,
  latency, errors (HTTP status + text) and whether the 3 outputs were identical.
- No workarounds or retries: a failed call is reported as-is.

All work happens in main(), so pytest collecting this file does not hit the network.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

MODELS = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
RUNS = 3

PROMPT = (
    "Inventory device name: 'Cisco RV320 Dual Gigabit WAN VPN Router, fw 1.4.2.22'. "
    "Extract the vendor, the product and the firmware version."
)
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "vendor": {"type": "STRING"},
        "product": {"type": "STRING"},
        "version": {"type": "STRING"},
    },
    "required": ["vendor", "product", "version"],
}

_KEY_RE = re.compile(r"(?:AIza|AQ\.)[0-9A-Za-z_\-.]{10,}")


def redact(text, key):
    text = str(text)
    if key:
        text = text.replace(key, "[REDACTED]")
    return _KEY_RE.sub("[REDACTED]", text)


def call_once(client, types, model):
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model,
            contents=PROMPT,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SCHEMA,
                temperature=0,
            ),
        )
        latency = time.perf_counter() - t0
        raw = resp.text
        try:
            parsed = json.loads(raw)
        except Exception as e:  # report, don't fix
            return {"ok": False, "latency": latency, "status": None,
                    "error": f"JSON parse failed: {e}; raw={raw!r}"}
        return {"ok": True, "latency": latency, "parsed": parsed, "raw": raw}
    except Exception as e:
        latency = time.perf_counter() - t0
        code = getattr(e, "code", None)
        status = getattr(e, "status", None)
        message = getattr(e, "message", None) or str(e)
        return {"ok": False, "latency": latency, "status": f"{code} {status}".strip(),
                "error": f"{type(e).__name__}: {message}"}


def main():
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY missing or empty in .env. Nothing called.")
        return 1

    from google import genai
    from google.genai import types
    print(f"google-genai version: {genai.__version__}")
    client = genai.Client(api_key=key)

    print("\n== 1. Available models ==")
    try:
        names = sorted(m.name for m in client.models.list())
        print(f"{len(names)} models")
        for n in names:
            print("  " + n)
        for target in MODELS:
            print(f"  -> {target}: {'LISTED' if f'models/{target}' in names else 'NOT LISTED'}")
    except Exception as e:
        print(f"list failed: status={getattr(e, 'code', None)} {getattr(e, 'status', '')} "
              f"error={redact(getattr(e, 'message', None) or e, key)}")

    summary = {}
    for model in MODELS:
        print(f"\n== 2-4. {model}: {RUNS} calls, temperature 0, JSON schema ==")
        results = [call_once(client, types, model) for _ in range(RUNS)]
        for i, r in enumerate(results, 1):
            if r["ok"]:
                print(f"  run {i}: {r['latency']:.2f}s  parsed={json.dumps(r['parsed'], ensure_ascii=False)}")
            else:
                print(f"  run {i}: {r['latency']:.2f}s  ERROR status={r['status']}  "
                      f"text={redact(r['error'], key)}")
        oks = [r for r in results if r["ok"]]
        identical = len(oks) == RUNS and len({r["raw"] for r in oks}) == 1
        lat = [r["latency"] for r in oks]
        print(f"  identical across {RUNS} runs: {identical}"
              + (f"  (successful {len(oks)}/{RUNS})" if len(oks) < RUNS else ""))
        if lat:
            print(f"  latency min/avg/max: {min(lat):.2f}/{sum(lat)/len(lat):.2f}/{max(lat):.2f}s")
        summary[model] = {"ok": f"{len(oks)}/{RUNS}", "identical": identical}

    print("\n== Summary ==")
    for m, s in summary.items():
        print(f"  {m}: ok {s['ok']}, identical={s['identical']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
