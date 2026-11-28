"""Le cerveau de B.AI : consignes, description des outils et boucle de réponse.

Le modèle (DeepSeek, compatible OpenAI) choisit lui-même ses outils grâce aux appels de
fonctions. La réponse arrive mot à mot. Tout ce que les outils produisent pendant un tour
(images, fichiers, sources, étapes, suggestions) est rangé dans un objet `Tour`.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

import outils

NOM = "B.AI"
MAX_TOURS_OUTILS = 5
MAX_HISTORIQUE = 24  # messages gardés pour le contexte
MAX_ILLUSTRATIONS = 6
SUGG = ">>>"  # ligne finale de la réponse : >>> question 1 | question 2 | question 3

ILLUSTRATION = {"type": "object", "properties": {
    "source": {"type": "string", "enum": ["ia", "photo", "galerie"],
               "description": "ia = image créée par IA (scène, illustration) ; photo = vraie photo ou schéma libre de droits "
                              "(lieu, monument, animal, schéma scientifique) ; galerie = image déjà montrée dans la discussion"},
    "description_en": {"type": "string",
                       "description": "ia : description précise en anglais (sujet, détails, style, cadrage ; jamais de texte dans l'image). "
                                      "photo : sujet en 2 à 5 mots anglais ; ajoute « diagram » pour un schéma (ex. « human arm bones diagram »)."},
    "numero": {"type": "integer", "description": "galerie : numéro de l'image (Image 1, Image 2…)"},
    "legende": {"type": "string", "description": "Légende courte en français"}},
    "required": ["source"]}

OUTILS = [
    {"type": "function", "function": {
        "name": "meteo", "description": "Météo actuelle et des 3 prochains jours pour une ville.",
        "parameters": {"type": "object", "properties": {"ville": {"type": "string", "description": "Nom de la ville, ex. Dakar"}},
                       "required": ["ville"]}}},
    {"type": "function", "function": {
        "name": "heure", "description": "Heure et date exactes, à Dakar par défaut ou dans une autre ville.",
        "parameters": {"type": "object", "properties": {"ville": {"type": "string", "description": "Ville (facultatif)"}}}}},
    {"type": "function", "function": {
        "name": "recherche_web", "description": "Cherche sur internet : actualités, faits récents, prix, dates, informations que tu ne connais pas avec certitude.",
        "parameters": {"type": "object", "properties": {
            "requete": {"type": "string", "description": "Mots-clés de recherche"},
            "actualites": {"type": "boolean", "description": "true pour les actualités récentes"}},
            "required": ["requete"]}}},
    {"type": "function", "function": {
        "name": "creer_image", "description": "Crée une image originale avec l'IA : scène, illustration, affiche, personnage imaginaire. "
                                              "Pour un vrai lieu, un monument, un animal ou un schéma scientifique, préfère photo_reelle.",
        "parameters": {"type": "object", "properties": {
            "description_en": {"type": "string", "description": "Description précise EN ANGLAIS : sujet principal, détails importants, "
                                                                "style (realistic photo, illustration, watercolor…), cadrage, ambiance. Jamais de texte dans l'image."},
            "format_image": {"type": "string", "enum": ["carre", "portrait", "paysage"]}},
            "required": ["description_en"]}}},
    {"type": "function", "function": {
        "name": "photo_reelle", "description": "Trouve une vraie photo ou un schéma libre de droits (Wikimedia, Wikipédia, Openverse), "
                                               "avec le nom de l'auteur. Idéal pour lieux, monuments, animaux, plantes, objets, schémas d'anatomie ou de sciences.",
        "parameters": {"type": "object", "properties": {"sujet_en": {"type": "string", "description": "Sujet en 2 à 5 mots, en anglais ; ajoute « diagram » pour un schéma"}},
                       "required": ["sujet_en"]}}},
    {"type": "function", "function": {
        "name": "creer_pdf", "description": "Crée un document PDF téléchargeable (fiche, cours, lettre, CV, exposé, résumé), avec des illustrations si utile. "
                                            "Écris le contenu complet en Markdown simple (# titres, - listes, **gras**). "
                                            "Pour placer l'illustration n°1, 2… à un endroit précis, mets une ligne seule [[image 1]], [[image 2]]…",
        "parameters": {"type": "object", "properties": {
            "titre": {"type": "string"},
            "contenu": {"type": "string", "description": "Texte complet du document en Markdown simple, avec les lignes [[image N]]"},
            "illustrations": {"type": "array", "maxItems": MAX_ILLUSTRATIONS, "items": ILLUSTRATION}},
            "required": ["titre", "contenu"]}}},
    {"type": "function", "function": {
        "name": "creer_powerpoint", "description": "Crée une présentation PowerPoint téléchargeable, avec une illustration sur les diapositives qui en ont besoin.",
        "parameters": {"type": "object", "properties": {
            "titre": {"type": "string"},
            "couverture": {**ILLUSTRATION, "description": "Facultatif : image de la couverture"},
            "diapos": {"type": "array", "description": "De 3 à 10 diapositives", "items": {"type": "object", "properties": {
                "titre": {"type": "string"},
                "points": {"type": "array", "items": {"type": "string"}, "description": "3 à 6 points courts"},
                "illustration": {**ILLUSTRATION, "description": "Facultatif : image de cette diapositive"}},
                "required": ["titre", "points"]}}},
            "required": ["titre", "diapos"]}}},
    {"type": "function", "function": {
        "name": "retenir", "description": "Retient une information utile sur la personne pour la suite de la discussion (prénom, études, ville, projet). Seulement si elle le dit ou le demande.",
        "parameters": {"type": "object", "properties": {"fait": {"type": "string", "description": "Une phrase courte"}},
                       "required": ["fait"]}}},
]

ETIQUETTES = {"meteo": "🌤️ Météo", "heure": "🕒 Heure", "recherche_web": "🔍 Recherche web", "creer_image": "🎨 Image IA",
              "photo_reelle": "📷 Photo libre", "creer_pdf": "📄 PDF", "creer_powerpoint": "📊 PowerPoint", "retenir": "🧠 Mémoire"}


@dataclass
class Tour:
    """Ce qu'un tour de réponse produit, en plus du texte."""
    memoire: list
    galerie: list  # images de la discussion : {"octets", "legende", "description", "source", "lien"}
    pieces: list = field(default_factory=list)
    etapes: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


