# NPI Trial & DOE Analyzer

A Python command-line tool that manages engineering / NPI trial runs and
analyzes a 2^3 full-factorial designed experiment (DOE) with center points
and replicates — built as a portfolio project for a Tesla NCM Process
Technician application (Buffalo, NY).

## Overview

Process technicians live in the gap between engineering trials and daily
production. This tool covers both sides of that job: it keeps a structured
log of NPI trials (trial ID, date, line, engineer, objective, status,
observations) and it turns a trial's raw run data into a decision. The
included example is a lamination process DOE for an NCM (Nickel Cobalt
Manganese) line: three factors — lamination temperature, line speed and
cure time — tested against first-pass yield and defect count, analyzed with
the Yates algorithm and ANOVA, and closed out with a go / no-go
recommendation and concrete next steps.

Everything runs from one file, `npi_doe.py`, with no paid tools and no
statsmodels dependency.

## Why this matters for the NCM Process Technician role

The role's core work maps directly onto this project:

| Job responsibility | How this project demonstrates it |
| --- | --- |
| Support and monitor engineering / NPI trials | Trial log (`--trials`) tracks 10 NPI trials across two lines with status, owners and observations; the DOE trial itself (NPI-2026-004) is managed end to end. |
| Analyze yield and process data | First-pass yield and defect count are the two responses; the analysis quantifies every factor's effect with significance tests instead of eyeballing charts. |
| Root cause and countermeasures | The effect Pareto and interaction plots isolate which factors — and which factor combinations — actually move yield, so countermeasures target the real driver (here, the temperature x speed interaction). |
| Maintain manufacturing instructions | The report's predicted best setting is written up as a concrete, auditable change to temperature, speed and cure limits, with a hold condition until the follow-up trial confirms it. |
| Day-to-day line coverage and rapid response on out-of-control processes | The trial log doubles as a line record: baseline characterization, oven recalibration, 5S audit and a virtual-inventory reconciliation are all logged with outcomes. |
| Manage small cross-functional projects | The axial-point follow-up trial (NPI-2026-005) is scoped, justified by the curvature test and handed over with owners and dates. |
| Disposition of unaccounted-for virtual inventory | Trial NPI-2026-008 tracks the virtual-inventory reconciliation pilot and its disposition status. |
| Lean / 5S | Trial NPI-2026-009 logs the 5S line-side audit, including a measured changeover-time improvement. |
| Data tools and record-keeping | Pandas / SQL-style tabular data, reproducible seeded datasets, CSVs committed to the repo, and a generated Markdown report — the same record-keeping discipline the role requires. |

## Features

- **Synthetic data generator** (`--generate`): 2^3 full-factorial DOE (8
  corner treatments x 2 replicates + 4 center points = 20 runs, randomized
  run order, fixed seed 42) plus a 10-row NPI trial log. Regenerating always
  produces identical data.
- **Yates algorithm**: main effects and two-factor interactions computed
  from treatment totals, cross-checked against an ordinary-least-squares fit
  (identical results).
- **ANOVA with F-tests and p-values** (SciPy): all seven factorial effects,
  a curvature test (factorial mean vs center mean) and a pure-error term
  from the replicates.
- **Four charts** (Matplotlib): effect Pareto with a significance limit,
  main-effects plot, two-factor interaction plots, and observed-vs-predicted
  yield.
- **Predicted best setting**: the model is evaluated at every corner and
  the best one is reported with predicted yield and predicted defect count.
- **Go / no-go recommendation**: a rules-based decision (target yield,
  significant main effects, curvature test) with a written rationale and
  next steps, saved as `outputs/trial_report.md`.
- **Trial log summary** (`--trials`): status counts and the full log with
  observations.

## Tech stack

- Python 3.10+
- pandas — tabular data, CSV input/output
- NumPy — Yates algorithm and array math
- SciPy — F-tests, t-tests, p-values
- Matplotlib — charts (Agg backend, no display needed)

