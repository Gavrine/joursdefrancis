"""Récupère toutes les campagnes Mailchimp envoyées et les stocke brutes dans raw/.

- Lit la clé dans la variable d'environnement MAILCHIMP_API_KEY (format xxxx-us3).
- Ne télécharge le contenu que des campagnes absentes de raw/ : les passages
  suivants ne récupèrent que les nouvelles.
- Écrit raw/index.json (liste triée par date d'envoi) et, pour chaque campagne,
  raw/<date>_<id>.html et raw/<date>_<id>.txt.

Aucune dépendance externe : bibliothèque standard Python uniquement.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"


def api(key: str, path: str) -> dict:
    dc = key.rsplit("-", 1)[-1]
    url = f"https://{dc}.api.mailchimp.com/3.0{path}"
    token = base64.b64encode(f"anystring:{key}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Erreur API Mailchimp {e.code} sur {path} : {e.read().decode()[:500]}")


def list_sent(key: str) -> list[dict]:
    fields = (
        "campaigns.id,campaigns.send_time,campaigns.archive_url,campaigns.long_archive_url,"
        "campaigns.settings.subject_line,campaigns.settings.title,campaigns.settings.preview_text,"
        "campaigns.recipients.list_name,total_items"
    )
    out, offset = [], 0
    while True:
        page = api(
            key,
            f"/campaigns?status=sent&count=500&offset={offset}"
            f"&sort_field=send_time&sort_dir=ASC&fields={fields}",
        )
        out += page.get("campaigns", [])
        offset += 500
        if offset >= page.get("total_items", 0):
            return out


def main() -> None:
    key = os.environ.get("MAILCHIMP_API_KEY", "").strip()
    if not key or "-" not in key:
        sys.exit("MAILCHIMP_API_KEY absente ou mal formée (attendu : xxxxxxxx-us3).")

    RAW.mkdir(exist_ok=True)
    campaigns = list_sent(key)
    index, new = [], 0
    for c in campaigns:
        date = (c.get("send_time") or "")[:10]
        slug = f"{date}_{c['id']}"
        s = c.get("settings", {})
        index.append({
            "id": c["id"],
            "file": slug,
            "send_time": c.get("send_time"),
            "subject": s.get("subject_line", ""),
            "title": s.get("title", ""),
            "preview": s.get("preview_text", ""),
            "list": c.get("recipients", {}).get("list_name", ""),
            "archive_url": c.get("long_archive_url") or c.get("archive_url"),
        })
        html_path = RAW / f"{slug}.html"
        if html_path.exists():
            continue
        content = api(key, f"/campaigns/{c['id']}/content?fields=html,plain_text")
        html_path.write_text(content.get("html") or "", encoding="utf-8")
        (RAW / f"{slug}.txt").write_text(content.get("plain_text") or "", encoding="utf-8")
        new += 1

    (RAW / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(index)} campagnes envoyées au total, {new} nouvelles récupérées.")


if __name__ == "__main__":
    main()
