# Classify comparison: effort, test split

- **Label set:** `labelsets/effort.yml` sha256 `5e702a9d8962f2c8bf062f2011530d6aef3de8648896fbfc4f3db77be61c3db3`
- **Labelled set:** `data/effort.jsonl` sha256 `f388d8a2708e8c0827f47e7bf7fb2168dff7a371bf211390d29dcf491d77b516`
- **Items:** 75
- **The cache uses:** `paths`: the model has no complete test-split eval: no recording of sample 1 for item 'pr-17' with this label set and text in recordings/effort/claude-haiku-5-5.jsonl; a --live run records it

| Classifier | Accuracy | Coverage | Pass mark |
|---|---|---|---|
| baseline `majority` | 49.3% | 100.0% | FAIL |
| baseline `paths` | 62.7% | 100.0% | FAIL |
| model | not run | not run | – |

## Baseline: majority

- **Classifier:** baseline `majority`
- **Mode:** baseline (no model calls)
- **Prior:** dev split draft labels (178); no gold dev labels
- **Label set:** `labelsets/effort.yml` sha256 `5e702a9d8962f2c8bf062f2011530d6aef3de8648896fbfc4f3db77be61c3db3`
- **Labelled set:** `data/effort.jsonl` sha256 `f388d8a2708e8c0827f47e7bf7fb2168dff7a371bf211390d29dcf491d77b516`
- **Items:** 75

**Result: FAIL**

### Pass mark

| Check | Value | Bar | |
|---|---|---|---|
| accuracy | 49.3% | 80.0% | FAIL |

### Overall

| Measure | Value |
|---|---|
| Accuracy | 49.3% (37 of 75) |
| Coverage | 100.0% (75 of 75 answered) |
| Accuracy on covered items | 49.3% |

### Per label

| Label | Gold | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| capability | 37 | 75 | 37 | 49.3% | 100.0% |
| upkeep | 15 | 0 | 0 | – | 0.0% |
| governance | 17 | 0 | 0 | – | 0.0% |
| knowledge | 6 | 0 | 0 | – | 0.0% |

### Confusion matrix

Rows are gold labels, columns predicted.

| Gold \ Predicted | capability | upkeep | governance | knowledge | needs human |
|---|---|---|---|---|---|
| capability | 37 | 0 | 0 | 0 | 0 |
| upkeep | 15 | 0 | 0 | 0 | 0 |
| governance | 17 | 0 | 0 | 0 | 0 |
| knowledge | 6 | 0 | 0 | 0 | 0 |

### Flags

On answered items.

| Flag | Gold true | Predicted true | Both | Precision | Recall |
|---|---|---|---|---|---|
| fix | 9 | 0 | 0 | – | 0.0% |

### Share error by week

Each label's share of the answered items, its share of the gold labels, and the difference.

| Week | capability | upkeep | governance | knowledge |
|---|---|---|---|---|
| 2026-W45 | 100.0% vs 45.5% (+54.5 pts) | 0.0% vs 23.6% (-23.6 pts) | 0.0% vs 29.1% (-29.1 pts) | 0.0% vs 1.8% (-1.8 pts) |
| 2026-W46 | 100.0% vs 60.0% (+40.0 pts) | 0.0% vs 10.0% (-10.0 pts) | 0.0% vs 5.0% (-5.0 pts) | 0.0% vs 25.0% (-25.0 pts) |

### Items

