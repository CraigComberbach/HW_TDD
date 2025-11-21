"""
spice_runner.py

Small wrapper around ngspice_con:
 * builds a temporary netlist by appending a .control block
 * runs ngspice_con -b
 * ensures wrdata CSV exists
 * returns a pandas DataFrame
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Union

import pandas as pd

PathLike = Union[str, Path]


def run_and_read_csv(
    base_netlist: PathLike,
    control_text: str,
    csv_name: str,
    tmp_dir: PathLike,
) -> pd.DataFrame:
    """
    base_netlist: Path to base .cir/.sp netlist with circuit only (no .control).
    control_text: Full .control ... .endc block (lines joined with \n).
    csv_name:     File name (not path) that wrdata will write (inside tmp_dir).
    tmp_dir:      Directory where temp netlist and CSV will live.

    Returns:
        pandas DataFrame containing wrdata output.
    """
    base_netlist = Path(base_netlist).resolve()
    tmp_dir = Path(tmp_dir).resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if not base_netlist.exists():
        raise FileNotFoundError(f"Base netlist not found: {base_netlist}")

    csv_path = tmp_dir / csv_name
    if csv_path.exists():
        csv_path.unlink()

    # Build temporary netlist that includes the control block
    with base_netlist.open("r", encoding="utf-8") as f:
        base_text = f.read()

    # Ensure base netlist ends with newline
    if not base_text.endswith("\n"):
        base_text += "\n"

    # Compose temp netlist
    tmp_netlist_fd, tmp_netlist_name = tempfile.mkstemp(
        prefix="ng_", suffix=".cir", dir=tmp_dir
    )
    tmp_netlist_path = Path(tmp_netlist_name)

    with open(tmp_netlist_path, "w", encoding="utf-8") as f:
        f.write(base_text)
        f.write("\n")
        f.write(control_text.strip())
        if not control_text.strip().endswith("\n"):
            f.write("\n")

    # Run ngspice_con in batch mode
    log_path = tmp_dir / (tmp_netlist_path.stem + ".log")

    cmd = [
        "ngspice_con",
        "-b",
        "-o",
        str(log_path),
        str(tmp_netlist_path),
    ]

    proc = subprocess.run(
        cmd,
        cwd=tmp_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"ngspice_con failed with code {proc.returncode}\n"
            f"Command: {' '.join(cmd)}\n"
            f"Output:\n{proc.stdout}"
        )

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Expected CSV {csv_path} not written. "
            f"Check your .control block and wrdata path."
        )

    # Pandas will happily parse the wr_vecnames header
    df = pd.read_csv(csv_path)

    return df
