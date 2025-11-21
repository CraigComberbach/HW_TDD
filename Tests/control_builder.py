"""
control_builder.py

Builds an ngspice .control block for a given DUT, interface, analysis, and corner.

Responsibilities:
 * Emit .param overrides from schematic tolerances (min/nom/max)
 * Emit the chosen analysis (tran/ac/dc)
 * Emit .save list
 * Emit wrdata with interface rails and auto stress vectors
 * Set wr_singlescale and wr_vecnames to make CSVs robust
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from .kicad_meta import SchematicMeta, SymbolMeta


def _value_with_tol(symbol: SymbolMeta, corner: Dict[str, float]) -> float:
    """
    Apply tolerance to the nominal 'Value' field based on Tol and corner's tol_sign.
    Only resistors + capacitors are handled here as an example.
    """
    from .kicad_meta import parse_number_with_unit

    try:
        base = parse_number_with_unit(symbol.value)
    except Exception:
        return None  # we will skip if can't parse

    tol = symbol.field_f("Tol") or 0.0
    tol_sign = float(corner.get("tol_sign", 0.0))
    return base * (1.0 + tol_sign * tol)


def _param_name_for_symbol(symbol: SymbolMeta) -> str:
    """
    Choose a SPICE parameter name for this symbol.
    Prefer user field 'Param', else derive from ref.
    """
    param = symbol.fields.get("Param")
    if param:
        return param
    # fallback: R_R1, C_C1, etc.
    return f"{symbol.ref[0].upper()}_{symbol.ref}"


def _build_param_lines(
    schem: SchematicMeta, dut: str, corner: Dict[str, float]
) -> List[str]:
    lines: List[str] = []
    for sym in schem.symbols_for_dut(dut):
        if sym.kind not in ("resistor", "capacitor", "inductor"):
            continue
        val = _value_with_tol(sym, corner)
        if val is None:
            continue
        pname = _param_name_for_symbol(sym)
        lines.append(f".param {pname} = {val:g}")
    return lines


def _analysis_lines(analysis: Dict[str, str]) -> List[str]:
    t = analysis.get("type", "tran").lower()
    lines: List[str] = []
    if t == "tran":
        tstep = analysis.get("tstep", "1u")
        tstop = analysis.get("tstop", "1m")
        tstart = analysis.get("tstart", "0")
        uic = analysis.get("uic", False)
        cmd = f"tran {tstep} {tstop} {tstart}"
        if uic:
            cmd += " uic"
        lines.append(cmd)
    elif t == "ac":
        ac_type = analysis.get("ac_type", "dec")
        npts = analysis.get("npts", "100")
        fstart = analysis.get("fstart", "10")
        fstop = analysis.get("fstop", "1Meg")
        lines.append(f"ac {ac_type} {npts} {fstart} {fstop}")
    elif t == "dc":
        # very generic; user must supply source name and range
        src = analysis["src"]  # required
        start = analysis.get("start", "0")
        stop = analysis.get("stop", "5")
        step = analysis.get("step", "0.1")
        lines.append(f"dc {src} {start} {stop} {step}")
    else:
        raise ValueError(f"Unknown analysis type: {t}")
    return lines


def _interface_vectors(iface: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """
    Given interface mapping, e.g.
        {"vin": "VIN", "vout": "VOUT", "gnd": "0"}
    return (save_list, data_list) with SPICE vector names.
    """
    save: List[str] = []
    data: List[str] = []

    # Always include time / frequency
    save.append("all")  # keep simple; wr_singlescale will keep time aligned

    for label_name, net in iface.items():
        # For now we only support voltages
        vec = f"v({net})"
        save.append(vec)
        data.append(vec)

    return save, data


def _stress_vectors_for_symbol(sym: SymbolMeta) -> List[str]:
    """
    Auto-generate SPICE vectors to record for stress checks.

    We rely on ngspice device parameters:
      @R1[i], @C1[v], @L1[i], @D1[id], @D1[vd], @M1[id], @M1[vds], etc.
    """
    ref = sym.ref
    k = sym.kind
    vecs: List[str] = []

    if k == "resistor":
        vecs.append(f"@{ref}[i]")
    elif k == "capacitor":
        vecs.append(f"@{ref}[v]")
    elif k == "inductor":
        vecs.append(f"@{ref}[i]")
    elif k == "diode":
        vecs.append(f"@{ref}[id]")
        vecs.append(f"@{ref}[vd]")
    elif k == "mosfet":
        vecs.append(f"@{ref}[id]")
        vecs.append(f"@{ref}[vds]")
    # 'ic' and others could be added as needed
    return vecs


def _stress_vectors(schem: SchematicMeta, dut: str) -> List[str]:
    vecs: List[str] = []
    for sym in schem.symbols_for_dut(dut):
        vecs.extend(_stress_vectors_for_symbol(sym))
    # remove duplicates while preserving order
    seen = set()
    uniq: List[str] = []
    for v in vecs:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def build_control_block(
    iface: Dict[str, str],
    analysis: Dict[str, str],
    dut: str,
    corner: Dict[str, float],
    schem: SchematicMeta,
    outdir: Path,
) -> Tuple[str, str]:
    """
    Build a complete .control block and the CSV file name.

    iface   : mapping of logical interface names -> net names (VIN, VOUT, etc.)
    analysis: dict describing tran/ac/dc run.
    dut     : DUT name (must match 'DUT' field in schematic symbols).
    corner  : one dict from corners_from_tolerances([...]).
    schem   : SchematicMeta instance.
    outdir  : directory where CSV will be written.

    Returns:
        (control_block_text, csv_filename)
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    corner_name = corner.get("name", "nom")
    csv_name = f"{dut}_{corner_name}.csv"
    csv_path = outdir / csv_name

    param_lines = _build_param_lines(schem, dut, corner)
    analysis_lines = _analysis_lines(analysis)

    save_if, data_if = _interface_vectors(iface)
    stress_vecs = _stress_vectors(schem, dut)
    data_vecs = data_if + stress_vecs

    control_lines: List[str] = []
    control_lines.append(".control")
    control_lines.append("set wr_singlescale")
    control_lines.append("set wr_vecnames")
    control_lines.extend(param_lines)
    control_lines.extend(analysis_lines)

    # Explicit .save is optional but keeps files smaller if desired
    # Here we use 'all' for robustness and rely on wrdata selection.
    # control_lines.append(".save " + " ".join(save_if + stress_vecs))

    # wrdata path must be quoted if it contains spaces
    control_lines.append(
        f"wrdata \"{csv_path}\" " + " ".join(data_vecs)
    )
    control_lines.append("quit")
    control_lines.append(".endc")

    return "\n".join(control_lines) + "\n", csv_name
