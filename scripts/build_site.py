"""Construit le site statique dans _site/ à partir des campagnes brutes de raw/.

Sélection :
- seules les campagnes envoyées à la liste nommée dans site.json ("liste_archivee") ;
- moins celles listées dans "exclues" ;
- moins celles dont le nom de campagne Mailchimp contient "marqueur_exclusion".

Nettoyage : on ne garde que le texte, les images et les séparateurs des blocs
Mailchimp ; partage, réseaux sociaux, pieds de page, liens de désinscription,
balises de fusion (*|...|*) et styles en ligne disparaissent.
"""

import difflib
import os
import html
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, Comment

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / os.environ.get("JDF_SORTIE", "_site")
ASSETS = ROOT / "assets"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

# Blocs Mailchimp sans contenu littéraire.
BLOCS_IGNORES = {"mcnShareBlock", "mcnFollowBlock", "mcnButtonBlock", "mcnCodeBlock"}
BLOCS_CONNUS = BLOCS_IGNORES | {
    "mcnTextBlock", "mcnBoxedTextBlock", "mcnDividerBlock", "mcnImageBlock",
    "mcnImageCardBlock", "mcnImageGroupBlock", "mcnCaptionBlock",
}

# Blocs de texte courts qui relèvent du pied de page ou de la mécanique d'envoi.
PIED = re.compile(
    r"désabonn|vous pouvez (soutenir|encourager)|copyright|merci de me lire|"
    r"merci pour vos messages|formulaire d.abonnement|un clic sur l.un de ces boutons|"
    r"autres sites|this email was sent|pour me contacter|ajoutez .{0,40} à vos contacts",
    re.I,
)
# Liens de navigation Mailchimp à supprimer avec leur texte.
NAV = re.compile(
    r"^\s*(lire|voir|consulter)( cette infolettre| ce message)? (dans|sur) (mon|un|votre) navigateur\s*$|"
    r"^\s*(lire|voir) en ligne\s*$|"
    r"^\s*(consulter|lire|voir) les (lettres|infolettres|numéros) précédent(e)?s\s*$|"
    r"^\s*(envoyer à un ami|gazouiller|partager|tweet|forward)\s*$",
    re.I,
)
FUSION = re.compile(r"\*\|[^|]*\|\*")
# Paragraphes de pied de page Mailchimp : on coupe à partir du premier rencontré.
PIED_DUR = re.compile(
    r"copyright\s*©|our mailing address|want to change how you receive|this email was sent to|"
    r"why did i get this|update subscription preferences|unsubscribe from this list|"
    r"\bvous d[ée]sabonner\b|merci pour vos messages|formulaire d.abonnement est ici|"
    r"un clic sur l.un de ces boutons",
    re.I,
)
# Formule d'adresse « Cher abonné, Chère abonnée » : propre à l'envoi par mail.
SALUT_LIGNE = re.compile(
    r"^\s*((ch[eè]re?s?|ch[eè]r\(e\))\s+abonn[ée]+(e|\(e\))?s?\s*[,;!.]?\s*)+$", re.I)
SALUTATION = re.compile(r"^\s*(ch[eè]re?s?|cher\(e\)|ch[eè]r\(e\))\b", re.I)

INLINE = {"em", "i", "strong", "b", "a", "sup", "sub", "u", "s", "small", "span", "font", "code"}
BLOCK_ATOMIQUE = {"ul", "ol", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "pre"}


def slugify(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:60].strip("-") or "texte"


def sans_emoji(texte: str) -> str:
    return "".join(c for c in texte if unicodedata.category(c) not in ("So", "Cs", "Mn")
                   and c not in "‍️").strip()


def normalise(texte: str) -> str:
    t = unicodedata.normalize("NFKD", sans_emoji(texte)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def date_fr(iso: str) -> str:
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS[d.month - 1]} {d.year}"


