# Offline analysis (no API calls)

Synthetic inventory; no real-world accuracy or time-saved claim. All 60 ground-truth rows are unverified. Repeat 2 is excluded from every score.

## all (n=60)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.42 | 1.00 | 1.00 |
| norm_product | 0.18 | 0.47 | 0.52 |
| norm_version | 0.97 | 0.98 | 0.98 |
| norm_all_three | 0.18 | 0.47 | 0.52 |
| lane_accuracy | 0.30 | 0.87 | 0.87 |
| exposure_precision | 0.72 | 1.00 | 1.00 |
| exposure_recall | 0.95 | 0.85 | 0.88 |
| unknown_rate | 0.00 | 0.17 | 0.17 |
| unknown_precision | n/a | 0.40 | 0.40 |
| unknown_recall | 0.00 | 1.00 | 1.00 |

## verified (n=0)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| (no rows) | | | |

## unverified (n=60)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.42 | 1.00 | 1.00 |
| norm_product | 0.18 | 0.47 | 0.52 |
| norm_version | 0.97 | 0.98 | 0.98 |
| norm_all_three | 0.18 | 0.47 | 0.52 |
| lane_accuracy | 0.30 | 0.87 | 0.87 |
| exposure_precision | 0.72 | 1.00 | 1.00 |
| exposure_recall | 0.95 | 0.85 | 0.88 |
| unknown_rate | 0.00 | 0.17 | 0.17 |
| unknown_precision | n/a | 0.40 | 0.40 |
| unknown_recall | 0.00 | 1.00 | 1.00 |

## group:clear_patch (n=15)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.27 | 1.00 | 1.00 |
| norm_product | 0.07 | 0.53 | 0.47 |
| norm_version | 1.00 | 1.00 | 1.00 |
| norm_all_three | 0.07 | 0.53 | 0.47 |
| lane_accuracy | 0.93 | 1.00 | 1.00 |
| exposure_precision | 1.00 | 1.00 | 1.00 |
| exposure_recall | 0.93 | 1.00 | 1.00 |
| unknown_rate | 0.00 | 0.00 | 0.00 |
| unknown_precision | n/a | n/a | n/a |
| unknown_recall | n/a | n/a | n/a |

## group:clear_retire (n=12)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.50 | 1.00 | 1.00 |
| norm_product | 0.17 | 0.25 | 0.33 |
| norm_version | 1.00 | 1.00 | 1.00 |
| norm_all_three | 0.17 | 0.25 | 0.33 |
| lane_accuracy | 0.00 | 0.83 | 0.92 |
| exposure_precision | 1.00 | 1.00 | 1.00 |
| exposure_recall | 1.00 | 0.83 | 0.92 |
| unknown_rate | 0.00 | 0.08 | 0.08 |
| unknown_precision | n/a | 0.00 | 0.00 |
| unknown_recall | n/a | n/a | n/a |

## group:critical_dnt (n=4)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.75 | 1.00 | 1.00 |
| norm_product | 0.50 | 0.25 | 0.25 |
| norm_version | 1.00 | 1.00 | 1.00 |
| norm_all_three | 0.50 | 0.25 | 0.25 |
| lane_accuracy | 0.50 | 1.00 | 1.00 |
| exposure_precision | 1.00 | 1.00 | 1.00 |
| exposure_recall | 1.00 | 1.00 | 1.00 |
| unknown_rate | 0.00 | 0.00 | 0.00 |
| unknown_precision | n/a | n/a | n/a |
| unknown_recall | n/a | n/a | n/a |

## group:messy_name (n=10)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.70 | 1.00 | 1.00 |
| norm_product | 0.20 | 0.30 | 0.40 |
| norm_version | 0.80 | 0.90 | 0.90 |
| norm_all_three | 0.20 | 0.30 | 0.40 |
| lane_accuracy | 0.20 | 0.60 | 0.50 |
| exposure_precision | 1.00 | 1.00 | 1.00 |
| exposure_recall | 0.88 | 0.62 | 0.50 |
| unknown_rate | 0.00 | 0.50 | 0.60 |
| unknown_precision | n/a | 0.40 | 0.33 |
| unknown_recall | 0.00 | 1.00 | 1.00 |

## group:name_collision (n=4)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.25 | 1.00 | 1.00 |
| norm_product | 0.00 | 0.25 | 0.50 |
| norm_version | 1.00 | 1.00 | 1.00 |
| norm_all_three | 0.00 | 0.25 | 0.50 |
| lane_accuracy | 0.00 | 0.75 | 0.75 |
| exposure_precision | 0.50 | 1.00 | 1.00 |
| exposure_recall | 1.00 | 1.00 | 1.00 |
| unknown_rate | 0.00 | 0.75 | 0.75 |
| unknown_precision | n/a | 0.67 | 0.67 |
| unknown_recall | 0.00 | 1.00 | 1.00 |

