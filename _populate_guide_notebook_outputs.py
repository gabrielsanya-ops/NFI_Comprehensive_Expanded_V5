# -*- coding: utf-8 -*-
"""Rebuild guide notebook and inject saved figure/table outputs so the .ipynb shows results."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs_national_v5"
NB = ROOT / "NFI_National_GeoPipeline_Guide_V5.ipynb"


def _img_output(path: Path) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "output_type": "display_data",
        "data": {"image/png": data, "text/plain": [path.name + "\n"]},
        "metadata": {},
    }


def _html_output(html: str) -> dict:
    return {
        "output_type": "display_data",
        "data": {"text/html": [html], "text/plain": ["<IPython.core.display.HTML object>\n"]},
        "metadata": {},
    }


def _md_output(text: str) -> dict:
    return {
        "output_type": "display_data",
        "data": {"text/markdown": [text], "text/plain": [text]},
        "metadata": {},
    }


def _df_output(df: pd.DataFrame, title: str) -> list[dict]:
    if df is None or len(df) == 0:
        return [_md_output(f"**{title}** (no rows)")]
    html = df.head(30).to_html(index=False, border=0)
    return [_md_output(f"### {title}"), _html_output(html)]


def ensure_products() -> None:
    report = OUT / "documents" / "NFI_national_geopipeline_report.html"
    figs_ok = (OUT / "figures" / "national_eda" / "univariate_trees_fv_national.png").exists()
    if report.exists() and figs_ok:
        # Refresh methodology report from current artefacts
        sys.path.insert(0, str(ROOT / "src"))
        from nfi_national_html import write_national_html_report

        summary = json.loads((OUT / "logs" / "national_run_summary.json").read_text(encoding="utf-8"))
        by_region = pd.read_csv(OUT / "audit" / "national_su_by_region.csv")
        ancillary = pd.read_csv(OUT / "audit" / "national_ancillary_pools.csv")
        area = pd.read_csv(OUT / "audit" / "national_area_coverage.csv") if (OUT / "audit" / "national_area_coverage.csv").exists() else None
        fig_dir = OUT / "figures" / "national_eda"
        map_dir = OUT / "maps" / "national"
        fig_paths = {p.stem: p for p in fig_dir.glob("*.png")}
        map_paths = {p.stem: p for p in map_dir.glob("*.png")}
        interactive = {
            p.stem.replace("interactive_national_", ""): str(p)
            for p in (OUT / "maps" / "html_interactive").glob("interactive_national_*.html")
        }
        write_national_html_report(
            out_path=report,
            run_summary=summary,
            by_region=by_region,
            ancillary=ancillary,
            area_cov=area,
            gate=summary.get("gate_tree_presence"),
            gate_shrub=summary.get("gate_shrub_presence"),
            fig_paths=fig_paths,
            map_paths=map_paths,
            interactive_paths=interactive,
            atlas_index=OUT / "maps" / "html_atlas" / "index.html",
            assumptions=summary.get("assumptions"),
            uni_trees=pd.read_csv(OUT / "audit" / "univariate_national_trees_fv.csv") if (OUT / "audit" / "univariate_national_trees_fv.csv").exists() else None,
            uni_shrubs=pd.read_csv(OUT / "audit" / "univariate_national_shrubs_fv.csv") if (OUT / "audit" / "univariate_national_shrubs_fv.csv").exists() else None,
            biv_spearman=pd.read_csv(fig_dir / "bivariate_spearman_trees_national.csv") if (fig_dir / "bivariate_spearman_trees_national.csv").exists() else None,
            biv_pearson=pd.read_csv(fig_dir / "bivariate_pearson_trees_national.csv") if (fig_dir / "bivariate_pearson_trees_national.csv").exists() else None,
        )
        print("Refreshed HTML report:", report)
        return
    print("Running national pipeline to create products...")
    subprocess.check_call([sys.executable, str(ROOT / "run_national_pipeline.py")], cwd=str(ROOT))


def inject_outputs(nb: dict) -> None:
    eda = OUT / "figures" / "national_eda"
    report = OUT / "documents" / "NFI_national_geopipeline_report.html"
    atlas = OUT / "maps" / "html_atlas" / "index.html"

    uni_t = pd.read_csv(OUT / "audit" / "univariate_national_trees_fv.csv") if (OUT / "audit" / "univariate_national_trees_fv.csv").exists() else pd.DataFrame()
    uni_s = pd.read_csv(OUT / "audit" / "univariate_national_shrubs_fv.csv") if (OUT / "audit" / "univariate_national_shrubs_fv.csv").exists() else pd.DataFrame()
    biv_s = pd.read_csv(eda / "bivariate_spearman_trees_national.csv") if (eda / "bivariate_spearman_trees_national.csv").exists() else pd.DataFrame()
    biv_p = pd.read_csv(eda / "bivariate_pearson_trees_national.csv") if (eda / "bivariate_pearson_trees_national.csv").exists() else pd.DataFrame()

    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        # Section 12 uni/biv cell
        if "write_national_eda_figures" in src and "BIV_S" in src:
            outs = []
            outs += _df_output(uni_t, "Univariate · trees (provisional FV)")
            outs += _df_output(uni_s, "Univariate · shrubs (provisional)")
            outs += _df_output(biv_s, "Bivariate · Spearman (trees)")
            outs += _df_output(biv_p, "Bivariate · Pearson (trees)")
            outs.append(_md_output("### Univariate and bivariate figures"))
            for name in [
                "univariate_trees_national.png",
                "univariate_trees_fv_national.png",
                "bivariate_corr_pair_trees_national.png",
                "univariate_shrubs_national.png",
            ]:
                p = eda / name
                if p.exists():
                    outs.append(_md_output(f"**{name}**"))
                    outs.append(_img_output(p))
            cell["outputs"] = outs
            cell["execution_count"] = 1
        # Deliverables cell
        if "Open these HTML deliverables" in src or ("REPORT_PATH" in src and "ATLAS_INDEX" in src and "rerun display" in src):
            outs = [_md_output("### Univariate / bivariate figures (rerun display)")]
            for name in [
                "univariate_trees_national.png",
                "univariate_trees_fv_national.png",
                "bivariate_corr_pair_trees_national.png",
                "univariate_shrubs_national.png",
            ]:
                p = eda / name
                if p.exists():
                    outs.append(_md_output(f"**{name}**"))
                    outs.append(_img_output(p))
            buttons = [
                f'<p><a style="display:inline-block;padding:10px 14px;background:#14351c;color:#fff;text-decoration:none;'
                f'border-radius:8px;font-weight:600;margin:6px 0" href="{report.as_uri()}" target="_blank">'
                f'Methodology + results HTML report</a><br/><code>{report}</code></p>',
                f'<p><a style="display:inline-block;padding:10px 14px;background:#14351c;color:#fff;text-decoration:none;'
                f'border-radius:8px;font-weight:600;margin:6px 0" href="{atlas.as_uri()}" target="_blank">'
                f'Interactive map atlas (Leaflet portal)</a><br/><code>{atlas}</code></p>',
            ]
            for p in sorted((OUT / "maps" / "html_interactive").glob("interactive_national_*.html")):
                label = p.stem.replace("interactive_national_", "Interactive map · ")
                buttons.append(
                    f'<p><a style="display:inline-block;padding:10px 14px;background:#fff;color:#14351c;border:1px solid #d5ddd7;'
                    f'text-decoration:none;border-radius:8px;font-weight:600;margin:6px 0" href="{p.as_uri()}" target="_blank">'
                    f'{label}</a><br/><code>{p}</code></p>'
                )
            outs.append(_html_output(
                '<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif">'
                '<h3 style="color:#1b5e20">Open these HTML deliverables</h3>'
                + "".join(buttons) + "</div>"
            ))
            cell["outputs"] = outs
            cell["execution_count"] = 1


def main() -> None:
    subprocess.check_call([sys.executable, str(ROOT / "_build_national_guide_notebook.py")], cwd=str(ROOT))
    ensure_products()
    nb = json.loads(NB.read_text(encoding="utf-8"))
    inject_outputs(nb)
    NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Wrote notebook with saved outputs:", NB)


if __name__ == "__main__":
    main()
