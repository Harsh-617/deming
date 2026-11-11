Fixture runs used by the tests. Hand-made, NOT output from the real Deming agent.

- `deming-20261111T010000Z`: 6/8 identity right, 6/8 lanes right against the current fixture truth
  (DEV-001/002/007 relabelled `unknown` on 2026-11-11: KEV match with no fixed_version in the
  fixture lifecycle; the run still says patch on DEV-001/002). Abstains on DEV-007 (right now) and
  writes `v6.5.62` with a v prefix on DEV-006. Predictions were made against the old labels.
- `deming-20261111T020000Z`: identical except DEV-007 is patched correctly, so DEV-007 is unstable.
- `baseline-20261111T000000Z`: real output of `eval/baseline.py` on the fixture, with a fixed run id.
