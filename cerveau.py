"""Le cerveau de B.AI : consignes, description des outils et boucle de réponse.

Le modèle (DeepSeek, compatible OpenAI) choisit lui-même ses outils grâce aux appels de
fonctions. La réponse arrive mot à mot ; les images et fichiers produits sont rangés dans
`pieces` pour être affichés sous la réponse.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

import outils

NOM = "B.AI"
MAX_TOURS_OUTILS = 5
MAX_HISTORIQUE = 24  # messages gardés pour le contexte

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
        "name": "creer_image", "description": "Génère une image originale avec l'IA (dessin, illustration, affiche, scène imaginaire).",
        "parameters": {"type": "object", "properties": {
            "description_en": {"type": "string", "description": "Description détaillée de l'image, EN ANGLAIS"},
            "format_image": {"type": "string", "enum": ["carre", "portrait", "paysage"]}},
            "required": ["description_en"]}}},
    {"type": "function", "function": {
        "name": "photo_reelle", "description": "Trouve une vraie photo libre de droits (Wikimedia Commons) d'un lieu, monument, animal, objet ou personnage historique.",
        "parameters": {"type": "object", "properties": {"sujet_en": {"type": "string", "description": "Sujet en 2 à 4 mots, en anglais"}},
                       "required": ["sujet_en"]}}},
    {"type": "function", "function": {
        "name": "creer_pdf", "description": "Crée un document PDF téléchargeable (fiche, lettre, CV, exposé, résumé). Écris le contenu complet, en Markdown simple (# titres, - listes, **gras**).",
        "parameters": {"type": "object", "properties": {
            "titre": {"type": "string"},
            "contenu": {"type": "string", "description": "Texte complet du document en Markdown simple"},
            "image_en": {"type": "string", "description": "Facultatif : description EN ANGLAIS d'une illustration à générer et à placer en haut"}},
            "required": ["titre", "contenu"]}}},
    {"type": "function", "function": {
        "name": "creer_powerpoint", "description": "Crée une présentation PowerPoint téléchargeable de plusieurs diapositives.",
        "parameters": {"type": "object", "properties": {
            "titre": {"type": "string"},
            "diapos": {"type": "array", "description": "De 3 à 10 diapositives", "items": {"type": "object", "properties": {
                "titre": {"type": "string"},
                "points": {"type": "array", "items": {"type": "string"}, "description": "3 à 6 points courts"}},
                "required": ["titre", "points"]}},
            "image_en": {"type": "string", "description": "Facultatif : description EN ANGLAIS d'une illustration pour la dernière diapositive"}},
            "required": ["titre", "diapos"]}}},
    {"type": "function", "function": {
        "name": "retenir", "description": "Retient une information utile sur la personne pour la suite de la discussion (prénom, études, ville, projet). Seulement si elle le dit ou le demande.",
        "parameters": {"type": "object", "properties": {"fait": {"type": "string", "description": "Une phrase courte"}},
                       "required": ["fait"]}}},
]

ETIQUETTES = {"meteo": "🌤️ Météo", "heure": "🕒 Heure", "recherche_web": "🔍 Recherche web", "creer_image": "🎨 Image IA",
              "photo_reelle": "📷 Photo libre", "creer_pdf": "📄 PDF", "creer_powerpoint": "📊 PowerPoint", "retenir": "🧠 Mémoire"}


def consignes(memoire: list[str], document: str = "", nom_document: str = "") -> str:
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
- Après une recherche web, cite tes sources avec leurs liens.
- Pour un PDF ou un PowerPoint, écris toi-même un contenu complet, structuré et soigné.

Ce que tu sais aussi faire
- Coach d'études pour les élèves et étudiants d'Afrique francophone (application My Futur) : orientation après le bac, révisions, méthodes de travail, lettres de motivation, budget étudiant.
- Pour les dates, frais et conditions d'admission, conseille de vérifier sur le site officiel de l'établissement. N'invente jamais un site ou un chiffre.

Honnêteté
- Si tu ne sais pas, dis-le, ou fais une recherche web.
- Ne demande jamais de mot de passe ni d'informations bancaires.
"""
    if memoire:
        txt += "\nCe que tu sais de la personne (retenu pendant cette session) :\n" + "\n".join(f"- {m}" for m in memoire) + "\n"
    if document:
        txt += f"\nDocument fourni par la personne ({nom_document}). Appuie-toi dessus quand la question s'y rapporte :\n<<<\n{document}\n>>>\n"
    return txt


