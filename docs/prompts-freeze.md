# Prompt freeze: prompts-v1

- Date: 2026-11-11
- Tag: `prompts-v1` (the commit that adds this file; the frozen files are unchanged from `7d59532`)
- Model: `gemini-3.5-flash-lite` (`sim/config.py` `GEMINI_MODEL`), temperature 0, google-genai 2.4.0
- Confidence threshold: 0.80 (`sim/config.py`)
- Evaluation `as_of_date`: 2026-11-12 (`data/ground_truth_meta.json`)
- Tests at freeze: 396 passed (`python -m pytest -q`)

Prompts, schemas, guards and data were frozen here **before** the full evaluation run on
`data/inventory.csv`. None of them was edited between this tag and the run being analysed in
`docs/results-analysis.md`. Any later change becomes `prompts-v2`; its results are labelled
"tuned after seeing the test results" and reported with before/after numbers.

Hashes are sha256 of the file bytes **as committed** (`git show prompts-v1:<path> | sha256sum`),
so they don't depend on a CRLF checkout.

## Prompts and schemas

| File | sha256 |
|---|---|
| `agents/checker.md` | `b9eca2ea88ab6e9c4339004ca9cb86c15bb8868fc97709afda45f3d06371d1fc` |
| `agents/main_agent.md` | `ccffe37463171a171cc6f7817cd8b1fbfda0c7257f8e2f52e0c0c09d0330587b` |
| `agents/normalizer.md` | `2be2e33672a376e3d2a5462aafc4e8fb8f5c3b30a4d8277dbb1063b053e99668` |
| `agents/planner.md` | `9b60374848b61397e9b24524e6f27dd5406c862636634c278ddc9cb64435dbbf` |
| `agents/verifier.md` | `eeaaef1653b1520a5db2a53aef5ede792d34c7e802cd603ca90cc42b0c49584b` |
| `schemas/checker.json` | `508d54fa6316279f64965edc0dccb68c202260672cdb059b1e55920e90e0e369` |
| `schemas/normalizer.json` | `68d9aa645eb510cb4666938c84946f93dc5bb75b8b7829ad3f7d58af7a536049` |
| `schemas/planner.json` | `ddac64fd37088f3c0c0543f332a860905d09df336437e80dafa0f34002261950` |
| `schemas/verifier.json` | `6656ccf7358770b1cb43a4fd2c7ea3dbcad640e8a1f29b3dbd8a8f28d4b655e3` |

## Also frozen (guards, retrieval, data)

| File | sha256 |
|---|---|
| `sim/guards.py` | `50fc2343304a9cb1a294eac0d91ce87f40de2edf17dd105ddfd43cd6cda92594` |
| `sim/retrieval.py` | `8064b82ba35a424938bbb283213ff560a130f92425e6f3c998d54d53fe772c64` |
| `sim/pipeline.py` | `c5b4314db83b8baffd523c90a7d73d85645b8e812c9e5ac14ba27f4cd439ed16` |
| `sim/config.py` | `33648d899991216b820ea34b05a647abd2efe9d89f45560a1647f6c3eafe6b91` |
| `sim/models.py` | `3cee3ecf1d11400ce8397593893aab2b1b3256fd5fd2f24b14e6c1437341f014` |
| `data/inventory.csv` | `b3f5d3ab45ac6f11b08a910ce44eebf67346154fb2847858e8836ea8dec4d670` |
| `data/ground_truth.csv` | `ce4e6410fcb12da7a253bc7f46b47f55fe532468cf35a85a537e8ccc631d7130` |
| `data/ground_truth_meta.json` | `1509442f10ddac333275ada1d81799164cd41d21a84d90be3f50b9d2e3830db9` |
| `data/lifecycle.csv` | `dce3df656ba8e6e82c8ab3e2caaeff64727209425c6428107a67a467f0bf7414` |
| `data/feeds/kev.json` | `4372c54ba169d113742974d9e0c68b3523d8e4374c9b2bdcf28712b68565d5cf` (KEV catalogVersion 2026.11.09, 1773 entries) |

## Ground truth status at freeze

All 60 rows are still a draft: none has both `verified_by_a` and `verified_by_b`. Results are
therefore reported as "unverified" throughout.
