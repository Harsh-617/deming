# Live fixture run (gemini-3.5-flash-lite, as of 2026-11-12)

Synthetic devices. No claim about real-world accuracy.

- Devices: 60, repeats: 3, settings: sim.loop.SETTINGS_DEFAULTS
- API calls: 495 (cache hits 0, 429/503 retries 132), wall time 3137.2 s
- Schema validation failures: 0; other errors: 22
- Lanes vs fixture truth: [53, 53, 33] correct per repeat

## Lanes

| Device | Truth | Predicted per repeat |
|---|---|---|
| DEV-001 | patch | patch / patch / patch |
| DEV-002 | retire | retire / retire / retire |
| DEV-003 | retire | retire / retire / retire |
| DEV-004 | patch | patch / patch / patch |
| DEV-005 | fine | fine / fine / fine |
| DEV-006 | fine | fine / fine / fine |
| DEV-007 | patch | patch / patch / patch |
| DEV-008 | fine | fine / fine / fine |
| DEV-009 | patch | patch / patch / patch |
| DEV-010 | retire | retire / retire / retire |
| DEV-011 | retire | fine / retire / fine |
| DEV-012 | retire | unknown / unknown / unknown |
| DEV-013 | fine | fine / fine / fine |
| DEV-014 | patch | patch / patch / patch |
| DEV-015 | retire | retire / retire / retire |
| DEV-016 | retire | unknown / unknown / unknown |
| DEV-017 | fine | fine / fine / fine |
| DEV-018 | patch | patch / patch / patch |
| DEV-019 | retire | retire / retire / retire |
| DEV-020 | retire | retire / retire / retire |
| DEV-021 | patch | patch / patch / patch |
| DEV-022 | fine | fine / fine / fine |
| DEV-023 | unknown | unknown / unknown / unknown |
| DEV-024 | patch | patch / patch / patch |
| DEV-025 | patch | patch / patch / patch |
| DEV-026 | fine | fine / fine / fine |
| DEV-027 | patch | unknown / unknown / unknown |
| DEV-028 | fine | unknown / unknown / unknown |
| DEV-029 | fine | fine / fine / fine |
| DEV-030 | unknown | unknown / unknown / unknown |
| DEV-031 | retire | retire / retire / retire |
| DEV-032 | retire | retire / retire / retire |
| DEV-033 | patch | patch / patch / patch |
| DEV-034 | patch | patch / patch / patch |
| DEV-035 | fine | fine / fine / fine |
| DEV-036 | retire | retire / unknown / retire |
| DEV-037 | patch | patch / patch / patch |
| DEV-038 | fine | fine / fine / fine |
| DEV-039 | retire | retire / retire / ERROR |
| DEV-040 | unknown | unknown / unknown / ERROR |
| DEV-041 | retire | retire / retire / ERROR |
| DEV-042 | retire | retire / retire / ERROR |
| DEV-043 | patch | patch / patch / ERROR |
| DEV-044 | retire | retire / retire / ERROR |
| DEV-045 | patch | unknown / unknown / ERROR |
| DEV-046 | fine | fine / fine / ERROR |
| DEV-047 | patch | patch / patch / ERROR |
| DEV-048 | patch | patch / patch / ERROR |
| DEV-049 | patch | patch / patch / ERROR |
| DEV-050 | patch | patch / patch / ERROR |
| DEV-051 | fine | fine / fine / ERROR |
| DEV-052 | fine | unknown / patch / ERROR |
| DEV-053 | unknown | unknown / unknown / ERROR |
| DEV-054 | retire | retire / retire / ERROR |
| DEV-055 | fine | fine / fine / ERROR |
| DEV-056 | patch | patch / patch / ERROR |
| DEV-057 | retire | retire / retire / ERROR |
| DEV-058 | retire | retire / retire / ERROR |
| DEV-059 | retire | retire / retire / ERROR |
| DEV-060 | fine | fine / fine / ERROR |

## Stability across repeats

Structured fields are compared exactly (vendor/product/version case-insensitive, evidence ids as a set); free text is compared exactly too, so any rewording counts.

- **structured**: lane 36/38, vendor 38/38, product 31/38, version 38/38, evidence 31/38, all 26/38
- **planner_structured**: action 36/38, priority 33/38, deadline 35/38, escalate_to_human 38/38, ticket_issue 36/38, ticket_create 37/38, recipient 36/38, all 32/38
- **free_text**: normalizer_reason 0/38, checker_reason 0/38, planner_subject 12/38, planner_body 11/38, planner_reason 0/38, all 0/38

## Latency per agent (live calls only)

- normalizer: 159 calls, mean 2.9 s, max 21.78 s
- checker: 156 calls, mean 4.03 s, max 25.59 s
- planner: 158 calls, mean 4.53 s, max 61.5 s
