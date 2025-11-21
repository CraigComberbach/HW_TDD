from pathlib import Path

import numpy as np

from .spice_runner import run_and_read_csv
from .kicad_meta import load_schematic, corners_from_tolerances
from .control_builder import build_control_block
from .stress_check import load_stress_rules, check_stress

ROOT = Path(__file__).resolve().parents[1]


def test_divider_gain_half():
    """
    Verify that Vout ≈ 0.5*Vin within schematic tolerance,
    and that resistor power ratings are not exceeded.
    """
    schem = load_schematic(ROOT / "projects" / "VoltageDivider" / "VoltageDivider.kicad_sch")
    stress_rules = load_stress_rules(ROOT / "rules" / "stress_rules.yaml")
    corners = corners_from_tolerances(["min", "nom", "max"])

    iface = {"vin": "VIN", "vout": "VOUT", "gnd": "0"}
    analysis = {"type": "tran", "tstep": "100u", "tstop": "10m"}

    base_netlist = ROOT / "netlists" / "voltage_divider.cir"
    outdir = ROOT / "out"

    for corner in corners:
        control, csv_name = build_control_block(
            iface=iface,
            analysis=analysis,
            dut="VoltageDivider",
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

        vin = df["v(VIN)"].to_numpy()
        vout = df["v(VOUT)"].to_numpy()

        ratio = vout / np.maximum(vin, 1e-12)
        # Expect ~0.5 gain; allow 5% window for this simple demo
        assert np.allclose(ratio[-1], 0.5, rtol=0.05), f"Unexpected gain: {ratio[-1]:.3f}"

        msgs = check_stress(df, schem, stress_rules, dut="VoltageDivider")
        errors = [m for m in msgs if m.startswith("ERROR")]
        assert not errors, "Stress violations:\n" + "\n".join(errors)
