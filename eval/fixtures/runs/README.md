Fixture runs used by the tests. Hand-made, NOT output from the real Deming agent.

- `deming-20261111T010000Z`: 6/8 identity right, 7/8 lanes right; abstains on DEV-007 (truth patch)
  and writes `v6.5.62` with a v prefix on DEV-006.
- `deming-20261111T020000Z`: identical except DEV-007 is patched correctly, so DEV-007 is unstable.
- `baseline-20261111T000000Z`: real output of `eval/baseline.py` on the fixture, with a fixed run id.