| Item | Gold | Predicted | Confidence | Evidence |
|---|---|---|---|---|
| pr-17 | governance | capability ✗ | 100.0% |  |
| pr-18 | governance | capability ✗ | 100.0% |  |
| pr-24 | capability | capability | 100.0% |  |
| pr-27 | capability | capability | 100.0% |  |
| pr-39 | governance | capability ✗ | 100.0% |  |
| pr-42 | governance | capability ✗ | 100.0% |  |
| pr-60 | governance | capability ✗ | 100.0% |  |
| pr-64 | capability | capability | 100.0% |  |
| pr-71 | capability | capability | 100.0% |  |
| pr-104 | capability | capability | 100.0% |  |
| pr-106 | governance | capability ✗ | 100.0% |  |
| pr-107 | governance | capability ✗ | 100.0% |  |
| pr-110 | capability | capability | 100.0% |  |
| pr-116 | governance | capability ✗ | 100.0% |  |
| pr-117 | capability | capability | 100.0% |  |
| pr-135 | governance | capability ✗ | 100.0% |  |
| pr-139 | upkeep | capability ✗ | 100.0% |  |
| pr-140 | governance | capability ✗ | 100.0% |  |
| pr-143 | upkeep | capability ✗ | 100.0% |  |
| pr-185 | capability | capability | 100.0% |  |
| pr-226 | governance | capability ✗ | 100.0% |  |
| pr-230 | capability | capability | 100.0% |  |
| pr-266 | governance | capability ✗ | 100.0% |  |
| pr-279 | upkeep | capability ✗ | 100.0% |  |
| pr-282 | upkeep | capability ✗ | 100.0% |  |
| pr-305 | upkeep | capability ✗ | 100.0% |  |
| pr-310 | upkeep | capability ✗ | 100.0% |  |
| pr-341 | capability | capability | 100.0% |  |
| pr-375 | capability | capability | 100.0% |  |
| pr-384 | upkeep | capability ✗ | 100.0% |  |
| pr-387 | capability | capability | 100.0% |  |
| pr-413 | capability | capability | 100.0% |  |
| pr-427 | capability | capability | 100.0% |  |
| pr-442 | capability | capability | 100.0% |  |
| pr-479 | capability | capability | 100.0% |  |
| pr-484 | knowledge | capability ✗ | 100.0% |  |
| pr-514 | upkeep | capability ✗ | 100.0% |  |
| pr-516 | capability | capability | 100.0% |  |
| pr-532 | upkeep | capability ✗ | 100.0% |  |
| pr-537 | capability | capability | 100.0% |  |
| pr-552 | upkeep | capability ✗ | 100.0% |  |
| pr-556 | capability | capability | 100.0% |  |
| pr-560 | upkeep | capability ✗ | 100.0% |  |
| pr-570 | upkeep | capability ✗ | 100.0% |  |
| pr-571 | upkeep | capability ✗ | 100.0% |  |
| pr-579 | governance | capability ✗ | 100.0% |  |
| pr-585 | governance | capability ✗ | 100.0% |  |
| pr-600 | capability | capability | 100.0% |  |
| pr-610 | governance | capability ✗ | 100.0% |  |
| pr-611 | capability | capability | 100.0% |  |
| pr-622 | capability | capability | 100.0% |  |
| pr-625 | capability | capability | 100.0% |  |
| pr-626 | governance | capability ✗ | 100.0% |  |
| pr-634 | capability | capability | 100.0% |  |
| pr-648 | capability | capability | 100.0% |  |
| pr-682 | capability | capability | 100.0% |  |
| pr-691 | upkeep | capability ✗ | 100.0% |  |
| pr-703 | knowledge | capability ✗ | 100.0% |  |
| pr-704 | knowledge | capability ✗ | 100.0% |  |
| pr-714 | capability | capability | 100.0% |  |
| pr-717 | capability | capability | 100.0% |  |
| pr-720 | knowledge | capability ✗ | 100.0% |  |
| pr-723 | capability | capability | 100.0% |  |
| pr-727 | capability | capability | 100.0% |  |
| pr-741 | capability | capability | 100.0% |  |
| pr-743 | upkeep | capability ✗ | 100.0% |  |
| pr-764 | governance | capability ✗ | 100.0% |  |
| pr-778 | knowledge | capability ✗ | 100.0% |  |
| pr-790 | capability | capability | 100.0% |  |
| pr-833 | capability | capability | 100.0% |  |
| pr-841 | capability | capability | 100.0% |  |
| pr-846 | capability | capability | 100.0% |  |
| pr-864 | capability | capability | 100.0% |  |
| pr-902 | capability | capability | 100.0% |  |
| pr-976 | knowledge | capability ✗ | 100.0% |  |