def consignes(memoire: list[str], document: str = "", nom_document: str = "", galerie: list | None = None) -> str:
    maintenant = datetime.now(ZoneInfo(outils.FUSEAU_DEFAUT))
    txt = f"""Tu es {NOM}, un assistant IA sénégalais : chaleureux, drôle, un peu taquin, et très compétent.
Nous sommes le {outils.date_longue(maintenant)}, il est {maintenant:%H:%M} à Dakar.

Ta façon de parler
- Réponds dans la langue de la personne (français, anglais, ou wolof simple si elle t'écrit en wolof).
- Va droit au but : une réponse claire, puis le détail utile. Des listes courtes quand ça aide. Pas de remplissage.
- Une touche d'humour ou une expression sénégalaise de temps en temps, jamais aux dépens de la personne.
- Tutoie si on te tutoie.

Tes outils
- Tu as de vrais outils : météo, heure, recherche web, image IA, photo libre, PDF, PowerPoint, mémoire. Utilise-les dès qu'ils servent la demande.
- Pour un fichier ou une image, appelle toujours l'outil : ne dis jamais qu'un fichier est prêt si l'outil n'a pas répondu qu'il l'est.
- Si un outil échoue, dis-le simplement et propose une autre solution.
- Après une recherche web, appuie-toi sur les sources (elles s'affichent sous ta réponse).

Images
- Choisis la bonne source : un vrai lieu, un monument, un animal, une plante ou un schéma scientifique → photo_reelle ;
  une scène, une illustration, une affiche ou quelque chose d'imaginaire → creer_image.
- Pour creer_image, écris une description anglaise précise et fidèle à la demande (sujet, détails, style, cadrage). L'IA écrit mal le texte : n'en demande jamais dans l'image.
- Montre ce que tu as obtenu sans exagérer : si l'image ne correspond pas exactement, dis-le et propose une autre version.

Documents (PDF, PowerPoint)
- Écris toi-même un contenu complet, structuré et soigné.
- Ajoute des illustrations quand elles aident à comprendre (schémas pour un cours, photos pour un exposé) : 1 à 4 dans un PDF, sur 2 à 4 diapositives dans un PowerPoint.
- Pour une image déjà montrée dans la discussion, utilise source « galerie » avec son numéro.
- N'écris jamais de schéma avec des caractères (|, —, ->) : demande plutôt un vrai schéma (photo_reelle avec « diagram »).
- Ne dis jamais à la personne d'ajouter elle-même les images.

Fin de chaque réponse
- Termine par une dernière ligne seule qui commence par {SUGG} et propose 2 ou 3 suites courtes que la personne pourrait demander, séparées par |
  (exemple : {SUGG} Fais-en un PDF | Explique plus simplement | Donne-moi un quiz). Cette ligne est cachée et devient des boutons.

Ce que tu sais aussi faire
- Coach d'études pour les élèves et étudiants d'Afrique francophone (application My Futur) : orientation après le bac, révisions, méthodes de travail, lettres de motivation, budget étudiant.
- Pour les dates, frais et conditions d'admission, conseille de vérifier sur le site officiel de l'établissement. N'invente jamais un site ou un chiffre.

Honnêteté
- Si tu ne sais pas, dis-le, ou fais une recherche web.
- Ne demande jamais de mot de passe ni d'informations bancaires.
"""
    if galerie:
        txt += "\nImages déjà montrées dans cette discussion (réutilisables avec source « galerie ») :\n" + "\n".join(
            f"- Image {i}: {g.get('description') or g.get('legende', '')}"[:160] for i, g in enumerate(galerie, start=1)) + "\n"
    if memoire:
        txt += "\nCe que tu sais de la personne (retenu pendant cette session) :\n" + "\n".join(f"- {m}" for m in memoire) + "\n"
    if document:
        txt += f"\nDocument fourni par la personne ({nom_document}). Appuie-toi dessus quand la question s'y rapporte :\n<<<\n{document}\n>>>\n"
    return txt


