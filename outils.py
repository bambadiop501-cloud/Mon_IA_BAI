"""Outils de B.AI : météo, heure, recherche web, images, photos libres, PDF et PowerPoint.

Chaque outil renvoie un texte court pour le modèle. Les images et fichiers produits
sont ajoutés à la liste `pieces` du tour en cours, pour être affichés et téléchargés.
"""
from __future__ import annotations

import io
import os
import re
import time
import unicodedata
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from fpdf import FPDF
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

ICI = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(ICI, "logo.png")
POLICE = os.path.join(ICI, "fonts", "DejaVuSans.ttf")
POLICE_GRAS = os.path.join(ICI, "fonts", "DejaVuSans-Bold.ttf")
FUSEAU_DEFAUT = "Africa/Dakar"
ENTETES = {"User-Agent": "B.AI/2.0 (https://github.com/bambadiop501-cloud/mon_ia_bai)"}
DELAI = 20  # secondes, pour tous les appels à internet

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def date_longue(d: datetime) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


# ---------------------------------------------------------------- lieux et heure
def trouver_lieu(ville: str) -> dict | None:
    """Coordonnées et fuseau d'une ville (Open-Meteo, gratuit, sans clé)."""
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": ville, "count": 1, "language": "fr", "format": "json"},
                     headers=ENTETES, timeout=DELAI)
    r.raise_for_status()
    res = r.json().get("results") or []
    return res[0] if res else None


def heure(ville: str = "") -> str:
    fuseau, lieu = FUSEAU_DEFAUT, "Dakar"
    if ville:
        try:
            l = trouver_lieu(ville)
            if l and l.get("timezone"):
                fuseau, lieu = l["timezone"], f"{l['name']} ({l.get('country', '')})"
        except requests.RequestException:
            pass
    maintenant = datetime.now(ZoneInfo(fuseau))
    return f"À {lieu}, il est {maintenant:%H:%M}, nous sommes le {date_longue(maintenant)} (fuseau {fuseau})."


# ---------------------------------------------------------------- météo
METEO_CODES = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
               45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte",
               56: "bruine verglaçante", 57: "bruine verglaçante", 61: "pluie faible", 63: "pluie", 65: "forte pluie",
               66: "pluie verglaçante", 67: "pluie verglaçante", 71: "neige faible", 73: "neige", 75: "forte neige",
               77: "grains de neige", 80: "averses", 81: "averses", 82: "fortes averses", 85: "averses de neige",
               86: "averses de neige", 95: "orage", 96: "orage avec grêle", 99: "orage avec grêle"}