def executer(nom: str, args: dict, pieces: list, memoire: list[str]) -> str:
    """Exécute un outil et renvoie un texte court pour le modèle."""
    try:
        if nom == "meteo":
            return outils.meteo(str(args.get("ville", "Dakar")))
        if nom == "heure":
            return outils.heure(str(args.get("ville", "")))
        if nom == "recherche_web":
            return outils.recherche_web(str(args.get("requete", "")), bool(args.get("actualites")))
        if nom == "creer_image":
            desc = str(args.get("description_en", ""))
            fmt = str(args.get("format_image", "carre"))
            img = outils.image_ia(desc, fmt)
            if not img:  # plan B : le navigateur de la personne charge l'image lui-même
                pieces.append({"type": "image", "url": outils.lien_image_ia(desc, fmt), "legende": desc[:120]})
                return "Le service d'images était lent : l'image se charge directement sous ta réponse (quelques secondes). Décris-la en une phrase."
            pieces.append({"type": "image", "octets": img, "legende": desc[:120], "nom": outils.nom_fichier(desc[:40], "jpg")})
            return "Image générée et affichée sous ta réponse. Décris-la en une phrase, sans lien."
        if nom == "photo_reelle":
            p = outils.photo_libre(str(args.get("sujet_en", "")))
            if not p:
                return "Aucune photo libre trouvée (sujet introuvable ou banques de photos saturées). Dis-le simplement et propose une image générée par IA à la place."
            pieces.append({"type": "image", "octets": p["octets"], "legende": p["legende"], "lien": p["page"],
                           "nom": outils.nom_fichier(str(args.get("sujet_en", "photo")), "jpg")})
            return f"Photo affichée sous ta réponse. Crédit à mentionner : {p['legende']}."
        if nom == "creer_pdf":
            titre = str(args.get("titre", "Document"))
            img = outils.image_ia(str(args["image_en"]), "paysage") if args.get("image_en") else None
            data = outils.creer_pdf(titre, str(args.get("contenu", "")), img)
            pieces.append({"type": "fichier", "octets": data, "nom": outils.nom_fichier(titre, "pdf"), "mime": "application/pdf"})
            return "PDF créé : le bouton de téléchargement est sous ta réponse." + ("" if img or not args.get("image_en") else " (L'illustration n'a pas pu être générée.)")
        if nom == "creer_powerpoint":
            titre = str(args.get("titre", "Présentation"))
            diapos = args.get("diapos") or []
            if not isinstance(diapos, list) or not diapos:
                return "Échec : il faut au moins une diapositive avec un titre et des points."
            img = outils.image_ia(str(args["image_en"]), "paysage") if args.get("image_en") else None
            data = outils.creer_pptx(titre, diapos, img)
            pieces.append({"type": "fichier", "octets": data, "nom": outils.nom_fichier(titre, "pptx"),
                           "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation"})
            return f"PowerPoint de {len(diapos) + 1} diapositives créé : le bouton de téléchargement est sous ta réponse."
        if nom == "retenir":
            fait = str(args.get("fait", "")).strip()[:200]
            if fait and fait not in memoire:
                memoire.append(fait)
                del memoire[:-15]
            return "C'est retenu."
        return f"Outil inconnu : {nom}."
    except Exception as e:  # un outil ne doit jamais faire tomber la conversation
        return f"Échec de l'outil {nom} : {type(e).__name__}."


def repondre(client, modele: str, historique: list[dict], systeme: str, temperature: float,
             pieces: list, memoire: list[str], signaler: Callable[[str], None]) -> Iterator[str]:
    """Générateur : renvoie la réponse mot à mot, en exécutant les outils demandés au passage."""
    messages = [{"role": "system", "content": systeme}] + historique[-MAX_HISTORIQUE:]
    for _ in range(MAX_TOURS_OUTILS + 1):
        flux = client.chat.completions.create(model=modele, messages=messages, tools=OUTILS,
                                              temperature=temperature, stream=True)
        texte, appels = "", {}
        for morceau in flux:
            if not morceau.choices:
                continue
            delta = morceau.choices[0].delta
            if delta.content:
                texte += delta.content
                yield delta.content
            for tc in delta.tool_calls or []:
                a = appels.setdefault(tc.index, {"id": "", "nom": "", "args": ""})
                if tc.id:
                    a["id"] = tc.id
                if tc.function and tc.function.name:
                    a["nom"] += tc.function.name
                if tc.function and tc.function.arguments:
                    a["args"] += tc.function.arguments
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
            signaler(f"{ETIQUETTES.get(a['nom'], a['nom'])}…")
            messages.append({"role": "tool", "tool_call_id": a["id"], "content": executer(a["nom"], args, pieces, memoire)})
    yield "\n\n(J'ai enchaîné trop d'outils d'un coup. Reformule ta demande, je reprends.)"