# ---------------------------------------------------------------- images
def _ajouter_galerie(tour: Tour, octets: bytes, legende: str, description: str, source: str, lien: str = "") -> int:
    tour.galerie.append({"octets": octets, "legende": legende, "description": description, "source": source, "lien": lien})
    del tour.galerie[:-20]
    return len(tour.galerie)


def obtenir_illustration(spec: dict, tour: Tour, format_ia: str = "paysage") -> dict | None:
    """Une illustration pour un document : {octets, legende} ou None."""
    if not isinstance(spec, dict):
        return None
    source = str(spec.get("source", "ia"))
    desc = str(spec.get("description_en", "")).strip()
    legende = str(spec.get("legende", "")).strip()
    if source == "galerie":
        try:
            g = tour.galerie[int(spec.get("numero", 0)) - 1]
        except (ValueError, IndexError):
            return None
        return {"octets": g["octets"], "legende": legende or g.get("legende", "")}
    if not desc:
        return None
    if source == "photo":
        p = outils.photo_libre(desc)
        if p:
            return {"octets": p["octets"], "legende": (legende + " — " if legende else "") + p["legende"]}
        source = "ia"  # pas de photo fiable : on dessine plutôt que de mettre une image hors sujet
        if "diagram" in desc.lower():
            desc += ", clean educational illustration, no text, no labels"
    img = outils.image_ia(desc, format_ia)
    return {"octets": img, "legende": legende or "Illustration créée par IA"} if img else None


