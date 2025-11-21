from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PROJECTS = (ROOT / "Projects") if (ROOT / "Projects").exists() else (ROOT / "projects")