def titre_affiche(sujet: str) -> str:
    """« Jours de Francis 21 : 12 novembre — 2 décembre 2018 » devient « 12 novembre — 2 décembre 2018 »."""
    t = re.sub(r"^\s*Jours de Francis\s*\d*\s*[^\w\s:]*\s*:\s*", "", sujet).strip()
    t = t or sujet.strip()
    t = "".join(c for c in t if unicodedata.category(c) != "So" and c not in "\u200d\ufe0f")
    t = re.sub(r"[\s\xa0]+", " ", t).strip()
    return t[0].upper() + t[1:] if t[0].islower() else t


# --------------------------------------------------------------------------- nettoyage

class Nettoyeur:
    def __init__(self, liens_locaux: dict[str, str]):
        self.liens_locaux = liens_locaux

    def lien(self, href: str) -> str | None:
        href = (href or "").strip()
        if not href or FUSION.search(href):
            return None
        href = re.sub(r"^http://https?:?/*", "https://", href)
        cle = href.split("#")[0].rstrip("/")
        if cle in self.liens_locaux:
            return self.liens_locaux[cle]
        if re.search(r"list-manage\.com/(unsubscribe|profile|vcard)|mailchimp\.com/(about|templates)", href):
            return None
        return href

    def inline(self, node) -> str:
        """Rend un nœud en HTML inline propre."""
        if isinstance(node, Comment):
            return ""
        if isinstance(node, NavigableString):
            t = FUSION.sub("", str(node))
            return html.escape(t, quote=False)
        if not isinstance(node, Tag):
            return ""
        nom = node.name
        if nom in ("style", "script", "head", "title", "meta"):
            return ""
        if nom == "br":
            return "<br>"
        interieur = "".join(self.inline(c) for c in node.children)
        if nom == "a":
            if NAV.match(node.get_text(" ", strip=True) or ""):
                return ""
            cible = self.lien(node.get("href", ""))
            if not cible or not interieur.strip():
                return interieur
            ext = "" if cible.startswith("/") or cible.startswith("mailto:") else ' rel="noopener"'
            return f'<a href="{html.escape(cible)}"{ext}>{interieur}</a>'
        style = (node.get("style") or "").replace(" ", "").lower()
        italique = nom in ("em", "i") or "font-style:italic" in style
        gras = nom in ("strong", "b") or re.search(r"font-weight:(bold|[6-9]00)", style)
        if not interieur.strip():
            return interieur
        if nom in ("sup", "sub"):
            interieur = f"<{nom}>{interieur}</{nom}>"
        if gras:
            interieur = f"<strong>{interieur}</strong>"
        if italique:
            interieur = f"<em>{interieur}</em>"
        return interieur

    def atomique(self, node: Tag) -> str:
        nom = node.name
        if nom in ("ul", "ol"):
            items = [self.inline(li).strip() for li in node.find_all("li", recursive=False)]
            items = [i for i in items if i]
            return f"<{nom}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{nom}>" if items else ""
        if nom in ("h1", "h2", "h3", "h4", "h5", "h6"):
            t = self.inline(node).strip()
            niveau = {"h1": "h2", "h2": "h2", "h3": "h3"}.get(nom, "h4")
            return f"<{niveau}>{t}</{niveau}>" if t else ""
        if nom == "blockquote":
            corps = self.flux(node)
            return f"<blockquote>{corps}</blockquote>" if corps else ""
        if nom == "pre":
            return f"<pre>{html.escape(node.get_text())}</pre>"
        return ""

    @staticmethod
    def habille(texte: str, fmt: tuple) -> str:
        if not texte.strip():
            return texte
        for f in reversed(fmt):
            texte = f"<{f}>{texte}</{f}>"
        return texte

    def jetons(self, node, sortie: list, fmt: tuple = ()):
        """Aplatit un bloc en jetons : ('t', html inline), ('br',), ('fin',), ('bloc', html)."""
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            sortie.append(("t", self.habille(self.inline(node), fmt)))
            return
        if not isinstance(node, Tag):
            return
        nom = node.name
        if nom == "br":
            sortie.append(("br",))
        elif nom == "img":
            src = node.get("src", "")
            if src and not FUSION.search(src) and "cdn-images.mailchimp.com/icons" not in src:
                alt = html.escape(node.get("alt", "") or "")
                sortie.append(("bloc", f'<figure><img src="{html.escape(src)}" alt="{alt}" loading="lazy"></figure>'))
        elif nom == "hr":
            sortie.append(("bloc", "<hr>"))
        elif nom == "pre":
            texte = node.get_text(" ", strip=True)
            if texte and not FUSION.search(texte) and not NAV.match(texte):
                sortie.append(("bloc", self.atomique(node)))
        elif nom in BLOCK_ATOMIQUE:
            sortie.append(("bloc", self.atomique(node)))
        elif nom in INLINE:
            if node.find(["br", "p", "div", "table", "img", "ul", "ol", "h1", "h2", "h3", "h4", "blockquote"]):
                # élément « en ligne » qui contient des retours : on descend en gardant sa mise en forme
                style = (node.get("style") or "").replace(" ", "").lower()
                ajout = ()
                if nom in ("strong", "b") or re.search(r"font-weight:(bold|[6-9]00)", style):
                    ajout += ("strong",)
                if nom in ("em", "i") or "font-style:italic" in style:
                    ajout += ("em",)
                for c in node.children:
                    self.jetons(c, sortie, fmt + ajout)
            else:
                sortie.append(("t", self.habille(self.inline(node), fmt)))
        else:
            # p, div, td, table… : frontières de paragraphe
            sortie.append(("fin",))
            for c in node.children:
                self.jetons(c, sortie, fmt)
            sortie.append(("fin",))

    def flux(self, node) -> str:
        jetons: list = []
        for c in node.children:
            self.jetons(c, jetons)
        paras, courant, brs = [], [], 0

        def clore():
            texte = "".join(courant)
            texte = re.sub(r"^(\s|<br>)+|(\s|<br>)+$", "", texte)
            if re.sub(r"<[^>]+>|&nbsp;|\s", "", texte):
                # Certains envois séparent les paragraphes par un seul retour à la ligne :
                # si les lignes sont longues, chacune devient un paragraphe.
                lignes = [l.strip() for l in texte.split("<br>")]
                longueurs = sorted(len(re.sub(r"<[^>]+>", "", l)) for l in lignes)
                if len(lignes) >= 3 and longueurs[len(longueurs) // 2] > 150:
                    paras.extend(f"<p>{l}</p>" for l in lignes if re.sub(r"<[^>]+>|&nbsp;|\s", "", l))
                else:
                    paras.append(f"<p>{texte}</p>")
            courant.clear()

        for j in jetons:
            if j[0] == "t" and not re.sub(r"&nbsp;|\s", "", j[1]):
                if brs == 0:
                    courant.append(" " if j[1] else "")
                continue
            if j[0] == "t":
                if brs >= 2:
                    clore()
                elif brs == 1:
                    courant.append("<br>")
                brs = 0
                courant.append(j[1])
            elif j[0] == "br":
                brs += 1
            elif j[0] == "fin":
                brs = 0
                clore()
            else:
                brs = 0
                clore()
                if j[1]:
                    paras.append(j[1])
        clore()
        gardes = []
        for para in paras:
            texte = html.unescape(re.sub(r"<[^>]+>", " ", para))
            texte = re.sub(r"\s+", " ", texte).strip()
            if PIED_DUR.search(texte) and len(texte) < 400:
                break
            if NAV.match(texte) or re.fullmatch(r"[\s|·•-]*", texte):
                continue
            gardes.append(para)
        return "\n".join(gardes)


def blocs_mailchimp(soup: BeautifulSoup) -> list[tuple[str, Tag]]:
    blocs = []
    for t in soup.find_all("table"):
        classes = [c for c in (t.get("class") or []) if c in BLOCS_CONNUS]
        if not classes:
            continue
        parent = t.find_parent(lambda p: p.name == "table" and any(
            c in BLOCS_CONNUS for c in (p.get("class") or [])))
        if parent is None:
            blocs.append((classes[0], t))
    return blocs


def extraire(html_brut: str, sujet: str, nettoyeur: Nettoyeur, images_communes: set) -> str:
    soup = BeautifulSoup(html_brut, "lxml")
    for s in soup.select(".mcnPreviewText, style, script"):
        s.decompose()
    morceaux: list[str] = []
    titre_n = normalise(sujet)
    titre_n2 = normalise(titre_affiche(sujet))
    for genre, bloc in blocs_mailchimp(soup):
        if genre in BLOCS_IGNORES:
            continue
        if genre == "mcnDividerBlock":
            morceaux.append("<hr>")
            continue
        for img in bloc.find_all("img"):
            if img.get("src", "") in images_communes:
                img.decompose()
        contenus = bloc.select(".mcnTextContent") if genre in ("mcnTextBlock", "mcnBoxedTextBlock") else [bloc]
        for c in contenus:
            texte = re.sub(r"\s+", " ", c.get_text(" ", strip=True))
            if texte and len(texte) < 700 and PIED.search(texte):
                continue
            rendu = nettoyeur.flux(c)
            if not rendu:
                continue
            if not morceaux or all(m == "<hr>" for m in morceaux):
                n = normalise(re.sub(r"<[^>]+>", "", rendu))
                if n and len(n) < 80 and any(
                    n == t or (len(n) >= 4 and (n in t or t in n))
                    or difflib.SequenceMatcher(None, n, t).ratio() > 0.75
                    for t in (titre_n, titre_n2) if t):
                    continue
            morceaux.append(rendu)
    # séparateurs superflus en tête, en queue ou doublés
    while morceaux and morceaux[0] == "<hr>":
        morceaux.pop(0)
    while morceaux and morceaux[-1] == "<hr>":
        morceaux.pop()
    morceaux = [m for m in morceaux if m]
    propre = []
    for m in morceaux:
        if m == "<hr>" and propre and propre[-1] == "<hr>":
            continue
        propre.append(m)
    return retirer_salutation("\n".join(propre))


def retirer_salutation_ancienne(morceaux: list[str]) -> list[str]:
    morceaux = list(morceaux)
    for i, m in enumerate(morceaux[:3]):
        para = re.match(r"\s*<p>(.*?)</p>", m, re.S)
        if not para:
            if m.strip() and m != "<hr>":
                break
            continue
        lignes = para.group(1).split("<br>")
        n = len(lignes)
        while lignes and SALUT_LIGNE.match(html.unescape(re.sub(r"<[^>]+>", "", lignes[0]))):
            lignes.pop(0)
        if len(lignes) == n:
            break  # le texte ne commence pas par une formule d'adresse : on n'y touche pas
        reste = "<br>".join(lignes).strip()
        reste = re.sub(r"^(\s|<br>)+", "", reste)
        nouveau = f"<p>{reste}</p>" if re.sub(r"<[^>]+>|&nbsp;|\s", "", reste) else ""
        morceaux[i] = (nouveau + m[para.end():]).strip()
        break
    return morceaux


def retirer_salutation(contenu: str) -> str:
    """Supprime « Cher abonné, Chère abonnée » dans les premiers paragraphes du texte."""
    vus = 0
    def remplace(m):
        nonlocal vus
        vus += 1
        if vus > 5:
            return m.group(0)
        lignes = m.group(1).split("<br>")
        n = len(lignes)
        while lignes and SALUT_LIGNE.match(html.unescape(re.sub(r"<[^>]+>", "", lignes[0]))):
            lignes.pop(0)
        if len(lignes) == n:
            return m.group(0)
        reste = re.sub(r"^(\s|<br>)+", "", "<br>".join(lignes).strip())
        return f"<p>{reste}</p>" if re.sub(r"<[^>]+>|&nbsp;|\s", "", reste) else ""
    contenu = re.sub(r"<p>(.*?)</p>", remplace, contenu, flags=re.S)
    return re.sub(r"\n{2,}", "\n", contenu).strip()


def retirer_paragraphe(contenu: str, debut: str, titre: str) -> str:
    """Retire le paragraphe qui commence par `debut` (comparaison sans ponctuation ni casse)."""
    cle = normalise(debut)[:60]
    trouve = False
    def remplace(m):
        nonlocal trouve
        texte = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        # un paragraphe sans lettres (« * », « *** ») se compare tel quel
        correspond = normalise(texte).startswith(cle) if cle else texte == debut.strip()
        if not trouve and correspond:
            trouve = True
            return ""
        return m.group(0)
    contenu = re.sub(r"<p>(.*?)</p>", remplace, contenu, flags=re.S)
    if not trouve:
        print(f"::warning::Retouche introuvable dans « {titre} » : {debut[:60]}")
    return re.sub(r"\n{2,}", "\n", contenu).strip()


def paragraphes(contenu: str) -> list:
    """Liste des paragraphes <p>…</p> avec leur position et leur texte brut."""
    return [(m.start(), m.end(), html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip())
            for m in re.finditer(r"<p>(.*?)</p>", contenu, re.S)]


def couper(contenu: str, debut: str, titre: str, garder_apres: bool) -> str:
    """Garde ce qui suit (ou précède) le premier paragraphe commençant par `debut`.

    garder_apres=True : le paragraphe repère et tout ce qui le précède sont retirés.
    garder_apres=False : le paragraphe repère et tout ce qui le suit sont retirés.
    """
    cle = normalise(debut)[:60]
    for a, b, texte in paragraphes(contenu):
        if (normalise(texte).startswith(cle) if cle else texte == debut.strip()):
            return (contenu[b:] if garder_apres else contenu[:a]).strip()
    print(f"::warning::Repère introuvable dans « {titre} » : {debut[:60]}")
    return contenu


def chapeau(contenu: str, longueur: int = 170) -> str:
    for p in re.findall(r"<p>(.*?)</p>", contenu, re.S):
        t = html.unescape(re.sub(r"<[^>]+>", " ", p))
        t = re.sub(r"\s+", " ", t).strip()
        lignes = [l for l in re.split(r"(?<=[,.!?])\s+", t)]
        if not t or SALUTATION.match(t) and len(t) < 60:
            continue
        t = re.sub(r"^(ch[eè]re? abonn[ée]+e?s?,?\s*)+", "", t, flags=re.I).strip()
        if len(t) < 25:
            continue
        if len(t) > longueur:
            t = t[:longueur].rsplit(" ", 1)[0].rstrip(",;:— ") + "…"
        t = re.sub(r"\s+([,.)…])", r"\1", t).replace("( ", "(")
        return html.escape(t)
    return ""


# --------------------------------------------------------------------------- gabarits

def page(cfg: dict, titre: str, corps: str, description: str = "", classe: str = "") -> str:
    titre_complet = titre if titre == cfg["titre"] else f"{titre} — {cfg['titre']}"
    desc = html.escape(description or cfg["accroche"])
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titre_complet)}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{html.escape(titre)}">
<meta property="og:description" content="{desc}">
<link rel="alternate" type="application/rss+xml" title="{html.escape(cfg['titre'])}" href="/flux.xml">
<link rel="icon" href="/favicon.png" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:image" content="https://{cfg['domaine']}/chien-web.jpg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
</head>
<body class="{classe}">
<header class="tete">
  <a class="marque" href="/">{html.escape(cfg['titre'])}</a>
  <nav><a href="/archives/">Archives</a><a href="/#livre">Le livre</a><a href="/#video">Vidéos</a><a class="nav-abo" href="/#inscription">S’abonner</a></nav>
