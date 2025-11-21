"""
kicad_meta.py

Very lightweight KiCad 8/9 .kicad_sch parser for:

 * global / intersheet labels
 * per-symbol fields (Tol, Vmax, Imax, Pmax, DUT, Param, etc.)
 * basic DUT selection via symbol field 'DUT'

NOTE: This is deliberately minimal and aims only at the pieces needed for
this harness. It treats the schematic file as an S-expression and walks
it as nested Python lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ---------- S-expression parsing ----------

TOKEN_RE = re.compile(r'''\s*(
    ;[^\n]*           |   # comments
    "([^"\\]|\\.)*"   |   # quoted strings
    [()]              |   # parens
    [^\s()"]+             # atoms
)''', re.VERBOSE)


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for m in TOKEN_RE.finditer(text):
        tok = m.group(1)
        if tok.startswith(";"):
            continue  # comment
        tokens.append(tok)
    return tokens


def _parse_tokens(tokens: List[str], idx: int = 0) -> (Any, int):
    if idx >= len(tokens):
        raise ValueError("Unexpected EOF while parsing")
    tok = tokens[idx]
    if tok == "(":
        lst: List[Any] = []
        idx += 1
        while idx < len(tokens) and tokens[idx] != ")":
            node, idx = _parse_tokens(tokens, idx)
            lst.append(node)
        if idx >= len(tokens):
            raise ValueError("Missing ')'")
        return lst, idx + 1
    elif tok == ")":
        raise ValueError("Unexpected ')'")
    else:
        # Strip quotes if present
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1], idx + 1
        return tok, idx + 1


def parse_sexpr(text: str) -> Any:
    tokens = _tokenize(text)
    root, idx = _parse_tokens(tokens, 0)
    if idx != len(tokens):
        # Best-effort: ignore trailing tokens
        pass
    return root


# ---------- Value / unit parsing ----------

PREFIXES = {
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
}


def parse_number_with_unit(s: str) -> float:
    """
    Very small helper to parse things like:
        '10', '10k', '10 k', '0.25W', '200 mA', '50V', '1%'
    For '%' we return the fractional value (e.g. 1% -> 0.01).
    For voltage/current/power, we just return the numeric part in SI.
    """
    s = s.strip()
    if not s:
        raise ValueError("Empty number")

    if s.endswith("%"):
        num = float(s[:-1])
        return num / 100.0

    m = re.match(r"^([+-]?\d+(\.\d+)?([eE][+-]?\d+)?)\s*([a-zA-Zµ]*)$", s)
    if not m:
        raise ValueError(f"Cannot parse number+unit: '{s}'")

    num = float(m.group(1))
    unit = m.group(4)
    if not unit:
        return num

    # Split prefix + base unit if needed (e.g. 'kV' -> 'k' 'V')
    if len(unit) > 1 and unit[0] in PREFIXES:
        pref = unit[0]
        return num * PREFIXES[pref]
    if unit in PREFIXES:
        return num * PREFIXES[unit]
    return num  # ignore unknown units but keep magnitude


# ---------- Schematic meta model ----------

@dataclass
class SymbolMeta:
    ref: str
    value: str
    lib_id: str
    fields: Dict[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """
        Infer component type from reference or library.
        'R1' -> 'resistor', 'C1' -> 'capacitor', etc.
        """
        if self.ref.upper().startswith("R"):
            return "resistor"
        if self.ref.upper().startswith("C"):
            return "capacitor"
        if self.ref.upper().startswith("L"):
            return "inductor"
        if self.ref.upper().startswith("D"):
            return "diode"
        if self.ref.upper().startswith("Q"):
            return "bjt"
        if self.ref.upper().startswith("M"):
            return "mosfet"
        if self.ref.upper().startswith("U"):
            return "ic"
        return "other"

    def dut_name(self) -> Optional[str]:
        return self.fields.get("DUT")

    def field_f(self, name: str) -> Optional[float]:
        """Parse a numeric field (Tol, Vmax, Imax, Pmax, etc.) into a float."""
        raw = self.fields.get(name)
        if not raw:
            return None
        try:
            return parse_number_with_unit(raw)
        except ValueError:
            return None


@dataclass
class SchematicMeta:
    path: Path
    symbols: List[SymbolMeta]
    global_labels: List[str]

    def symbols_for_dut(self, dut: str) -> List[SymbolMeta]:
        return [s for s in self.symbols if s.dut_name() == dut]


def _find_children(root: Any, name: str) -> List[Any]:
    """
    Find all lists that start with the given symbol name.
    E.g. (symbol ...) or (global_label ...)
    """
    found: List[Any] = []

    if isinstance(root, list) and root:
        head = root[0]
        if head == name:
            found.append(root)

        for item in root[1:]:
            found.extend(_find_children(item, name))

    return found


def _extract_property_list(node: Any) -> Dict[str, str]:
    """
    Given a (symbol ...) node, find all (property "Name" "Value" ...) children.
    Return a dict: {Name: Value}
    """
    props: Dict[str, str] = {}

    if not isinstance(node, list):
        return props

    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == "property":
            # form: (property "Ref" "R1" ...)
            if len(child) >= 3:
                key = str(child[1])
                val = str(child[2])
                props[key] = val
    return props


def load_schematic(path: Path) -> SchematicMeta:
    """
    Load a KiCad .kicad_sch file and build minimal metadata.
    """
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    root = parse_sexpr(text)

    symbols: List[SymbolMeta] = []
    global_labels: List[str] = []

    for sym_node in _find_children(root, "symbol"):
        lib_id = ""
        if len(sym_node) >= 2 and isinstance(sym_node[1], str):
            lib_id = sym_node[1]
        props = _extract_property_list(sym_node)
        ref = props.get("Reference", "?")
        val = props.get("Value", "?")
        # Include all properties as fields
        symbol = SymbolMeta(ref=ref, value=val, lib_id=lib_id, fields=props)
        symbols.append(symbol)

    for gl_node in _find_children(root, "global_label") + _find_children(
        root, "hierarchical_label"
    ):
        # Expect something like: (global_label (at ...) (shape ...) (text "VIN") ...)
        for child in gl_node[1:]:
            if isinstance(child, list) and child and child[0] == "text":
                if len(child) >= 2:
                    global_labels.append(str(child[1]))

    return SchematicMeta(path=path, symbols=symbols, global_labels=global_labels)


# ---------- Corners ----------

def corners_from_tolerances(
    kinds: Sequence[str] = ("min", "nom", "max")
) -> List[Dict[str, float]]:
    """
    Build deterministic tolerance corners for R/C/etc.

    This function returns a list of dicts; each dict describes how tolerances
    are applied for that corner. 'tol_sign' is multiplied by the per-symbol
    Tol field.

    Example output (for default kinds):
        [
          {"name": "min", "tol_sign": -1.0},
          {"name": "nom", "tol_sign": 0.0},
          {"name": "max", "tol_sign": +1.0},
        ]

    The control builder uses this together with per-symbol Tol values.
    """
    mapping = {
        "min": {"name": "min", "tol_sign": -1.0},
        "nom": {"name": "nom", "tol_sign": 0.0},
        "max": {"name": "max", "tol_sign": +1.0},
    }
    result: List[Dict[str, float]] = []
    for k in kinds:
        if k not in mapping:
            raise ValueError(f"Unknown corner kind: '{k}'")
        result.append(mapping[k])
    return result


# ---------- Netlist mapping ----------

def net_for_dut(dut: str, root: Path) -> Path:
    """
    Simple convention: DUT 'VoltageDivider' -> 'netlists/voltage_divider.cir'
    and 'LDO' -> 'netlists/ldo_example.cir', etc.

    'dut' is lowercased and non-alphanumerics changed to underscores.
    """
    norm = re.sub(r"[^0-9a-zA-Z]+", "_", dut).lower()
    return (root / "netlists" / f"{norm}.cir").resolve()
