# -*- coding: utf-8 -*-
"""Professional data-science national report figures and HTML assembly helpers.

Produces KDE / distribution suites, missingness profiles, thematic categorical
charts (fire, disease agents, env problems, tree condition), and a structured
methodology HTML section pack. Numbers come only from computed tables.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nfi_datascience import (
    apply_plot_style,
    missingness_report,
    plot_categorical_bars,
    plot_metric_distribution_suite,
    plot_missingness_profile,
    univariate_numeric,
)


def _esc(x: Any) -> str:
    import html
    return html.escape("" if x is None else str(x))


def _img_b64(path: Path | str | None, alt: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return f"<p class='note'>Missing figure: {_esc(alt)}</p>"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return (
        f'<figure class="fig"><img alt="{_esc(alt)}" src="data:image/png;base64,{b64}"/>'
        f"<figcaption>{_esc(alt)}</figcaption></figure>"
    )


def write_processing_flowchart(out_path: Path) -> Path:
    apply_plot_style()
    steps = [
        "1. Ingest cleansed national tables",
        "2. Attach SU_UID / PLOT_UID keys",
        "3. Coordinate QA (field vs DB)",
        "4. Anti-clip SU x 5 lattice",
        "5. Presence gates (trees / shrubs)",
        "6. Optional Area_H (Asir/Makkah)",
        "7. Exclude grass / Calotropis / palm",
        "8. Engineer BA, Vol, AGB, BGB, C",
        "9. Shrub allometric AGB / C",
        "10. Missingness + KDE EDA",
        "11. Thematic SU attributes",
        "12. Point + Voronoi + hex maps",
        "13. HTML report + atlas",
    ]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(steps) + 1)
    ax.axis("off")
    for i, s in enumerate(reversed(steps), start=1):
        y = i
        ax.add_patch(plt.Rectangle((0.12, y - 0.35), 0.76, 0.7, facecolor="#e8f5e9", edgecolor="#1b5e20", lw=1.2, zorder=2))
        ax.text(0.5, y, s, ha="center", va="center", fontsize=10, fontweight="600", zorder=3)
        if i < len(steps):
            ax.annotate("", xy=(0.5, y + 0.45), xytext=(0.5, y + 0.65),
                        arrowprops=dict(arrowstyle="->", color="#1b5e20", lw=1.4))
    ax.set_title("National geopipeline: data processing and engineering flow", fontsize=13, fontweight="bold", pad=8)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def write_thematic_bar_charts(tables: dict[str, pd.DataFrame], out_dir: Path) -> dict[str, Path]:
    """Categorical frequency charts for disturbance / health themes."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    trees = tables.get("trees")
    if trees is not None:
        for col, name in [
            ("overall_tree_condition_label", "tree_condition"),
            ("crown_condition_label", "crown_condition"),
            ("causative_agent_label[1]", "causative_agent"),
        ]:
            if col in trees.columns and trees[col].notna().any():
                p = out_dir / f"bar_{name}.png"
                plot_categorical_bars(trees, col, p, top_n=12, title=f"National trees: {col}")
                paths[name] = p
    fire = tables.get("fire")
    if fire is not None:
        for col, name in [("fire_evidence_label", "fire_evidence"), ("fir_type_label", "fire_type")]:
            if col in fire.columns and fire[col].notna().any():
                p = out_dir / f"bar_{name}.png"
                plot_categorical_bars(fire, col, p, top_n=10, title=f"National fire table: {col}")
                paths[name] = p
    env = tables.get("environmental_problems")
    if env is not None and "categories_label" in env.columns:
        p = out_dir / "bar_env_category.png"
        plot_categorical_bars(env, "categories_label", p, top_n=12, title="Environmental problem categories")
        paths["env_category"] = p
    return paths