</header>
<main>
{corps}
</main>
<footer class="pied">
  <p>© {datetime.now().year} Francis · <a href="/flux.xml">Flux RSS</a></p>
</footer>
</body>
</html>
"""


def formulaire(cfg: dict, ident: str = "inscription") -> str:
    ins = cfg["inscription"]
    return f"""<form class="inscription" id="{ident}" action="{html.escape(ins['action'])}" method="post" target="_blank">
  <label for="email-{ident}">Votre adresse électronique</label>
  <div class="champ">
    <input type="email" name="EMAIL" id="email-{ident}" placeholder="nom@exemple.fr" required autocomplete="email">
    <button type="submit">Je m’abonne</button>
  </div>
  <div aria-hidden="true" style="position:absolute;left:-5000px"><input type="text" name="{ins['pot_de_miel']}" tabindex="-1" value=""></div>
</form>"""


# --------------------------------------------------------------------------- construction

def main() -> None:
    cfg = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    index = json.loads((RAW / "index.json").read_text(encoding="utf-8"))
    exclues = {e["id"] for e in cfg.get("exclues", [])}
    marqueur = cfg.get("marqueur_exclusion", "").lower()

    retenues = [
        c for c in index
        if c.get("list") == cfg["liste_archivee"]
        and c["id"] not in exclues
        and not (marqueur and marqueur in (c.get("title") or "").lower())
        and (RAW / f"{c['file']}.html").exists()
    ]
    retenues.sort(key=lambda c: c["send_time"])

    retouches = {r["id"]: r for r in cfg.get("retouches", [])}

    # adresses web locales, et correspondance des anciennes URL d'archive Mailchimp
    vus = set()
    for c in retenues:
        titre = (retouches.get(c["id"], {}).get("titre")
                 or titre_affiche(c["subject"]) or c["title"])
        slug = f"{c['send_time'][:10]}-{slugify(sans_emoji(titre))}"
        while slug in vus:
            slug += "-2"
        vus.add(slug)
        c["slug"], c["titre_aff"] = slug, titre
    liens = {}
    for c in retenues:
        for u in (c.get("archive_url"), c.get("long_archive_url")):
            if u:
                liens[u.rstrip("/")] = f"/archives/{c['slug']}/"

    # images répétées d'un envoi à l'autre = bandeau du gabarit, pas du contenu
    from collections import Counter
    compte = Counter()
    for c in retenues:
        srcs = set(re.findall(r'<img[^>]+src="([^"]+)"', (RAW / f"{c['file']}.html").read_text(encoding="utf-8")))
        compte.update(srcs)
    communes = {s for s, n in compte.items() if n >= 3}

    nettoyeur = Nettoyeur(liens)
    for c in retenues:
        brut = (RAW / f"{c['file']}.html").read_text(encoding="utf-8")
        c["contenu"] = extraire(brut, c["subject"], nettoyeur, communes)
        r = retouches.get(c["id"], {})
        # « garder_apres » : repère (souvent « *** ») après lequel commence le texte
        if r.get("garder_apres"):
            c["contenu"] = couper(c["contenu"], r["garder_apres"], c["titre_aff"], True)
        if r.get("arreter_avant"):
            c["contenu"] = couper(c["contenu"], r["arreter_avant"], c["titre_aff"], False)
        for avant, apres in r.get("corrections", []):
            if avant not in c["contenu"]:
                print(f"::warning::Correction introuvable dans « {c['titre_aff']} » : {avant[:60]}")
            c["contenu"] = c["contenu"].replace(avant, apres)
        for debut in retouches.get(c["id"], {}).get("paragraphes_a_retirer", []):
            c["contenu"] = retirer_paragraphe(c["contenu"], debut, c["titre_aff"])
        c["chapeau"] = chapeau(c["contenu"])
        c["date_fr"] = date_fr(c["send_time"])

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    lourds = set(cfg.get("images", {}))  # originaux rapatriés de l'ancien site, non utilisés tels quels
    for f in ASSETS.iterdir():
        if f.name not in lourds:
            shutil.copy(f, OUT / f.name)
    prefixe = os.environ.get("JDF_BASE", cfg.get("base", "")).rstrip("/")
    if os.environ.get("JDF_CIBLE") == "infomaniak":
        # hébergement Apache : page 404 maison, HTTPS forcé, cache raisonnable
        (OUT / ".htaccess").write_text(
            "ErrorDocument 404 /404.html\n"
            "RewriteEngine On\n"
            "RewriteCond %{HTTPS} off\n"
            "RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]\n"
            "<IfModule mod_expires.c>\n"
            "  ExpiresActive On\n"
            "  ExpiresByType text/css \"access plus 1 week\"\n"
            "  ExpiresByType image/jpeg \"access plus 1 month\"\n"
            "  ExpiresByType image/png \"access plus 1 month\"\n"
            "</IfModule>\n")
    elif not prefixe and cfg.get("domaine"):
        # domaine personnel sur GitHub Pages : déclaré dans ce fichier
        (OUT / "CNAME").write_text(cfg["domaine"] + "\n")

    # pages des textes
    for i, c in enumerate(retenues):
        prec = retenues[i - 1] if i > 0 else None
        suiv = retenues[i + 1] if i + 1 < len(retenues) else None
        nav = '<nav class="suite">'
        nav += (f'<a class="prec" href="/archives/{prec["slug"]}/"><span>Précédente</span>{html.escape(prec["titre_aff"])}</a>'
                if prec else "<span></span>")
        nav += (f'<a class="suiv" href="/archives/{suiv["slug"]}/"><span>Suivante</span>{html.escape(suiv["titre_aff"])}</a>'
                if suiv else "<span></span>")
        nav += "</nav>"
        corps = f"""<article class="texte">
  <header>
    <p class="date"><time datetime="{c['send_time'][:10]}">{c['date_fr']}</time></p>
    <h1>{html.escape(c['titre_aff'])}</h1>
  </header>
  <div class="corps">
{c['contenu']}
  </div>
