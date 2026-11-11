#!/usr/bin/env python3
"""
NPI Trial & DOE Analyzer
========================

A command-line tool for managing engineering / NPI trial runs and analyzing
a 2^3 full-factorial designed experiment (DOE) with center points and
replicates. Built as a portfolio project for a Tesla NCM (Nickel Cobalt
Manganese) Process Technician application: the role covers day-to-day
production line coverage, rapid response on out-of-control processes, root
cause and countermeasures, maintaining manufacturing instructions, yield and
process-data analysis, Lean / 5S, small cross-functional projects, support
and monitoring of engineering / NPI trials, and disposition of unaccounted
virtual inventory.

What it does
------------
* ``--generate``  Create synthetic trial-log and DOE datasets (seeded and
  reproducible). All data is synthetic and labelled as such.
* ``--analyze``   Run the DOE analysis (Yates algorithm, ANOVA with
  F-tests, effect Pareto, main-effects and interaction plots, predicted
  best setting) and write charts plus a go/no-go trial report.
* ``--trials``    Print a summary of the NPI trial log.

The analysis uses only numpy / scipy / pandas / matplotlib -- no
statsmodels dependency.

Usage
-----
    python npi_doe.py --generate
    python npi_doe.py --analyze
    python npi_doe.py --trials

Author: Anusha Bathini
Data: 100% synthetic, generated with a fixed seed (42) for reproducibility.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe: no display required
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 42
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

DOE_RUNS_CSV = DATA_DIR / "doe_runs.csv"
TRIAL_LOG_CSV = DATA_DIR / "trial_log.csv"
REPORT_MD = OUTPUT_DIR / "trial_report.md"

DOE_TRIAL_ID = "NPI-2026-004"
UNITS_PER_RUN = 200          # units inspected per DOE run
TARGET_YIELD = 95.0          # go/no-go threshold, first-pass yield (%)
ALPHA = 0.05                 # significance level
N_REPS = 2                   # replicates per corner treatment
N_CENTER = 4                 # center points

# Factors: coded -1 / 0 / +1 with real-world levels.
# A = lamination temperature, B = line speed, C = cure time.
FACTORS = {
    "A": {"name": "Lamination temperature", "short": "Temp",
          "low": 150.0, "high": 170.0, "center": 160.0, "unit": "degC"},
    "B": {"name": "Line speed", "short": "Speed",
          "low": 8.0, "high": 12.0, "center": 10.0, "unit": "m/min"},
    "C": {"name": "Cure time", "short": "Cure",
          "low": 30.0, "high": 45.0, "center": 37.5, "unit": "min"},
}

# Yates standard order for a 2^3 design: (1), a, b, ab, c, ac, bc, abc.
STD_ORDER = [(-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
             (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)]
EFFECT_LABELS = ["Mean", "A", "B", "AB", "C", "AC", "BC", "ABC"]
TERM_FACTORS = {"A": ("A",), "B": ("B",), "C": ("C",),
                "AB": ("A", "B"), "AC": ("A", "C"), "BC": ("B", "C"),
                "ABC": ("A", "B", "C")}

# True (synthetic) yield model in coded units. Used ONLY to generate data;
# the analysis re-estimates every effect from the generated runs.
TRUE_YIELD = {"intercept": 93.0,
              "A": 2.1, "B": -1.4, "C": 1.8,
              "AB": 1.2, "AC": -0.9, "BC": 0.4, "ABC": 0.3}
YIELD_NOISE_SD = 0.8
CENTER_CURVATURE = 0.3   # small offset at the center point

# NPI trial log (synthetic). The DOE runs below belong to NPI-2026-004.
TRIALS = [
    {"trial_id": "NPI-2026-001", "date": "2026-09-08", "line": "NCM Line 1",
     "engineer": "M. Okafor", "objective": "Baseline yield characterization",
     "status": "complete",
     "observations": "Baseline first-pass yield 91.8% over 3 shifts; "
                     "lamination temperature flagged as largest variance source."},
    {"trial_id": "NPI-2026-002", "date": "2026-09-22", "line": "NCM Line 2",
     "engineer": "J. Alvarez", "objective": "New adhesive supplier qualification",
     "status": "complete",
     "observations": "Alternate adhesive passed peel test; no yield impact "
                     "observed. Approved as second source."},
    {"trial_id": "NPI-2026-003", "date": "2026-10-05", "line": "NCM Line 1",
     "engineer": "R. Chen", "objective": "Cure oven profile validation",
     "status": "complete",
     "observations": "Oven zone 3 ran 2 degC below setpoint; recalibrated and "
                     "re-verified before the DOE."},
    {"trial_id": "NPI-2026-004", "date": "2026-10-19", "line": "NCM Line 2",
     "engineer": "J. Alvarez",
     "objective": "2^3 factorial DOE: lamination temperature x line speed x cure time",
     "status": "complete",
     "observations": "Best corner (170 degC, 12 m/min, 45 min) averaged the "
                     "highest yield across replicates. Curvature detected "
                     "(center mean above factorial mean); axial follow-up "
                     "recommended. See trial_report.md."},
    {"trial_id": "NPI-2026-005", "date": "2026-10-28", "line": "NCM Line 2",
     "engineer": "J. Alvarez",
     "objective": "Axial-point follow-up around DOE best setting",
     "status": "planned",
     "observations": "Curvature was detected in the DOE (p = 0.024), so "
                     "face-centered axial runs will map the response surface "
                     "around the best setting before scale-up."},
    {"trial_id": "NPI-2026-006", "date": "2026-11-02", "line": "NCM Line 1",
     "engineer": "R. Chen", "objective": "New separator material trial",
     "status": "running",
     "observations": "First two lots complete; tracking edge-defect rate "
                     "against the NPI-2026-004 baseline."},
    {"trial_id": "NPI-2026-007", "date": "2026-11-09", "line": "NCM Line 2",
     "engineer": "M. Okafor", "objective": "Cure oven profile validation (repeat)",
     "status": "planned",
     "observations": "Repeat of NPI-2026-003 after the zone 3 recalibration."},
    {"trial_id": "NPI-2026-008", "date": "2026-11-04", "line": "NCM Line 1",
     "engineer": "J. Alvarez",
     "objective": "Virtual inventory reconciliation pilot",
     "status": "running",
     "observations": "Reconciling unaccounted-for virtual inventory on Line 1; "
                     "two of five variances dispositioned so far."},
    {"trial_id": "NPI-2026-009", "date": "2026-10-12", "line": "NCM Line 2",
     "engineer": "R. Chen", "objective": "5S line-side audit and reset",
     "status": "complete",
     "observations": "Shadow boards restocked; lamination changeover kit "
                     "relocated to point of use. Changeover time down 6 min."},
    {"trial_id": "NPI-2026-010", "date": "2026-11-16", "line": "NCM Line 2",
     "engineer": "M. Okafor", "objective": "Second-source lamination film trial",
     "status": "planned",
     "observations": "Film lots staged; trial to run at the DOE best setting "
                     "once the go/no-go decision is signed off."},
]

CHART_STYLE = {"color_sig": "#C0392B", "color_nonsig": "#7F8C8D",
               "color_line": "#2C3E50", "color_accent": "#C0392B"}


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def _true_yield(a: int, b: int, c: int) -> float:
    """Synthetic ground-truth yield model (coded units)."""
    return (TRUE_YIELD["intercept"] + TRUE_YIELD["A"] * a + TRUE_YIELD["B"] * b
            + TRUE_YIELD["C"] * c + TRUE_YIELD["AB"] * a * b
            + TRUE_YIELD["AC"] * a * c + TRUE_YIELD["BC"] * b * c
            + TRUE_YIELD["ABC"] * a * b * c)


def _actual_level(factor: str, coded: int) -> float:
    """Convert a coded level (-1 / 0 / +1) to its real-world value."""
    spec = FACTORS[factor]
    return {(-1): spec["low"], 0: spec["center"], 1: spec["high"]}[coded]


def generate_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate the synthetic DOE runs and trial log; write both CSVs."""
    rng = np.random.default_rng(SEED)
    rows: list[dict] = []

    # Corner treatments, 2 replicates each.
    for a, b, c in STD_ORDER:
        for _ in range(N_REPS):
            y = _true_yield(a, b, c) + rng.normal(0, YIELD_NOISE_SD)
            y = float(np.clip(y, 85.0, 99.5))
            lam = max(0.5, (100.0 - y) * 1.5)
            defects = int(rng.poisson(lam))
            rows.append({"trial_id": DOE_TRIAL_ID, "a": a, "b": b, "c": c,
                         "is_center": False,
                         "temp_degc": _actual_level("A", a),
                         "speed_m_min": _actual_level("B", b),
                         "cure_min": _actual_level("C", c),
                         "yield_pct": round(y, 2),
                         "defect_count": defects,
                         "units_inspected": UNITS_PER_RUN})

    # Center points.
    for _ in range(N_CENTER):
        y = TRUE_YIELD["intercept"] + CENTER_CURVATURE + rng.normal(0, YIELD_NOISE_SD)
        y = float(np.clip(y, 85.0, 99.5))
        lam = max(0.5, (100.0 - y) * 1.5)
        defects = int(rng.poisson(lam))
        rows.append({"trial_id": DOE_TRIAL_ID, "a": 0, "b": 0, "c": 0,
                     "is_center": True,
                     "temp_degc": _actual_level("A", 0),
                     "speed_m_min": _actual_level("B", 0),
                     "cure_min": _actual_level("C", 0),
                     "yield_pct": round(y, 2),
                     "defect_count": defects,
                     "units_inspected": UNITS_PER_RUN})

    # Randomize execution order (seeded, reproducible).
    order = rng.permutation(len(rows))
    runs = pd.DataFrame([rows[i] for i in order]).reset_index(drop=True)
    runs.insert(0, "run_id", [f"R{i + 1:02d}" for i in range(len(runs))])
    runs["run_order"] = range(1, len(runs) + 1)

    trials = pd.DataFrame(TRIALS)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    runs.to_csv(DOE_RUNS_CSV, index=False)
    trials.to_csv(TRIAL_LOG_CSV, index=False)
    print(f"Wrote {len(runs)} DOE runs to {DOE_RUNS_CSV}")
    print(f"Wrote {len(trials)} trial-log rows to {TRIAL_LOG_CSV}")
    return runs, trials


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the CSVs, generating them first if they are missing."""
    if not DOE_RUNS_CSV.exists() or not TRIAL_LOG_CSV.exists():
        print("Data files not found -- generating synthetic data first.")
        return generate_data()
    return pd.read_csv(DOE_RUNS_CSV), pd.read_csv(TRIAL_LOG_CSV)


# ---------------------------------------------------------------------------
# DOE analysis (Yates algorithm + ANOVA)
# ---------------------------------------------------------------------------

def yates(totals: np.ndarray, n_reps: int, k: int = 3) -> dict:
    """Run Yates' algorithm on treatment totals in standard order.

    Returns a dict with, for each effect, its contrast, effect estimate
    (change in response from the -1 to the +1 level) and sum of squares.
    """
    col = np.asarray(totals, dtype=float).copy()
    for _ in range(k):
        nxt = np.empty_like(col)
        half = len(col) // 2
        nxt[:half] = col[0::2] + col[1::2]   # sums of adjacent pairs
        nxt[half:] = col[1::2] - col[0::2]   # differences of adjacent pairs
        col = nxt
    contrasts = col
    out = {}
    for i, label in enumerate(EFFECT_LABELS):
        contrast = contrasts[i]
        if label == "Mean":
            out[label] = {"contrast": contrast,
                          "effect": contrast / (n_reps * 2 ** k),
                          "ss": None}
        else:
            out[label] = {"contrast": contrast,
                          "effect": contrast / (n_reps * 2 ** (k - 1)),
                          "ss": contrast ** 2 / (n_reps * 2 ** k)}
    return out


def analyze_doe(runs: pd.DataFrame) -> dict:
    """Full DOE analysis on first-pass yield; returns every result needed
    for the charts and the report."""
    corners = runs[~runs["is_center"]].copy()
    centers = runs[runs["is_center"]].copy()

    # Treatment totals in Yates standard order.
    totals = []
    for a, b, c in STD_ORDER:
        mask = (corners["a"] == a) & (corners["b"] == b) & (corners["c"] == c)
        totals.append(corners.loc[mask, "yield_pct"].sum())
    y = yates(np.array(totals), N_REPS)

    # Pure error: replicate variation within corner treatments + centers.
    ss_pe = 0.0
    for a, b, c in STD_ORDER:
        mask = (corners["a"] == a) & (corners["b"] == b) & (corners["c"] == c)
        vals = corners.loc[mask, "yield_pct"].to_numpy()
        ss_pe += float(((vals - vals.mean()) ** 2).sum())
    c_vals = centers["yield_pct"].to_numpy()
    ss_pe += float(((c_vals - c_vals.mean()) ** 2).sum())
    df_pe = len(STD_ORDER) * (N_REPS - 1) + (N_CENTER - 1)
    ms_pe = ss_pe / df_pe
    se_effect = float(np.sqrt(ms_pe * 4.0 / (N_REPS * 2 ** 3)))
    t_crit = float(stats.t.ppf(1 - ALPHA / 2, df_pe))

    # Curvature test: factorial mean vs center mean.
    n_f, n_c = len(corners), len(centers)
    mean_f = float(corners["yield_pct"].mean())
    mean_c = float(centers["yield_pct"].mean())
    ss_curv = n_f * n_c * (mean_f - mean_c) ** 2 / (n_f + n_c)

    # ANOVA rows for the 7 factorial effects.
    anova_rows = []
    effects_rows = []
    for label in EFFECT_LABELS[1:]:
        ss = y[label]["ss"]
        f_stat = ss / ms_pe
        p_val = float(stats.f.sf(f_stat, 1, df_pe))
        anova_rows.append({"Source": label, "SS": ss, "df": 1, "MS": ss,
                           "F": f_stat, "p": p_val})
        effect = y[label]["effect"]
        t_stat = effect / se_effect
        effects_rows.append({"Effect": label, "Estimate": effect,
                             "SE": se_effect, "t": t_stat,
                             "p": float(stats.t.sf(abs(t_stat), df_pe) * 2),
                             "Significant": p_val < ALPHA})
    f_curv = ss_curv / ms_pe
    anova_rows.append({"Source": "Curvature", "SS": ss_curv, "df": 1,
                       "MS": ss_curv, "F": f_curv,
                       "p": float(stats.f.sf(f_curv, 1, df_pe))})
    anova_rows.append({"Source": "Pure error", "SS": ss_pe, "df": df_pe,
                       "MS": ms_pe, "F": np.nan, "p": np.nan})
    ss_total = float(((runs["yield_pct"] - runs["yield_pct"].mean()) ** 2).sum())
    anova_rows.append({"Source": "Total", "SS": ss_total,
                       "df": len(runs) - 1, "MS": np.nan, "F": np.nan,
                       "p": np.nan})
    anova = pd.DataFrame(anova_rows)
    effects = pd.DataFrame(effects_rows)

    # Fitted model (coded units) and predicted best corner.
    intercept = y["Mean"]["effect"]
    coefs = {label: y[label]["effect"] / 2.0 for label in EFFECT_LABELS[1:]}

    def predict(a: int, b: int, c: int) -> float:
        vals = {"A": a, "B": b, "C": c}
        pred = intercept
        for label, facs in TERM_FACTORS.items():
            term = 1
            for f in facs:
                term *= vals[f]
            pred += coefs[label] * term
        return pred

    corners_pred = [(a, b, c, predict(a, b, c)) for a, b, c in STD_ORDER]
    best_a, best_b, best_c, best_yield = max(corners_pred, key=lambda t: t[3])

    # Same factorial model fitted to defect count, for the best-setting
    # defect prediction.
    defect_totals = []
    for a, b, c in STD_ORDER:
        mask = (corners["a"] == a) & (corners["b"] == b) & (corners["c"] == c)
        defect_totals.append(corners.loc[mask, "defect_count"].sum())
    yd = yates(np.array(defect_totals, dtype=float), N_REPS)
    d_intercept = yd["Mean"]["effect"]
    d_coefs = {label: yd[label]["effect"] / 2.0 for label in EFFECT_LABELS[1:]}
    best_defects = d_intercept
    vals = {"A": best_a, "B": best_b, "C": best_c}
    for label, facs in TERM_FACTORS.items():
        term = 1
        for f in facs:
            term *= vals[f]
        best_defects += d_coefs[label] * term

    # Observed vs predicted (corners + centers, predicted = intercept).
    runs_pred = []
    for _, row in runs.iterrows():
        if row["is_center"]:
            runs_pred.append(intercept)
        else:
            runs_pred.append(predict(int(row["a"]), int(row["b"]), int(row["c"])))
    runs = runs.copy()
    runs["predicted_yield"] = np.round(runs_pred, 2)
    corner_obs = corners["yield_pct"].to_numpy()
    corner_pred = np.array([predict(int(r["a"]), int(r["b"]), int(r["c"]))
                            for _, r in corners.iterrows()])
    ss_reg = float(((corner_pred - corner_obs.mean()) ** 2).sum())
    ss_tot_c = float(((corner_obs - corner_obs.mean()) ** 2).sum())
    r_squared = ss_reg / ss_tot_c if ss_tot_c else float("nan")

    # Go / no-go decision.
    sig_main = effects[(effects["Effect"].isin(["A", "B", "C"]))
                       & (effects["Significant"])]
    curv_p = float(anova.loc[anova["Source"] == "Curvature", "p"].iloc[0])
    if best_yield >= TARGET_YIELD and len(sig_main) >= 1 and curv_p >= ALPHA:
        decision = "GO"
        rationale = (
            f"Predicted best-setting yield of {best_yield:.2f}% clears the "
            f"{TARGET_YIELD:.0f}% target, {len(sig_main)} main effect(s) are "
            "statistically significant, and the curvature test is not "
            f"significant (p = {curv_p:.3f}), so a linear model is adequate "
            "for scale-up.")
    elif best_yield >= TARGET_YIELD and len(sig_main) >= 1:
        decision = "CONDITIONAL GO"
        rationale = (
            f"Predicted best-setting yield of {best_yield:.2f}% clears the "
            f"{TARGET_YIELD:.0f}% target and {len(sig_main)} main effect(s) "
            "are significant, but the curvature test is significant "
            f"(p = {curv_p:.3f}): the center points averaged {mean_c:.2f}% "
            f"against a factorial mean of {mean_f:.2f}%, so the response "
            "surface is not flat in the middle of the design space. Confirm "
            "the optimum with the planned axial-point follow-up before full "
            "scale-up.")
    elif best_yield >= TARGET_YIELD - 1.0:
        decision = "CONDITIONAL GO"
        rationale = (
            f"Predicted best-setting yield of {best_yield:.2f}% is within one "
            f"point of the {TARGET_YIELD:.0f}% target but does not clear it. "
            "Confirm with the planned axial-point follow-up before full "
            "scale-up.")
    else:
        decision = "NO-GO"
        rationale = (
            f"Predicted best-setting yield of {best_yield:.2f}% is below the "
            f"{TARGET_YIELD:.0f}% target. Do not scale up; re-scope the "
            "factor ranges or investigate additional factors.")

    return {"runs": runs, "corners": corners, "centers": centers,
            "effects": effects, "anova": anova, "intercept": intercept,
            "coefs": coefs, "se_effect": se_effect, "t_crit": t_crit,
            "df_error": df_pe, "ms_error": ms_pe,
            "mean_factorial": mean_f, "mean_center": mean_c,
            "curvature_p": curv_p, "best": (best_a, best_b, best_c),
            "best_yield": best_yield, "best_defects": best_defects,
            "r_squared": r_squared, "decision": decision,
            "rationale": rationale}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _save(fig: plt.Figure, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_effect_pareto(effects: pd.DataFrame, se_effect: float,
                        t_crit: float) -> Path:
    """Pareto chart of absolute effect sizes with a significance line."""
    df = effects.assign(abs_effect=effects["Estimate"].abs())
    df = df.sort_values("abs_effect", ascending=True)
    threshold = t_crit * se_effect
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = [CHART_STYLE["color_sig"] if s else CHART_STYLE["color_nonsig"]
              for s in df["Significant"]]
    ax.barh(df["Effect"], df["abs_effect"], color=colors, height=0.6)
    ax.axvline(threshold, color=CHART_STYLE["color_accent"], linestyle="--",
               linewidth=1.5, label=f"Significance limit ({threshold:.2f})")
    ax.set_xlabel("Absolute effect on first-pass yield (percentage points)")
    ax.set_title("Effect Pareto — NPI-2026-004 DOE (first-pass yield)")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(row["abs_effect"] + 0.05, i, f"{row['abs_effect']:.2f}",
                va="center", fontsize=9)
    return _save(fig, "effect_pareto.png")


def chart_main_effects(corners: pd.DataFrame) -> Path:
    """Main-effects plot: mean yield at the low (-1) and high (+1) level
    of each factor."""
    fig, axes = plt.subplots(1, 3, figsize=(10, 4), sharey=True)
    for ax, factor in zip(axes, ["a", "b", "c"]):
        means = corners.groupby(factor)["yield_pct"].mean()
        ax.plot([-1, 1], [means[-1], means[1]], marker="o",
                color=CHART_STYLE["color_line"], linewidth=2)
        for x, m in zip([-1, 1], [means[-1], means[1]]):
            ax.annotate(f"{m:.2f}%", (x, m), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=9)
        ax.set_xticks([-1, 1])
        ax.set_xticklabels(["Low (-1)", "High (+1)"])
        spec = FACTORS[factor.upper()]
        ax.set_title(f"{spec['short']}\n{spec['name']}", fontsize=10)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Mean first-pass yield (%)")
    fig.suptitle("Main effects — mean first-pass yield by factor level",
                 fontsize=12)
    return _save(fig, "main_effects.png")


def chart_interactions(corners: pd.DataFrame) -> Path:
    """Two-factor interaction plots (AB, AC, BC)."""
    fig, axes = plt.subplots(1, 3, figsize=(11, 4), sharey=True)
    pairs = [("a", "b", "A", "B"), ("a", "c", "A", "C"), ("b", "c", "B", "C")]
    for ax, (f1, f2, l1, l2) in zip(axes, pairs):
        for level in (-1, 1):
            sub = corners[corners[f2] == level]
            means = sub.groupby(f1)["yield_pct"].mean()
            ax.plot([-1, 1], [means[-1], means[1]], marker="o",
                    label=f"{FACTORS[l2]['short']} = {'High (+1)' if level == 1 else 'Low (-1)'}")
        ax.set_xticks([-1, 1])
        ax.set_xticklabels(["Low (-1)", "High (+1)"])
        ax.set_xlabel(f"{FACTORS[l1]['short']} ({FACTORS[l1]['name']})")
        ax.set_title(f"{l1} x {l2} interaction", fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Mean first-pass yield (%)")
    fig.suptitle("Two-factor interactions — mean first-pass yield",
                 fontsize=12)
    return _save(fig, "interaction_plot.png")


def chart_observed_vs_predicted(runs: pd.DataFrame, r_squared: float) -> Path:
    """Observed vs predicted yield for every run."""
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    centers = runs[runs["is_center"]]
    corners = runs[~runs["is_center"]]
    ax.scatter(corners["predicted_yield"], corners["yield_pct"],
               label="Factorial runs", color=CHART_STYLE["color_line"], s=45)
    ax.scatter(centers["predicted_yield"], centers["yield_pct"],
               label="Center points", color=CHART_STYLE["color_accent"],
               marker="s", s=45)
    lo = min(runs["yield_pct"].min(), runs["predicted_yield"].min()) - 1
    hi = max(runs["yield_pct"].max(), runs["predicted_yield"].max()) + 1
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=1, label="y = x")
    ax.set_xlabel("Predicted first-pass yield (%)")
    ax.set_ylabel("Observed first-pass yield (%)")
    ax.set_title(f"Observed vs predicted yield (R² = {r_squared:.3f})")
    ax.legend()
    ax.grid(alpha=0.3)
    return _save(fig, "observed_vs_predicted.png")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _md_table(df: pd.DataFrame, float_fmt: str = "{:.3f}") -> str:
    """Render a DataFrame as a Markdown table (no tabulate dependency)."""
    header = "| " + " | ".join(df.columns) + " |"
    divider = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, divider]
    for _, row in df.iterrows():
        cells = []
        for val in row:
            if isinstance(val, float) and np.isnan(val):
                cells.append("--")
            elif isinstance(val, float):
                cells.append(float_fmt.format(val))
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(res: dict) -> Path:
    """Write outputs/trial_report.md from the analysis results."""
    a, b, c = res["best"]
    best_actual = {"A": _actual_level("A", a), "B": _actual_level("B", b),
                   "C": _actual_level("C", c)}
    anova = res["anova"].copy()
    anova["p"] = anova["p"].apply(lambda p: f"{p:.4f}" if pd.notna(p) else "--")
    anova["F"] = anova["F"].apply(lambda f: f"{f:.2f}" if pd.notna(f) else "--")
    effects = res["effects"].copy()
    effects["Significant"] = effects["Significant"].map({True: "Yes", False: "No"})

    sig = effects[effects["Significant"] == "Yes"]["Effect"].tolist()
    if res["decision"] == "GO":
        next_steps = [
            "Lock the best setting into the manufacturing instructions and "
            "update the control plan with the new temperature, speed and cure "
            "limits.",
            "Hand the best setting over to production with a 2-week yield "
            "watch: flag any shift where first-pass yield drops below 93%.",
            "Use the best setting as the baseline for the second-source "
            "lamination film trial (NPI-2026-010).",
            "Close out the trial in the NPI log and file the DOE report with "
            "the manufacturing instructions.",
        ]
    else:
        next_steps = [
            "Hold scale-up until the conditional items above are closed out "
            "and the follow-up data is reviewed.",
            "Run the planned axial-point follow-up (trial NPI-2026-005) "
            "around the best setting to confirm the optimum is not on a "
            "boundary.",
            "Do not lock the best setting into the manufacturing "
            "instructions until the axial follow-up confirms it.",
            "Keep production on the current approved settings and track "
            "first-pass yield weekly against the 93% floor in the meantime.",
            "Hold the second-source lamination film trial (NPI-2026-010) "
            "until the DOE best setting is confirmed.",
        ]

    lines = [
        "# NPI Trial Report — Trial NPI-2026-004",
        "",
        "2^3 full-factorial DOE: lamination temperature x line speed x cure "
        "time, with 4 center points and 2 replicates (20 runs total, "
        "randomized run order, seed 42).",
        "",
        "> **Synthetic data disclaimer:** all data in this report was "
        "generated synthetically for a portfolio project. It is not Tesla "
        "production data and must not be used for real process decisions.",
        "",
        f"## Recommendation: {res['decision']}",
        "",
        res["rationale"],
        "",
        "## Design summary",
        "",
        "| Factor | Low (-1) | Center (0) | High (+1) | Unit |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key, spec in FACTORS.items():
        lines.append(f"| {spec['name']} ({key}) | {spec['low']} | "
                     f"{spec['center']} | {spec['high']} | {spec['unit']} |")
    lines += [
        "",
        "- Runs: 8 corner treatments x 2 replicates + 4 center points = 20 runs",
        f"- Responses: first-pass yield (%) and defect count per {UNITS_PER_RUN} units",
        f"- Overall mean yield: {res['runs']['yield_pct'].mean():.2f}% "
        f"(factorial mean {res['mean_factorial']:.2f}%, center mean "
        f"{res['mean_center']:.2f}%)",
        f"- Model R² (factorial runs): {res['r_squared']:.3f}",
        "",
        "## Effects (Yates algorithm)",
        "",
        "Effect = change in first-pass yield when the factor moves from its "
        "low (-1) to high (+1) level. Significance at alpha = 0.05.",
        "",
        _md_table(effects[["Effect", "Estimate", "SE", "t", "p", "Significant"]]),
        "",
        f"Significant effects: {', '.join(sig) if sig else 'none'}.",
        "",
        "## ANOVA (first-pass yield)",
        "",
        _md_table(anova[["Source", "SS", "df", "MS", "F", "p"]]),
        "",
        f"Pure-error df = {res['df_error']}, MS error = "
        f"{res['ms_error']:.3f}. Curvature p = {res['curvature_p']:.4f}.",
        "",
        "## Predicted best setting",
        "",
        f"- Lamination temperature: {best_actual['A']:.0f} degC "
        f"({'High (+1)' if a == 1 else 'Low (-1)'})",
        f"- Line speed: {best_actual['B']:.0f} m/min "
        f"({'High (+1)' if b == 1 else 'Low (-1)'})",
        f"- Cure time: {best_actual['C']:.0f} min "
        f"({'High (+1)' if c == 1 else 'Low (-1)'})",
        f"- Predicted first-pass yield: **{res['best_yield']:.2f}%**",
        f"- Predicted defects per {UNITS_PER_RUN} units: "
        f"**{res['best_defects']:.1f}**",
        "",
        "## Charts",
        "",
        "![Effect Pareto](effect_pareto.png)",
        "![Main effects](main_effects.png)",
        "![Interaction plot](interaction_plot.png)",
        "![Observed vs predicted](observed_vs_predicted.png)",
        "",
        "## Next steps",
        "",
    ]
    lines += [f"{i + 1}. {step}" for i, step in enumerate(next_steps)]
    lines += ["",
              "## Data",
              "",
              "- `data/doe_runs.csv` — one row per DOE run (run order, coded "
              "and actual factor levels, yield, defect count).",
              "- `data/trial_log.csv` — NPI trial log (trial ID, date, line, "
              "engineer, objective, status, observations).",
              "- Reproduce with: `python npi_doe.py --generate` then "
              "`python npi_doe.py --analyze`.",
              ""]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_MD


# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------

def run_analysis() -> dict:
    """Load data, run the DOE analysis, save charts and the report."""
    runs, _ = load_data()
    res = analyze_doe(runs)
    paths = [chart_effect_pareto(res["effects"], res["se_effect"], res["t_crit"]),
             chart_main_effects(res["corners"]),
             chart_interactions(res["corners"]),
             chart_observed_vs_predicted(res["runs"], res["r_squared"])]
    report = write_report(res)
    print("\nDOE analysis complete (trial NPI-2026-004):")
    print(res["effects"][["Effect", "Estimate", "p", "Significant"]]
          .to_string(index=False))
    a, b, c = res["best"]
    print(f"\nPredicted best setting: Temp "
          f"{_actual_level('A', a):.0f} degC, Speed "
          f"{_actual_level('B', b):.0f} m/min, Cure "
          f"{_actual_level('C', c):.0f} min")
    print(f"Predicted first-pass yield: {res['best_yield']:.2f}% "
          f"(predicted defects: {res['best_defects']:.1f} per "
          f"{UNITS_PER_RUN} units)")
    print(f"Recommendation: {res['decision']}")
    for p in paths:
        print(f"  chart: {p}")
    print(f"  report: {report}")
    return res


def print_trials() -> None:
    """Print a summary of the NPI trial log."""
    _, trials = load_data()
    print(f"\nNPI trial log: {len(trials)} trials")
    print(trials["status"].value_counts().to_string())
    print()
    cols = ["trial_id", "date", "line", "engineer", "objective", "status"]
    print(trials[cols].to_string(index=False))
    print()
    for _, row in trials.iterrows():
        print(f"{row['trial_id']} [{row['status']}]: {row['observations']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NPI Trial & DOE Analyzer — manage NPI trials and "
                    "analyze a 2^3 factorial DOE.")
    parser.add_argument("--generate", action="store_true",
                        help="Generate the synthetic DOE and trial-log data.")
    parser.add_argument("--analyze", action="store_true",
                        help="Run the DOE analysis and write charts + report.")
    parser.add_argument("--trials", action="store_true",
                        help="Print the NPI trial log summary.")
    args = parser.parse_args()

    if not (args.generate or args.analyze or args.trials):
        parser.print_help()
        return
    if args.generate:
        generate_data()
    if args.analyze:
        run_analysis()
    if args.trials:
        print_trials()


if __name__ == "__main__":
    main()