def meteo(ville: str) -> str:
    try:
        lieu = trouver_lieu(ville)
        if not lieu:
            return f"Ville introuvable : {ville}."
        r = requests.get("https://api.open-meteo.com/v1/forecast", headers=ENTETES, timeout=DELAI, params={
            "latitude": lieu["latitude"], "longitude": lieu["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        r.raise_for_status()
        d = r.json()
        c, j = d["current"], d["daily"]
        txt = (f"Météo à {lieu['name']} ({lieu.get('country', '')}) maintenant : "
               f"{METEO_CODES.get(c['weather_code'], 'temps variable')}, {c['temperature_2m']:.0f} °C "
               f"(ressenti {c['apparent_temperature']:.0f} °C), humidité {c['relative_humidity_2m']} %, "
               f"vent {c['wind_speed_10m']:.0f} km/h.")
        for i, jour in enumerate(j["time"][:3]):
            nom = ["Aujourd'hui", "Demain", "Après-demain"][i]
            pluie = j["precipitation_probability_max"][i]
            txt += (f"\n{nom} : {METEO_CODES.get(j['weather_code'][i], 'variable')}, "
                    f"{j['temperature_2m_min'][i]:.0f} à {j['temperature_2m_max'][i]:.0f} °C"
                    + (f", pluie {pluie} %" if pluie is not None else "") + ".")
        return txt + "\nSource : Open-Meteo."
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return meteo_secours(ville)


def meteo_secours(ville: str) -> str:
    """Deuxième source (wttr.in) quand Open-Meteo est saturé."""
    try:
        r = requests.get(f"https://wttr.in/{urllib.parse.quote(ville)}", params={"format": "j1", "lang": "fr"},
                         headers=ENTETES, timeout=DELAI)
        r.raise_for_status()
        d = r.json()
        c = d["current_condition"][0]
        etat = (c.get("lang_fr") or c.get("weatherDesc") or [{"value": ""}])[0]["value"].lower()
        txt = (f"Météo à {ville} maintenant : {etat}, {c['temp_C']} °C (ressenti {c['FeelsLikeC']} °C), "
               f"humidité {c['humidity']} %, vent {c['windspeedKmph']} km/h.")
        noms = ["Aujourd'hui", "Demain", "Après-demain"]
        for i, j in enumerate(d.get("weather", [])[:3]):
            txt += f"\n{noms[i]} : {j['mintempC']} à {j['maxtempC']} °C."
        return txt + "\nSource : wttr.in."
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return "Le service météo ne répond pas pour le moment."


# ---------------------------------------------------------------- appels prudents
def _get(url: str, essais: int = 2, **kw) -> requests.Response | None:
    """GET avec délai et une nouvelle tentative si le service dit « trop de demandes »."""
    kw.setdefault("headers", ENTETES)
    kw.setdefault("timeout", DELAI)
    for i in range(essais):
        try:
            r = requests.get(url, **kw)
        except requests.RequestException:
            r = None
        if r is not None and r.status_code == 200:
            return r
        if i < essais - 1:
            attente = 3
            if r is not None and r.status_code in (429, 503):
                try:
                    attente = min(6, int(r.headers.get("Retry-After", 3)))
                except ValueError:
                    pass
            time.sleep(attente)
    return None


# ---------------------------------------------------------------- recherche web
def _wikipedia(requete: str) -> list[dict]:
    """Dernier recours : articles Wikipédia en français."""
    r = _get("https://fr.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": requete,
                                                           "srlimit": 5, "format": "json", "utf8": 1})
    if not r:
        return []
    res = []
    for x in r.json().get("query", {}).get("search", []):
        titre = x.get("title", "")
        res.append({"title": titre, "body": re.sub(r"<[^>]+>", "", x.get("snippet", "")),
                    "href": "https://fr.wikipedia.org/wiki/" + urllib.parse.quote(titre.replace(" ", "_"))})
    return res


def _tavily(requete: str, actualites: bool) -> list[dict]:
    """Moteur fiable (gratuit jusqu'à 1 000 recherches par mois), seulement si TAVILY_API_KEY est réglé."""
    cle = os.environ.get("TAVILY_API_KEY", "").strip()
    if not cle:
        return []
    try:
        r = requests.post("https://api.tavily.com/search", timeout=DELAI,
                          headers={"Authorization": f"Bearer {cle}", **ENTETES},
                          json={"query": requete, "max_results": 6, "topic": "news" if actualites else "general"})
        if r.status_code != 200:
            return []
        return [{"title": x.get("title", ""), "body": x.get("content", ""), "href": x.get("url", ""),
                 "date": x.get("published_date") or ""} for x in r.json().get("results", [])]
    except (requests.RequestException, ValueError):
        return []


def recherche_web(requete: str, actualites: bool = False) -> str:
    """Plusieurs moteurs l'un après l'autre : le premier qui répond gagne."""
    try:
        from ddgs import DDGS
    except ImportError:  # ancien nom du paquet
        from duckduckgo_search import DDGS
    res, source = _tavily(requete, actualites), "web"
    moteurs = ["auto"] if actualites else ["auto", "google"]
    for moteur in ([] if res else moteurs):
        try:
            with DDGS(timeout=6) as d:
                f = d.news if actualites else d.text
                res = list(f(requete, region="fr-fr", max_results=6, backend=moteur))
            if res:
                break
        except Exception:
            continue
    if not res and not actualites:
        res, source = _wikipedia(requete), "Wikipédia"
    if not res:
        return ("La recherche web ne répond pas pour le moment (moteurs gratuits saturés). "
                "Dis-le simplement, réponds avec tes connaissances en précisant qu'elles peuvent dater, et propose de réessayer plus tard.")
    lignes = []
    for x in res:
        url = x.get("href") or x.get("url") or ""
        date = f" ({x['date'][:10]})" if x.get("date") else ""
        lignes.append(f"- {x.get('title', '')}{date} : {x.get('body', '')[:300]} [{url}]")
    entete = "Résultats" + (" (source : Wikipédia, les moteurs web étaient saturés)" if source == "Wikipédia" else "")
    return entete + " — cite tes sources avec leurs liens :\n" + "\n".join(lignes)


# ---------------------------------------------------------------- images
TAILLES = {"carre": (1024, 1024), "portrait": (832, 1216), "paysage": (1216, 832)}


def lien_image_ia(description: str, format_image: str = "carre") -> str:
    w, h = TAILLES.get(format_image, TAILLES["carre"])
    return f"https://image.pollinations.ai/prompt/{urllib.parse.quote(description)}?width={w}&height={h}&nologo=true"


def _image_hf(description: str) -> bytes | None:
    """Secours : Hugging Face (FLUX.1 schnell), seulement si un jeton HF_TOKEN est réglé."""
    jeton = os.environ.get("HF_TOKEN", "").strip()
    if not jeton:
        return None
    try:
        r = requests.post("https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
                          headers={"Authorization": f"Bearer {jeton}", **ENTETES}, json={"inputs": description}, timeout=90)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except requests.RequestException:
        pass
    return None


def image_ia(description: str, format_image: str = "carre") -> bytes | None:
    """Image IA : Pollinations (gratuit, parfois saturé, 3 essais), puis Hugging Face si un jeton est réglé."""
    url = lien_image_ia(description, format_image)
    for essai in range(3):
        try:
            r = requests.get(url + f"&seed={essai + 1}", headers=ENTETES, timeout=60)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                return r.content
            if r.status_code == 400:
                break
            if essai < 2:
                time.sleep(min(10, int(r.headers.get("Retry-After", 6) or 6)))
        except (requests.RequestException, ValueError):
            pass
    return _image_hf(description)


def _photo_commons(sujet: str) -> dict | None:
    r = _get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "generator": "search", "gsrsearch": f"{sujet} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 6, "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
        "iiurlwidth": 1200, "format": "json"})
    if not r:
        return None
    pages = sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/") or "svg" in info.get("mime", ""):
            continue
        meta = info.get("extmetadata", {})
        auteur = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "auteur inconnu")).strip()
        licence = meta.get("LicenseShortName", {}).get("value", "licence libre")
        img = _get(info.get("thumburl") or info["url"])
        if img:
            return {"octets": img.content, "legende": f"Photo : {auteur[:80]}, {licence}, Wikimedia Commons",
                    "page": info.get("descriptionurl", "")}
    return None