</article>
{nav}
<aside class="encart">{formulaire(cfg, 'inscription-bas')}</aside>"""
        d = OUT / "archives" / c["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(cfg, c["titre_aff"], corps, html.unescape(c["chapeau"]), "page-texte"), encoding="utf-8")

    # archives : tous les titres, du plus récent au plus ancien
    items = "\n".join(
        f"""    <li><a href="/archives/{c['slug']}/"><span class="t">{html.escape(c['titre_aff'])}</span>
      <span class="c">{c['chapeau']}</span></a></li>"""
        for c in reversed(retenues))
    corps = f"""<header class="intro">
  <h1>Archives</h1>
</header>
<section class="annee">
  <ul class="liste sans-date">
{items}
  </ul>
</section>"""
    (OUT / "archives").mkdir(exist_ok=True)
    (OUT / "archives" / "index.html").write_text(page(cfg, "Archives", corps, classe="page-archives"), encoding="utf-8")

    # accueil
    acc = cfg.get("accueil", {})
    livre = cfg.get("livre")
    video = cfg.get("video")
    paras = "\n".join(f"    <p>{t}</p>" for t in acc.get("presentation", []))
    dernieres = "\n".join(
        f"""      <li><a href="/archives/{c['slug']}/"><span class="t">{html.escape(c['titre_aff'])}</span>
        <span class="c">{c['chapeau']}</span></a></li>"""
        for c in list(reversed(retenues))[:3])
    bloc_livre = f"""<section class="livre" id="livre">
  <div class="livre-int">
    <a class="couv" href="{html.escape(livre['lien'])}" rel="noopener"><img src="/{livre['image']}" alt="Couverture de Jours de Francis, I. {html.escape(livre['titre'])}" width="480" height="829" loading="lazy" decoding="async"></a>
    <div class="livre-texte">
      <p class="etiquette">{html.escape(livre.get('etiquette', 'Le livre'))}</p>
      <h2>Jours de Francis<span>I. {html.escape(livre['titre'])}</span></h2>
{"".join(f"      <p>{t}</p>" for t in livre.get('presentation', []))}
      <p><a class="bouton" href="{html.escape(livre['lien'])}" rel="noopener">{html.escape(livre.get('bouton', 'Commander'))}</a></p>
    </div>
  </div>