## Baseline: paths

- **Classifier:** baseline `paths`
- **Mode:** baseline (no model calls)
- **Label set:** `labelsets/effort.yml` sha256 `5e702a9d8962f2c8bf062f2011530d6aef3de8648896fbfc4f3db77be61c3db3`
- **Labelled set:** `data/effort.jsonl` sha256 `f388d8a2708e8c0827f47e7bf7fb2168dff7a371bf211390d29dcf491d77b516`
- **Items:** 75

**Result: FAIL**

### Pass mark

| Check | Value | Bar | |
|---|---|---|---|
| accuracy | 62.7% | 80.0% | FAIL |

### Overall

| Measure | Value |
|---|---|
| Accuracy | 62.7% (47 of 75) |
| Coverage | 100.0% (75 of 75 answered) |
| Accuracy on covered items | 62.7% |

### Per label

| Label | Gold | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| capability | 37 | 13 | 11 | 84.6% | 29.7% |
| upkeep | 15 | 30 | 13 | 43.3% | 86.7% |
| governance | 17 | 26 | 17 | 65.4% | 100.0% |
| knowledge | 6 | 6 | 6 | 100.0% | 100.0% |

### Confusion matrix

Rows are gold labels, columns predicted.

| Gold \ Predicted | capability | upkeep | governance | knowledge | needs human |
|---|---|---|---|---|---|
| capability | 11 | 17 | 9 | 0 | 0 |
| upkeep | 2 | 13 | 0 | 0 | 0 |
| governance | 0 | 0 | 17 | 0 | 0 |
| knowledge | 0 | 0 | 0 | 6 | 0 |

### Flags

On answered items.

| Flag | Gold true | Predicted true | Both | Precision | Recall |
|---|---|---|---|---|---|
| fix | 9 | 0 | 0 | – | 0.0% |

### Share error by week

Each label's share of the answered items, its share of the gold labels, and the difference.

| Week | capability | upkeep | governance | knowledge |
|---|---|---|---|---|
| 2026-W45 | 21.8% vs 45.5% (-23.6 pts) | 36.4% vs 23.6% (+12.7 pts) | 40.0% vs 29.1% (+10.9 pts) | 1.8% vs 1.8% (0.0 pts) |
| 2026-W46 | 5.0% vs 60.0% (-55.0 pts) | 50.0% vs 10.0% (+40.0 pts) | 20.0% vs 5.0% (+15.0 pts) | 25.0% vs 25.0% (0.0 pts) |

### Items