def _illustrations(specs: list, tour: Tour, format_ia: str = "paysage") -> list:
    """Prépare plusieurs illustrations en même temps (bien plus rapide qu'une par une)."""
    specs = list(specs or [])[:MAX_ILLUSTRATIONS]
    if not specs:
        return []
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(lambda s: obtenir_illustration(s, tour, format_ia), specs))


def _sources(texte: str) -> list[dict]:
    res = []
    for m in re.finditer(r"^- (.+?) : .*\[(https?://[^\]\s]+)\]\s*$", texte, re.M):
        res.append({"titre": m.group(1)[:90], "url": m.group(2)})
    return res


# ---------------------------------------------------------------- outils
def executer(nom: str, args: dict, tour: Tour) -> str:
    """Exécute un outil et renvoie un texte court pour le modèle."""
    try:
        if nom == "meteo":
            return outils.meteo(str(args.get("ville", "Dakar")))
        if nom == "heure":
            return outils.heure(str(args.get("ville", "")))
        if nom == "recherche_web":
            r = outils.recherche_web(str(args.get("requete", "")), bool(args.get("actualites")))
            for s in _sources(r):
                if s["url"] not in {x["url"] for x in tour.sources}:
                    tour.sources.append(s)
            return r
        if nom == "creer_image":
            desc = str(args.get("description_en", "")).strip()
            fmt = str(args.get("format_image", "carre"))
            img = outils.image_ia(desc, fmt)
            if not img:  # plan B : le navigateur de la personne charge l'image lui-même
                tour.pieces.append({"type": "image", "url": outils.lien_image_ia(desc, fmt), "legende": desc[:140],
                                    "description": desc, "format": fmt, "ia": True})
                return "Le service d'images était saturé : l'image se charge directement sous ta réponse (quelques secondes). Décris-la en une phrase."
            n = _ajouter_galerie(tour, img, "Image créée par IA", desc, "ia")
            tour.pieces.append({"type": "image", "octets": img, "legende": f"Image {n} · créée par IA", "description": desc,
                                "format": fmt, "ia": True, "nom": outils.nom_fichier(desc[:40], "jpg")})
            return f"Image {n} créée et affichée sous ta réponse. Décris-la en une phrase, sans lien."
        if nom == "photo_reelle":
            sujet = str(args.get("sujet_en", "")).strip()
            p = outils.photo_libre(sujet)
            if not p:
                return ("Aucune photo libre qui corresponde vraiment au sujet. Dis-le simplement et propose une image "
                        "créée par IA à la place (sans l'appeler tant que la personne n'a pas accepté).")
            n = _ajouter_galerie(tour, p["octets"], p["legende"], sujet, "photo", p.get("page", ""))
            tour.pieces.append({"type": "image", "octets": p["octets"], "legende": f"Image {n} · {p['legende']}", "lien": p["page"],
                                "nom": outils.nom_fichier(sujet or "photo", "jpg")})
            return f"Image {n} affichée sous ta réponse (fichier « {p.get('titre', '')} »). Crédit : {p['legende']}."
        if nom == "creer_pdf":
            titre = str(args.get("titre", "Document"))
            specs = args.get("illustrations") or []
            illus = _illustrations(specs, tour)
            data = outils.creer_pdf(titre, str(args.get("contenu", "")), illus)
            tour.pieces.append({"type": "fichier", "octets": data, "nom": outils.nom_fichier(titre, "pdf"), "mime": "application/pdf"})
            ok = sum(1 for x in illus if x)
            manque = len(specs) - ok
            return (f"PDF créé avec {ok} illustration(s) : le bouton de téléchargement est sous ta réponse."
                    + (f" {manque} illustration(s) n'ont pas pu être obtenues (services d'images saturés) : dis-le en une phrase." if manque > 0 else ""))
        if nom == "creer_powerpoint":
            titre = str(args.get("titre", "Présentation"))
            diapos = args.get("diapos") or []
            if not isinstance(diapos, list) or not diapos:
                return "Échec : il faut au moins une diapositive avec un titre et des points."
            demandes = [(i, d.get("illustration")) for i, d in enumerate(diapos, start=1) if isinstance(d, dict) and d.get("illustration")]
            couv = args.get("couverture")
            specs = ([couv] if couv else []) + [s for _, s in demandes]
            obtenues = _illustrations(specs, tour, "paysage")
            couverture = obtenues.pop(0) if couv else None
            par_diapo = {i: img for (i, _), img in zip(demandes, obtenues) if img}
            data = outils.creer_pptx(titre, diapos, par_diapo, couverture)
            tour.pieces.append({"type": "fichier", "octets": data, "nom": outils.nom_fichier(titre, "pptx"),
                                "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"})
            ok = len(par_diapo) + (1 if couverture else 0)
            manque = len(specs) - ok
            return (f"PowerPoint de {len(diapos) + 1} diapositives créé, avec {ok} illustration(s) : le bouton de téléchargement est sous ta réponse."
                    + (f" {manque} illustration(s) n'ont pas pu être obtenues (services d'images saturés) : dis-le en une phrase." if manque > 0 else ""))
        if nom == "retenir":
            fait = str(args.get("fait", "")).strip()[:200]
            if fait and fait not in tour.memoire:
                tour.memoire.append(fait)
                del tour.memoire[:-15]
            return "C'est retenu."
        return f"Outil inconnu : {nom}."
    except Exception as e:  # un outil ne doit jamais faire tomber la conversation
        return f"Échec de l'outil {nom} : {type(e).__name__}."