</section>""" if livre else ""
    bloc_video = f"""<section class="video" id="video">
  <p class="etiquette">{html.escape(video.get('etiquette', 'En vidéo'))}</p>
  <h2>{html.escape(video['titre'])}</h2>
{"".join(f"  <p>{t}</p>" for t in video.get('presentation', []))}
  <p><a class="lien-fleche" href="{html.escape(video['lien'])}" rel="noopener">{html.escape(video.get('bouton', 'Voir la chaîne'))} →</a></p>
</section>""" if video else ""
    corps = f"""<section class="une">
  <div class="une-int">
    <figure class="embleme"><img src="/{acc.get('image', 'chien-web.jpg')}" alt="Tête de chien, gravure sur bois" width="560" height="603" fetchpriority="high"></figure>
    <div class="une-texte">
      <h1>{html.escape(cfg['titre'])}</h1>
      <p class="accroche">{html.escape(cfg['accroche'])}</p>
{paras}
      {formulaire(cfg)}
      {f'<p class="rassurance">{acc["rassurance"]}</p>' if acc.get("rassurance") else ""}
    </div>
  </div>
</section>
<section class="recents">
  <h2>Derniers envois</h2>
  <ul class="liste sans-date">
{dernieres}
  </ul>
  <p class="tout"><a href="/archives/">Toutes les infolettres →</a></p>