## Project structure

```text
tesla-npi-doe-trial-analyzer/
├── npi_doe.py                  # the whole tool: generate, analyze, trials
├── requirements.txt
├── .gitignore
├── README.md
├── data/
│   ├── doe_runs.csv           # 20 DOE runs (generated, committed)
│   └── trial_log.csv          # 10 NPI trials (generated, committed)
└── outputs/
    ├── effect_pareto.png
    ├── main_effects.png
    ├── interaction_plot.png
    ├── observed_vs_predicted.png
    └── trial_report.md         # go/no-go report (generated, committed)
```

## How to run

```bash
pip install -r requirements.txt

# 1. Generate the synthetic datasets (seeded, reproducible)
python npi_doe.py --generate

# 2. Run the DOE analysis — charts + trial report land in outputs/
python npi_doe.py --analyze

# 3. Print the NPI trial log summary
python npi_doe.py --trials
```

Running `--analyze` without data present generates it first. Running the
commands again overwrites the outputs with identical results.

## Sample results

Results below are the actual output of `python npi_doe.py --analyze` on
the generated data (trial NPI-2026-004, 20 runs, overall mean yield
93.09%).

**Design.** Factors: lamination temperature 150–170 degC, line speed
8–12 m/min, cure time 30–45 min. Responses: first-pass yield (%) and
defect count per 200 units inspected.

**Effects (Yates algorithm, alpha = 0.05).**

| Effect | Estimate (pp) | p-value | Significant |
| --- | --- | --- | --- |
| A — Lamination temperature | +4.38 | < 0.001 | Yes |
| B — Line speed | −2.84 | < 0.001 | Yes |
| C — Cure time | +2.87 | < 0.001 | Yes |
| AB — Temp x Speed | +2.38 | < 0.001 | Yes |
| AC — Temp x Cure | −1.71 | < 0.001 | Yes |
| BC — Speed x Cure | +1.02 | 0.003 | Yes |
| ABC | +0.34 | 0.236 | No |

**What the numbers say.**

- Lamination temperature is the dominant driver: moving it from 150 to
  170 degC lifts yield by about 4.4 points.
- The temperature x speed interaction is the finding that matters on the
  floor: at low temperature, running fast costs about 5.2 points of yield;
  at high temperature it costs only about 0.5 points. Speed is safe only
  when the line is hot — a one-factor-at-a-time trial would have missed
  this entirely.
- The model fits well (R² = 0.988 on the factorial runs).
- The curvature test is significant (p = 0.024): the center points
  averaged 93.72% against a factorial mean of 92.93%, so the response
  surface is not flat in the middle of the design space.

**Predicted best setting:** 170 degC, 12 m/min, 45 min — predicted
first-pass yield **96.15%**, predicted defects **7.0 per 200 units**.

**Recommendation: CONDITIONAL GO.** The predicted yield clears the 95%
target and all three main effects are significant, but the significant
curvature means the optimum has not been pinned down yet. Next step: run
the planned axial-point follow-up (trial NPI-2026-005) around the best
setting, hold the manufacturing-instruction change until it confirms, and
keep production on the current approved settings with a weekly yield watch
against the 93% floor.

**Trial log:** 10 trials — 5 complete, 2 running, 3 planned — across NCM
Line 1 and Line 2, including the DOE trial, an oven recalibration, a 5S
audit and a virtual-inventory reconciliation pilot.

## Synthetic data disclaimer

All data in this repository is synthetic. It was generated in code with a
fixed seed (NumPy `default_rng(42)`) from a stated ground-truth model so
that results are reproducible; it is not Tesla production data, not
measured on any real line, and must not be used for real process
decisions. The trial log, engineer names, dates and observations are
fictional and exist only to demonstrate the workflow. The factor levels,
responses and conclusions are illustrative of the method, not of any real
Tesla process.