# ---------------------------------------------------------------- boucle de réponse
def repondre(client, modele: str, historique: list[dict], systeme: str, temperature: float,
             tour: Tour, signaler: Callable[[str], None]) -> Iterator[str]:
    """Générateur : renvoie la réponse mot à mot, exécute les outils demandés et cache la ligne des suggestions."""
    messages = [{"role": "system", "content": systeme}] + historique[-MAX_HISTORIQUE:]
    for _ in range(MAX_TOURS_OUTILS + 1):
        flux = client.chat.completions.create(model=modele, messages=messages, tools=OUTILS,
                                              temperature=temperature, stream=True)
        texte, envoye, appels = "", 0, {}
        for morceau in flux:
            if not morceau.choices:
                continue
            delta = morceau.choices[0].delta
            if delta.content:
                texte += delta.content
                coupe = texte.find(SUGG)
                limite = coupe if coupe >= 0 else len(texte.rstrip(">"))  # retient un « > » qui pourrait commencer >>>
                if limite > envoye:
                    yield texte[envoye:limite]
                    envoye = limite
            for tc in delta.tool_calls or []:
                a = appels.setdefault(tc.index, {"id": "", "nom": "", "args": ""})
                if tc.id:
                    a["id"] = tc.id
                if tc.function and tc.function.name:
                    a["nom"] += tc.function.name
                if tc.function and tc.function.arguments:
                    a["args"] += tc.function.arguments
        coupe = texte.find(SUGG)
        if coupe >= 0:
            tour.suggestions = [s.strip(" .") for s in texte[coupe + len(SUGG):].split("|") if s.strip(" .")][:3]
        elif len(texte) > envoye:
            yield texte[envoye:]
        if not appels:
            return
        if texte and not texte.endswith("\n"):
            yield "\n\n"
        messages.append({"role": "assistant", "content": texte, "tool_calls": [
            {"id": a["id"], "type": "function", "function": {"name": a["nom"], "arguments": a["args"] or "{}"}}
            for a in appels.values()]})
        for a in appels.values():
            try:
                args = json.loads(a["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            etiquette = ETIQUETTES.get(a["nom"], a["nom"])
            signaler(f"{etiquette}…")
            resultat = executer(a["nom"], args, tour)
            tour.etapes.append(f"{etiquette} · {resultat.split('.')[0][:90]}")
            messages.append({"role": "tool", "tool_call_id": a["id"], "content": resultat})
    yield "\n\n(J'ai enchaîné trop d'outils d'un coup. Reformule ta demande, je reprends.)"
