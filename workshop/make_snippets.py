"""Regenerate workshop/snippets/ from workshop/stages/. Run after editing a stage.

Each snippet lists, in file order, the blocks that stage N adds or changes,
with an anchor line saying where they go. The runbook says which lines to
type by hand; everything else is pasted from here.
"""

import difflib
from pathlib import Path

ROOT = Path(__file__).parent
STAGES, OUT = ROOT / "stages", ROOT / "snippets"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for n in range(1, 6):
        old = (STAGES / f"stage_{n - 1}.py").read_text().splitlines()
        new = (STAGES / f"stage_{n}.py").read_text().splitlines()
        parts = [f"# Stage {n} snippets: blocks to add or replace, in file order.\n"]
        sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            anchor = next((ln for ln in reversed(old[:i1]) if ln.strip()), "<top of file>")
            verb = "REPLACE the lines below this anchor with" if tag == "replace" else "ADD after"
            if tag == "delete":
                parts.append(f"# ---- DELETE {i2 - i1} line(s) after: {anchor.strip()[:70]}\n")
                continue
            parts.append(f"# ---- {verb}: {anchor.strip()[:70]}")
            parts.append("\n".join(new[j1:j2]) + "\n")
        (OUT / f"stage_{n}.txt").write_text("\n".join(parts))
        print(f"stage {n}: {sum(1 for p in parts if p.startswith('# ----'))} blocks")


if __name__ == "__main__":
    main()