</section>
{bloc_livre}
{bloc_video}"""
    (OUT / "index.html").write_text(page(cfg, cfg["titre"], corps, acc.get("description", ""), classe="page-accueil"), encoding="utf-8")

    # 404
    (OUT / "404.html").write_text(page(cfg, "Page introuvable", """<header class="intro"><h1>Page introuvable</h1>
<p>Cette page n'existe pas, ou plus. Les infolettres sont toutes dans les <a href="/archives/">archives</a>.</p></header>"""), encoding="utf-8")

    # flux RSS des 20 derniers textes
    base = f"https://{cfg['domaine']}" if not prefixe else f"https://gavrine.github.io{prefixe}"
    items = []
    for c in list(reversed(retenues))[:20]:
        d = datetime.fromisoformat(c["send_time"].replace("Z", "+00:00"))
        contenu = re.sub(r'href="/', f'href="{base}/', c["contenu"])
        items.append(f"""<item><title>{html.escape(c['titre_aff'])}</title><link>{base}/archives/{c['slug']}/</link>
<guid>{base}/archives/{c['slug']}/</guid><pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
<description>{html.escape(contenu)}</description></item>""")
    (OUT / "flux.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>{html.escape(cfg['titre'])}</title><link>{base}/</link>
<description>{html.escape(cfg['accroche'])}</description><language>fr</language>
{''.join(items)}
</channel></rss>
""", encoding="utf-8")

    # Tant que le site est servi sous github.io/joursdefrancis, les liens internes
    # doivent porter ce préfixe ; il disparaît quand "base" est vidé dans site.json.
    if prefixe:
        for f in OUT.rglob("*.html"):
            t = f.read_text(encoding="utf-8")
            t = re.sub(r'(href|src|action)="/(?!/)', rf'\1="{prefixe}/', t)
            f.write_text(t, encoding="utf-8")

    print(f"{len(retenues)} infolettres publiées dans _site/.")


if __name__ == "__main__":
    main()
