from pathlib import Path
from .spice_runner import run_and_read_csv
from .kicad_meta import load_schematic, corners_from_tolerances
from .control_builder import build_control_block
from .stress_check import load_stress_rules, check_stress

ROOT = Path(__file__).resolve().parents[1]

def test_mydut_behavior():
    schem = load_schematic(ROOT / "projects" / "MyDUT" / "MyDUT.kicad_sch")
    stress_rules = load_stress_rules(ROOT / "rules" / "stress_rules.yaml")
    corners = corners_from_tolerances(["nom"])  # or ["min","nom","max"]

    iface = {"vin": "VIN", "vout": "VOUT", "gnd": "0"}
    analysis = {"type": "tran", "tstep": "10u", "tstop": "10m"}

    for corner in corners:
        control, csv_name = build_control_block(
            iface=iface,
            analysis=analysis,
            dut="MyDUT",
            corner=corner,
            schem=schem,
            outdir=ROOT / "out"
        )
        df = run_and_read_csv(
            base_netlist=ROOT / "netlists" / "mydut.cir",
            control_text=control,
            csv_name=csv_name,
            tmp_dir=ROOT / "out"
        )

        # Your asserts here...
        # assert ...

        msgs = check_stress(df, schem, stress_rules, dut="MyDUT")
        assert not any(m.startswith("ERROR") for m in msgs), "\n".join(msgs)
