"""
stress_check.py

Evaluate generic stress metrics from a wrdata CSV and schematic metadata.

check_stress(df, schem, stress_rules, dut="VoltageDivider") -> list[str]

Each message:
  "<SEVERITY>: <ref> <metric> measured=<val> limit=<limit> at t=<time>"
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yaml

from .kicad_meta import SchematicMeta, SymbolMeta, parse_number_with_unit


def load_stress_rules(path: Path) -> Dict:
    path = Path(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _limit_for_metric(
    sym: SymbolMeta, metric_cfg: Dict
) -> Optional[float]:
    field_name = metric_cfg.get("field")
    default_str = metric_cfg.get("default")
    if field_name:
        val = sym.field_f(field_name)
        if val is not None:
            return val
    if default_str:
        try:
            return parse_number_with_unit(str(default_str))
        except Exception:
            return None
    return None


def _find_time_column(df: pd.DataFrame) -> Optional[str]:
    for cand in ("time", "Time", "t"):
        if cand in df.columns:
            return cand
    # AC: possibly 'frequency'
    for cand in ("frequency", "Frequency"):
        if cand in df.columns:
            return cand
    return None


def _max_abs(series: pd.Series) -> float:
    return float(series.abs().max())


def check_stress(
    df: pd.DataFrame,
    schem: SchematicMeta,
    stress_rules: Dict,
    dut: str,
) -> List[str]:
    msgs: List[str] = []

    tcol = _find_time_column(df)
    tvals = df[tcol] if tcol and tcol in df.columns else None

    for sym in schem.symbols_for_dut(dut):
        kind = sym.kind
        rule = stress_rules.get(kind)
        if not rule:
            continue
        metrics = rule.get("metrics", {})
        for metric_name, metric_cfg in metrics.items():
            limit = _limit_for_metric(sym, metric_cfg)
            if limit is None or limit <= 0:
                continue  # nothing to check

            measured, t_at = _eval_metric(df, sym, metric_name, tvals)
            if measured is None:
                continue

            if measured > limit:
                sev = str(metric_cfg.get("severity", "warn")).upper()
                ref = sym.ref
                msg = (
                    f"{sev}: {ref} {metric_name} measured={measured:g} "
                    f"limit={limit:g}"
                )
                if t_at is not None:
                    msg += f" at t={t_at:g}"
                msgs.append(msg)

    return msgs


def _eval_metric(
    df: pd.DataFrame,
    sym: SymbolMeta,
    metric_name: str,
    tvals: Optional[pd.Series],
) -> (Optional[float], Optional[float]):
    ref = sym.ref
    k = sym.kind

    if metric_name == "power" and k == "resistor":
        col_i = f"@{ref}[i]"
        if col_i not in df.columns:
            return None, None
        series_i = df[col_i]
        try:
            r = parse_number_with_unit(sym.value)
        except Exception:
            return None, None
        series_p = (series_i ** 2) * r
        idx = series_p.abs().idxmax()
        p_max = float(series_p.iloc[idx])
        t_at = float(tvals.iloc[idx]) if tvals is not None else None
        return abs(p_max), t_at

    if metric_name == "voltage" and k in ("capacitor", "diode"):
        if k == "capacitor":
            col_v = f"@{ref}[v]"
        else:  # diode
            col_v = f"@{ref}[vd]"
        if col_v not in df.columns:
            return None, None
        series = df[col_v]
        idx = series.abs().idxmax()
        v_max = float(series.iloc[idx])
        t_at = float(tvals.iloc[idx]) if tvals is not None else None
        return abs(v_max), t_at

    if metric_name == "current" and k in ("inductor", "diode", "mosfet"):
        if k == "inductor":
            col_i = f"@{ref}[i]"
        elif k == "diode":
            col_i = f"@{ref}[id]"
        else:  # mosfet
            col_i = f"@{ref}[id]"
        if col_i not in df.columns:
            return None, None
        series = df[col_i]
        idx = series.abs().idxmax()
        i_max = float(series.iloc[idx])
        t_at = float(tvals.iloc[idx]) if tvals is not None else None
        return abs(i_max), t_at

    if metric_name == "vds" and k == "mosfet":
        col_vds = f"@{ref}[vds]"
        if col_vds not in df.columns:
            return None, None
        series = df[col_vds]
        idx = series.abs().idxmax()
        vds_max = float(series.iloc[idx])
        t_at = float(tvals.iloc[idx]) if tvals is not None else None
        return abs(vds_max), t_at

    return None, None