## group:supported_fine (n=15)

| Metric | baseline | deming_rep0 | deming_rep1 |
|---|---|---|---|
| norm_vendor | 0.27 | 1.00 | 1.00 |
| norm_product | 0.27 | 0.80 | 0.87 |
| norm_version | 1.00 | 1.00 | 1.00 |
| norm_all_three | 0.27 | 0.80 | 0.87 |
| lane_accuracy | 0.00 | 0.93 | 0.93 |
| exposure_precision | 0.07 | n/a | 1.00 |
| exposure_recall | 1.00 | 0.00 | 1.00 |
| unknown_rate | 0.00 | 0.07 | 0.00 |
| unknown_precision | n/a | 0.00 | n/a |
| unknown_recall | n/a | n/a | n/a |

## Stability, complete repeats (0 and 1, n=60)

lane 0.95, vendor 1.00, product 0.80, version 1.00, evidence 0.87, all structured 0.73

Unstable devices: DEV-011 (lane/product/evidence), DEV-014 (evidence), DEV-019 (evidence), DEV-023 (product), DEV-024 (product), DEV-031 (product), DEV-034 (evidence), DEV-036 (lane/product/evidence), DEV-040 (product), DEV-041 (product/evidence), DEV-044 (product), DEV-045 (product), DEV-051 (product), DEV-052 (lane/evidence), DEV-053 (product), DEV-057 (product/evidence)

## Footnote: 3 repeats on DEV-001..DEV-040 (n=40, replayed from cache)

lane 0.95, vendor 1.00, product 0.80, version 1.00, evidence 0.82, all structured 0.68

Replay vs published CSVs (repeats 0-1): 0 mismatches.

## POST-HOC alias view (defined after seeing the results)

| Slice | System | strict product | alias vendor | alias product | alias vendor+product |
|---|---|---|---|---|---|
| all | baseline | 0.18 | 0.42 | 0.30 | 0.30 |
| all | deming_rep0 | 0.47 | 1.00 | 0.90 | 0.90 |
| all | deming_rep1 | 0.52 | 1.00 | 0.95 | 0.95 |
| unverified | baseline | 0.18 | 0.42 | 0.30 | 0.30 |
| unverified | deming_rep0 | 0.47 | 1.00 | 0.90 | 0.90 |
| unverified | deming_rep1 | 0.52 | 1.00 | 0.95 | 0.95 |
| group:clear_patch | baseline | 0.07 | 0.27 | 0.27 | 0.27 |
| group:clear_patch | deming_rep0 | 0.53 | 1.00 | 1.00 | 1.00 |
| group:clear_patch | deming_rep1 | 0.47 | 1.00 | 1.00 | 1.00 |
| group:clear_retire | baseline | 0.17 | 0.50 | 0.25 | 0.25 |
| group:clear_retire | deming_rep0 | 0.25 | 1.00 | 0.92 | 0.92 |
| group:clear_retire | deming_rep1 | 0.33 | 1.00 | 1.00 | 1.00 |
| group:critical_dnt | baseline | 0.50 | 0.75 | 0.75 | 0.75 |
| group:critical_dnt | deming_rep0 | 0.25 | 1.00 | 1.00 | 1.00 |
| group:critical_dnt | deming_rep1 | 0.25 | 1.00 | 1.00 | 1.00 |
| group:messy_name | baseline | 0.20 | 0.70 | 0.40 | 0.40 |
| group:messy_name | deming_rep0 | 0.30 | 1.00 | 0.70 | 0.70 |
| group:messy_name | deming_rep1 | 0.40 | 1.00 | 0.80 | 0.80 |
| group:name_collision | baseline | 0.00 | 0.25 | 0.00 | 0.00 |
| group:name_collision | deming_rep0 | 0.25 | 1.00 | 0.50 | 0.50 |
| group:name_collision | deming_rep1 | 0.50 | 1.00 | 0.75 | 0.75 |
| group:supported_fine | baseline | 0.27 | 0.27 | 0.27 | 0.27 |
| group:supported_fine | deming_rep0 | 0.80 | 1.00 | 1.00 | 1.00 |
| group:supported_fine | deming_rep1 | 0.87 | 1.00 | 1.00 | 1.00 |