def produce_national_ds_figures(
    *,
    tables: dict[str, pd.DataFrame],
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    out_root: Path,
    cfg: dict,
) -> dict[str, Any]:
    """Write DS figure pack under figures/national_ds/ and audit CSVs."""
    out_root = Path(out_root)
    fig_dir = out_root / "figures" / "national_ds"
    audit = out_root / "audit"
    fig_dir.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)

    trees = tables["trees"]
    shrubs = tables["shrubs"]
    flow = write_processing_flowchart(fig_dir / "processing_flowchart.png")

    miss_t = missingness_report(trees, "national_trees")
    miss_s = missingness_report(shrubs, "national_shrubs")
    miss_t.to_csv(audit / "missingness_national_trees.csv", index=False)
    miss_s.to_csv(audit / "missingness_national_shrubs.csv", index=False)
    miss_fig_t = plot_missingness_profile(
        df=trees, out_path=fig_dir / "missingness_trees.png", source_label="national_trees",
    )
    miss_fig_s = plot_missingness_profile(
        df=shrubs, out_path=fig_dir / "missingness_shrubs.png", source_label="national_shrubs",
    )

    dbh = cfg["columns"]["dbh"]
    ht = cfg["columns"]["height"]
    raw_paths = plot_metric_distribution_suite(
        trees, [c for c in [dbh, ht] if c in trees.columns], fig_dir / "kde_raw", prefix="raw"
    )
    tree_fv_cols = [c for c in ["basal_area_m2", "volume_m3", "agb_mg", "bgb_mg", "carbon_mg_provisional", "co2eq_mg_provisional"] if c in tree_m.columns]
    fv_paths = plot_metric_distribution_suite(tree_m, tree_fv_cols, fig_dir / "kde_trees_fv", prefix="tree_fv")
    shrub_cols = [c for c in ["mean_CD_m", "height_cm", "agb_mg", "carbon_mg_provisional"] if c in shrub_m.columns]
    shrub_paths = plot_metric_distribution_suite(shrub_m, shrub_cols, fig_dir / "kde_shrubs", prefix="shrub")

    theme_bars = write_thematic_bar_charts(tables, fig_dir / "thematic_bars")

    # Causative-agent summary table (computed)
    agent_col = "causative_agent_label[1]"
    agent_tbl = pd.DataFrame()
    if agent_col in trees.columns:
        vc = trees[agent_col].astype(str).replace({"nan": pd.NA}).dropna().value_counts().rename("n").reset_index()
        vc.columns = ["causative_agent_label", "n"]
        vc["pct_of_non_null"] = (100 * vc["n"] / vc["n"].sum()).round(2)
        agent_tbl = vc
        agent_tbl.to_csv(audit / "causative_agent_frequency.csv", index=False)

    fire_tbl = pd.DataFrame()
    if "fire" in tables and "fire_evidence_label" in tables["fire"].columns:
        vc = tables["fire"]["fire_evidence_label"].astype(str).replace({"nan": pd.NA}).dropna().value_counts().rename("n").reset_index()
        vc.columns = ["fire_evidence_label", "n"]
        fire_tbl = vc
        fire_tbl.to_csv(audit / "fire_evidence_frequency.csv", index=False)

    env_tbl = pd.DataFrame()
    if "environmental_problems" in tables and "categories_label" in tables["environmental_problems"].columns:
        vc = tables["environmental_problems"]["categories_label"].astype(str).replace({"nan": pd.NA}).dropna().value_counts().rename("n").reset_index()
        vc.columns = ["categories_label", "n"]
        env_tbl = vc
        env_tbl.to_csv(audit / "env_problem_frequency.csv", index=False)

    return {
        "flowchart": flow,
        "missingness_trees": Path(miss_fig_t) if miss_fig_t else None,
        "missingness_shrubs": Path(miss_fig_s) if miss_fig_s else None,
        "kde_raw": raw_paths,
        "kde_trees_fv": fv_paths,
        "kde_shrubs": shrub_paths,
        "theme_bars": theme_bars,
        "agent_tbl": agent_tbl,
        "fire_tbl": fire_tbl,
        "env_tbl": env_tbl,
        "uni_trees": univariate_numeric(tree_m, tree_fv_cols),
        "uni_shrubs": univariate_numeric(shrub_m, shrub_cols),
        "miss_trees": miss_t,
        "miss_shrubs": miss_s,
    }
