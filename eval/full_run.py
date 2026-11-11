"""Full evaluation run: the real Deming pipeline on data/inventory.csv, 3 repeats.

    python eval/full_run.py                 # data/ inventory, truth, KEV, lifecycle; 3 repeats

A thin driver around eval/live_fixture_run.py (same per-device loop, summary and stability
report), with one addition: a stop rule for the daily quota. sim.gemini_runner already retries
429/503 with backoff. If a 429 still comes back:
- its message names a per-day quota -> stop the whole run at once (no workaround);
- otherwise (a per-minute limit) -> wait 65 s and retry the same call, up to 3 times; if it
  still fails and names a quota, stop.
On a stop, the progress log says how many devices and repeats completed; every finished call is
in the response cache, so nothing is lost.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))

import live_fixture_run as lfr  # noqa: E402
from sim.gemini_runner import _status_code  # noqa: E402

DATA = ROOT / "data"
EXTRA_WAITS = 3
WAIT_S = 65


class QuotaExhausted(BaseException):
    """BaseException so live_fixture_run's per-device `except Exception` does not swallow it."""


def _names_daily_quota(msg: str) -> bool:
    m = msg.lower().replace(" ", "")
    return "perday" in m or "requestsperday" in m


class QuotaAwareRunner(lfr.TimedRunner):
    def run(self, agent, payload, repeat_index=0):
        for extra in range(EXTRA_WAITS + 1):
            try:
                return super().run(agent, payload, repeat_index)
            except Exception as exc:  # noqa: BLE001
                if _status_code(exc) != 429:
                    raise
                msg = str(exc)
                if _names_daily_quota(msg):
                    raise QuotaExhausted(f"{agent}: daily quota exhausted (429, per-day quota named)") from None
                if extra == EXTRA_WAITS:
                    if "quota" in msg.lower():
                        raise QuotaExhausted(f"{agent}: 429 quota error persisted after "
                                             f"{EXTRA_WAITS} waits of {WAIT_S}s") from None
                    raise
                print(f"  {agent}: 429 after runner retries; waiting {WAIT_S}s "
                      f"({extra + 1}/{EXTRA_WAITS})", flush=True)
                time.sleep(WAIT_S)


def main() -> int:
    lfr.TimedRunner = QuotaAwareRunner  # live_fixture_run.main builds its runner from this name
    argv = ["--inventory", str(DATA / "inventory.csv"), "--truth", str(DATA / "ground_truth.csv"),
            "--kev", str(DATA / "feeds/kev.json"), "--lifecycle", str(DATA / "lifecycle.csv"),
            "--repeats", "3", *sys.argv[1:]]
    try:
        return lfr.main(argv)
    except QuotaExhausted as exc:
        print(f"STOPPED: {exc}. See the 'rep <n> DEV-xxx' lines above for completed devices.",
              flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