| Item | Gold | Predicted | Confidence | Evidence |
|---|---|---|---|---|
| pr-17 | governance | governance | 100.0% |  |
| pr-18 | governance | governance | 100.0% |  |
| pr-24 | capability | upkeep ✗ | 100.0% |  |
| pr-27 | capability | capability | 100.0% |  |
| pr-39 | governance | governance | 100.0% |  |
| pr-42 | governance | governance | 100.0% |  |
| pr-60 | governance | governance | 100.0% |  |
| pr-64 | capability | upkeep ✗ | 100.0% |  |
| pr-71 | capability | capability | 100.0% |  |
| pr-104 | capability | upkeep ✗ | 100.0% |  |
| pr-106 | governance | governance | 100.0% |  |
| pr-107 | governance | governance | 100.0% |  |
| pr-110 | capability | upkeep ✗ | 100.0% |  |
| pr-116 | governance | governance | 100.0% |  |
| pr-117 | capability | governance ✗ | 100.0% |  |
| pr-135 | governance | governance | 100.0% |  |
| pr-139 | upkeep | capability ✗ | 100.0% |  |
| pr-140 | governance | governance | 100.0% |  |
| pr-143 | upkeep | upkeep | 100.0% |  |
| pr-185 | capability | upkeep ✗ | 100.0% |  |
| pr-226 | governance | governance | 100.0% |  |
| pr-230 | capability | capability | 100.0% |  |
| pr-266 | governance | governance | 100.0% |  |
| pr-279 | upkeep | upkeep | 100.0% |  |
| pr-282 | upkeep | upkeep | 100.0% |  |
| pr-305 | upkeep | upkeep | 100.0% |  |
| pr-310 | upkeep | upkeep | 100.0% |  |
| pr-341 | capability | capability | 100.0% |  |
| pr-375 | capability | capability | 100.0% |  |
| pr-384 | upkeep | upkeep | 100.0% |  |
| pr-387 | capability | capability | 100.0% |  |
| pr-413 | capability | capability | 100.0% |  |
| pr-427 | capability | capability | 100.0% |  |
| pr-442 | capability | capability | 100.0% |  |
| pr-479 | capability | governance ✗ | 100.0% |  |
| pr-484 | knowledge | knowledge | 100.0% |  |
| pr-514 | upkeep | upkeep | 100.0% |  |
| pr-516 | capability | governance ✗ | 100.0% |  |
| pr-532 | upkeep | upkeep | 100.0% |  |
| pr-537 | capability | governance ✗ | 100.0% |  |
| pr-552 | upkeep | capability ✗ | 100.0% |  |
| pr-556 | capability | capability | 100.0% |  |
| pr-560 | upkeep | upkeep | 100.0% |  |
| pr-570 | upkeep | upkeep | 100.0% |  |
| pr-571 | upkeep | upkeep | 100.0% |  |
| pr-579 | governance | governance | 100.0% |  |
| pr-585 | governance | governance | 100.0% |  |
| pr-600 | capability | upkeep ✗ | 100.0% |  |
| pr-610 | governance | governance | 100.0% |  |
| pr-611 | capability | upkeep ✗ | 100.0% |  |
| pr-622 | capability | upkeep ✗ | 100.0% |  |
| pr-625 | capability | governance ✗ | 100.0% |  |
| pr-626 | governance | governance | 100.0% |  |
| pr-634 | capability | governance ✗ | 100.0% |  |
| pr-648 | capability | upkeep ✗ | 100.0% |  |
| pr-682 | capability | upkeep ✗ | 100.0% |  |
| pr-691 | upkeep | upkeep | 100.0% |  |
| pr-703 | knowledge | knowledge | 100.0% |  |
| pr-704 | knowledge | knowledge | 100.0% |  |
| pr-714 | capability | upkeep ✗ | 100.0% |  |
| pr-717 | capability | upkeep ✗ | 100.0% |  |
| pr-720 | knowledge | knowledge | 100.0% |  |
| pr-723 | capability | governance ✗ | 100.0% |  |
| pr-727 | capability | capability | 100.0% |  |
| pr-741 | capability | upkeep ✗ | 100.0% |  |
| pr-743 | upkeep | upkeep | 100.0% |  |
| pr-764 | governance | governance | 100.0% |  |
| pr-778 | knowledge | knowledge | 100.0% |  |
| pr-790 | capability | governance ✗ | 100.0% |  |
| pr-833 | capability | upkeep ✗ | 100.0% |  |
| pr-841 | capability | governance ✗ | 100.0% |  |
| pr-846 | capability | upkeep ✗ | 100.0% |  |
| pr-864 | capability | upkeep ✗ | 100.0% |  |
| pr-902 | capability | upkeep ✗ | 100.0% |  |
| pr-976 | knowledge | knowledge | 100.0% |  |

## The model

Not run: no recording of sample 1 for item 'pr-17' with this label set and text in recordings/effort/claude-haiku-5-5.jsonl; a --live run records it. A `swarm classify eval effort --split test --live` records its replies (GOV-0045).