def _photo_wikipedia(sujet: str) -> dict | None:
    for langue in ("en", "fr"):
        r = _get(f"https://{langue}.wikipedia.org/w/api.php", params={
            "action": "query", "generator": "search", "gsrsearch": sujet, "gsrlimit": 3,
            "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1000, "format": "json"})
        if not r:
            continue
        pages = sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        for p in pages:
            src = (p.get("thumbnail") or {}).get("source")
            img = _get(src) if src else None
            if img:
                page = f"https://{langue}.wikipedia.org/wiki/" + urllib.parse.quote(p.get("title", "").replace(" ", "_"))
                return {"octets": img.content, "legende": f"Photo de l'article Wikipédia « {p.get('title', '')} » (licence libre, voir la source)",
                        "page": page}
    return None


def _photo_openverse(sujet: str) -> dict | None:
    r = _get("https://api.openverse.org/v1/images/", params={"q": sujet, "page_size": 5})
    if not r:
        return None
    for x in r.json().get("results", []):
        img = _get(x.get("url", ""))
        if img and img.headers.get("content-type", "").startswith("image"):
            licence = f"CC {x.get('license', '').upper()} {x.get('license_version', '')}".strip()
            return {"octets": img.content, "legende": f"Photo : {x.get('creator') or 'auteur inconnu'}, {licence}, via Openverse",
                    "page": x.get("foreign_landing_url", "")}
    return None


def photo_libre(sujet: str) -> dict | None:
    """Vraie photo libre de droits avec son crédit : Wikimedia Commons, puis Wikipédia, puis Openverse."""
    for source in (_photo_commons, _photo_wikipedia, _photo_openverse):
        try:
            p = source(sujet)
            if p:
                return p
        except (KeyError, ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------- PDF
EMOJIS = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F]")


def _propre(t: str) -> str:
    """La police couvre le français et bien plus, mais pas les emojis."""
    return EMOJIS.sub("", t).replace("__", "")


class _PDF(FPDF):
    titre_doc = ""

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("dejavu", "", 8)
        self.set_text_color(120, 120, 130)
        self.cell(0, 8, self.titre_doc[:90], align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-14)
        self.set_font("dejavu", "", 8)
        self.set_text_color(120, 120, 130)
        self.cell(0, 8, f"Créé avec B.AI · page {self.page_no()}/{{nb}}", align="C")


def creer_pdf(titre: str, contenu: str, image: bytes | None = None) -> bytes:
    pdf = _PDF(format="A4")
    pdf.titre_doc = titre
    pdf.add_font("dejavu", "", POLICE)
    pdf.add_font("dejavu", "B", POLICE_GRAS)
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    # bandeau de titre
    pdf.set_fill_color(11, 11, 15)
    pdf.rect(0, 0, 210, 46, "F")
    if os.path.exists(LOGO):
        pdf.image(LOGO, x=18, y=9, h=28)
    pdf.set_xy(42, 13)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("dejavu", "B", 20)
    pdf.multi_cell(150, 9, _propre(titre)[:120])
    pdf.set_xy(42, 35)
    pdf.set_font("dejavu", "", 9)
    pdf.set_text_color(190, 190, 200)
    pdf.cell(0, 5, f"B.AI · {date_longue(datetime.now(ZoneInfo(FUSEAU_DEFAUT)))}")
    pdf.set_y(56)
    pdf.set_text_color(25, 25, 32)
    if image:
        try:
            im = Image.open(io.BytesIO(image)).convert("RGB")
            tampon = io.BytesIO()
            im.save(tampon, "JPEG", quality=85)
            largeur = 174
            hauteur = largeur * im.height / im.width
            if hauteur > 110:
                hauteur, largeur = 110, 110 * im.width / im.height
            pdf.image(tampon, x=(210 - largeur) / 2, w=largeur)
            pdf.ln(6)
        except Exception:
            pass
    for ligne in _propre(contenu).replace("\r", "").split("\n"):
        l = ligne.rstrip()
        if not l.strip():
            pdf.ln(3)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", l)
        if m:
            pdf.ln(2)
            pdf.set_font("dejavu", "B", {1: 16, 2: 14, 3: 12}[len(m.group(1))])
            pdf.multi_cell(0, 8, m.group(2).replace("**", ""))
            pdf.ln(1)
            continue
        puce = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)", l)
        pdf.set_font("dejavu", "", 11)
        if puce:
            pdf.set_x(24)
            pdf.multi_cell(0, 6.4, "• " + puce.group(1), markdown=True)
        else:
            pdf.multi_cell(0, 6.4, l, markdown=True)
    return bytes(pdf.output())


# ---------------------------------------------------------------- PowerPoint
NOIR, BLANC, GRIS, ACCENT = RGBColor(11, 11, 15), RGBColor(255, 255, 255), RGBColor(170, 170, 185), RGBColor(157, 140, 255)


def _fond(diapo, couleur):
    f = diapo.background.fill
    f.solid()
    f.fore_color.rgb = couleur


def _texte(diapo, x, y, w, h, texte, taille, couleur, gras=False):
    boite = diapo.shapes.add_textbox(x, y, w, h)
    tf = boite.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = texte
    p.font.size, p.font.bold, p.font.color.rgb = Pt(taille), gras, couleur
    return tf


def creer_pptx(titre: str, diapos: list[dict], image: bytes | None = None) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    vide = prs.slide_layouts[6]
    # couverture
    d = prs.slides.add_slide(vide)
    _fond(d, NOIR)
    if os.path.exists(LOGO):
        d.shapes.add_picture(LOGO, Inches(0.8), Inches(0.7), height=Inches(1.6))
    _texte(d, Inches(0.8), Inches(2.9), Inches(11.5), Inches(2.4), titre, 46, BLANC, True)
    _texte(d, Inches(0.8), Inches(6.3), Inches(11), Inches(0.6),
           f"Préparé avec B.AI · {date_longue(datetime.now(ZoneInfo(FUSEAU_DEFAUT)))}", 14, GRIS)
    # contenu
    for i, s in enumerate(diapos or [], start=1):
        d = prs.slides.add_slide(vide)
        _fond(d, RGBColor(250, 250, 252))
        barre = d.shapes.add_shape(1, 0, 0, Inches(0.25), prs.slide_height)
        barre.fill.solid()
        barre.fill.fore_color.rgb = ACCENT
        barre.line.fill.background()
        _texte(d, Inches(0.8), Inches(0.6), Inches(11.5), Inches(1.2), str(s.get("titre", "")), 34, NOIR, True)
        tf = _texte(d, Inches(0.8), Inches(1.9), Inches(11.6), Inches(5), "", 20, NOIR)
        points = [str(p) for p in (s.get("points") or [])][:8]
        for j, pt in enumerate(points):
            p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
            p.text = "•  " + pt
            p.font.size, p.font.color.rgb = Pt(22 if len(points) <= 5 else 18), RGBColor(30, 30, 40)
            p.space_after = Pt(10)
        _texte(d, Inches(11.6), Inches(6.85), Inches(1.4), Inches(0.4), str(i + 1), 12, GRIS)
    if image:
        try:
            im = Image.open(io.BytesIO(image))
            d = prs.slides.add_slide(vide)
            _fond(d, NOIR)
            h = Inches(6.3)
            w = Emu(int(h * im.width / im.height))
            if w > Inches(12.3):
                w = Inches(12.3)
                h = Emu(int(w * im.height / im.width))
            d.shapes.add_picture(io.BytesIO(image), int((prs.slide_width - w) / 2), int((prs.slide_height - h) / 2), w, h)
        except Exception:
            pass
    tampon = io.BytesIO()
    prs.save(tampon)
    return tampon.getvalue()


def nom_fichier(titre: str, ext: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", titre.lower()).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", sans_accents).strip("-")[:40]
    return f"{base or 'document'}-bai.{ext}"
