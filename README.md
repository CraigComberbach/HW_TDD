# SPICE CI Harness for KiCad + ngspice (Windows, local-first)

This repo is a minimal example of a **unit-test style** SPICE harness:

* **Simulator**: `ngspice_con` (batch console).
* **Schematics**: KiCad 8/9 `.kicad_sch` (S-expression).
* **Tests**: `pytest`, one behavior per test, treating circuits like unit tests.
* **Stress rules**: global `rules/stress_rules.yaml` controlling generic checks.

Key ideas:

1. **Tests specify only interfaces + analysis.**  
   Tests know about rails/ports like `VIN`, `VOUT`, `GND` and what analysis to run (`tran`, `ac`, `dc`).  
   They do **not** name internal refdes.

2. **Ratings & tolerances from schematics.**  
   Symbol fields like `Tol`, `Vmax`, `Imax`, `Pmax`, etc. are read from KiCad schematics and used to build deterministic corners and stress limits.

3. **Deterministic corners, no Monte Carlo.**  
   Corners are derived from tolerances as min/nom/max scaling, so runs are repeatable.

4. **Global stress rules.**  
   `rules/stress_rules.yaml` defines generic checks per component type. Tightening rules makes older designs move from pass → marginal → fail without touching tests.

5. **Robust CSV I/O.**  
   SPICE output is written using `.control` + `wrdata` with `wr_singlescale` and `wr_vecnames`. Python parses CSV via pandas; tests never scrape logs.

6. **Local now, CI-ready later.**  
   All paths are relative; `scripts/run_tests.ps1` uses `python -m venv`, `python -m pip`, and `python -m pytest` so it’s easy to drop into GitHub Actions.

## Quick start (Windows)

1. Install:
   * KiCad 8/9
   * ngspice with `ngspice_con` on your `PATH`
   * Python 3.10+ (64-bit)

2. Clone this repo and run:

   ```powershell
   .\scripts\run_tests.ps1
