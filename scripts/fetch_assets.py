"""Télécharge une seule fois les images listées dans site.json ("images") vers assets/.

Sert à rapatrier les visuels de l'ancien site WordPress pour ne plus en dépendre.
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def main() -> None:
    cfg = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    for nom, url in cfg.get("images", {}).items():
        cible = ASSETS / nom
        if cible.exists():
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                cible.write_bytes(r.read())
            print(f"Image récupérée : {nom}")
        except Exception as e:  # une image manquante ne doit pas bloquer la publication
            print(f"::warning::Impossible de récupérer {url} : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
