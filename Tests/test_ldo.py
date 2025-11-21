from pathlib import Path

import numpy as np

from .spice_runner import run_and_read_csv
from .kicad_meta import load_schematic, corners_from_tolerances
from .control_builder import build_control_block
from .stress_check import load_stress_rules, check_stress

ROOT = Path(__file__).resolve().parents[1]


def _steady_state_window(df, frac_start=0.6, frac_end=0.9):
    n = len(df)
    i0 = int(n * frac_start)
    i1 = int(n * frac_end)
    return slice(i0, i1)


def test_ldo_startup_overshoot_lt_100mV():
    """
    Startup overshoot: VOUT should not exceed 3.4V (3.3V + 0.1V).
    """
    schem = load_schematic(ROOT / "projects" / "LDO" / "LDO.kicad_sch")
    stress_rules = load_stress_rules(ROOT / "rules" / "stress_rules.yaml")
    corners = corners_from_tolerances(["nom"])  # only nominal corner for now

    iface = {"vin": "IN", "vout": "VOUT", "gnd": "0"}
    analysis = {"type": "tran", "tstep": "100u", "tstop": "20m"}

    base_netlist = ROOT / "netlists" / "ldo_example.cir"
    outdir = ROOT / "out"

    for corner in corners:
        control, csv_name = build_control_block(
            iface=iface,
            analysis=analysis,
            dut="LDO",
            corner=corner,
            schem=schem,
            outdir=outdir,
        )

        df = run_and_read_csv(
            base_netlist=base_netlist,
            control_text=control,
            csv_name=csv_name,
            tmp_dir=outdir,
        )

        vout = df["v(VOUT)"].to_numpy()
        max_vout = float(np.max(vout))
        assert max_vout <= 3.4, f"Startup overshoot too high: {max_vout:.3f} V"

        msgs = check_stress(df, schem, stress_rules, dut="LDO")
        errors = [m for m in msgs if m.startswith("ERROR")]
        assert not errors, "Stress violations:\n" + "\n".join(errors)


def test_ldo_ripple_lt_30mVpp():
    """
    Ripple at steady state: VOUT peak-to-peak should be < 30mV.
    """
    schem = load_schematic(ROOT / "projects" / "LDO" / "LDO.kicad_sch")
    stress_rules = load_stress_rules(ROOT / "rules" / "stress_rules.yaml")
    corners = corners_from_tolerances(["nom"])

    iface = {"vin": "IN", "vout": "VOUT", "gnd": "0"}
    analysis = {"type": "tran", "tstep": "100u", "tstop": "50m"}

    base_netlist = ROOT / "netlists" / "ldo_example.cir"
    outdir = ROOT / "out"

    for corner in corners:
        control, csv_name = build_control_block(
            iface=iface,
            analysis=analysis,
            dut="LDO",
            corner=corner,
            schem=schem,
            outdir=outdir,
        )

        df = run_and_read_csv(
            base_netlist=base_netlist,
            control_text=control,
            csv_name=csv_name,
            tmp_dir=outdir,
        )

        vout = df["v(VOUT)"].to_numpy()
        win = _steady_state_window(df)
        vwin = vout[win]
        ripple_pp = float(vwin.max() - vwin.min())
        assert ripple_pp < 0.03, f"Ripple too high: {ripple_pp*1e3:.1f} mVpp"

        msgs = check_stress(df, schem, stress_rules, dut="LDO")
        errors = [m for m in msgs if m.startswith("ERROR")]
        assert not errors, "Stress violations:\n" + "\n".join(errors)
