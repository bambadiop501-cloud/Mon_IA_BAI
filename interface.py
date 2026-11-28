"""B.AI : interface de discussion (Streamlit).

Lancer en local :   streamlit run interface.py
Clé DeepSeek : dans .streamlit/secrets.toml (DEEPSEEK_API_KEY = "...") ou dans la variable
d'environnement DEEPSEEK_API_KEY. Jamais dans le code.
"""
from __future__ import annotations

import base64
import html
import io
import os
import random
import time
from urllib.parse import urlparse

import streamlit as st
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
                    OpenAI, RateLimitError)
from pypdf import PdfReader

import cerveau
import outils

ICI = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(ICI, "logo.png")
LOGO_PETIT = os.path.join(ICI, "logo-petit.png")
AVATAR_IA = LOGO_PETIT if os.path.exists(LOGO_PETIT) else LOGO
AVATAR_MOI = "🧑🏾‍💻"
MAX_CARACTERES_DOC = 20000
MAX_DISCUSSIONS = 12


def config(nom: str, defaut: str = "") -> str:
    """Lit un réglage dans les secrets Streamlit, sinon dans l'environnement."""
    try:
        valeur = st.secrets.get(nom)
    except Exception:  # pas de fichier secrets.toml
        valeur = None
    return str(valeur or os.environ.get(nom) or defaut)


CLE = config("DEEPSEEK_API_KEY")
MODELE = config("DEEPSEEK_MODEL", "deepseek-chat")
ADRESSE = config("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
for _nom in ("HF_TOKEN", "TAVILY_API_KEY"):  # facultatifs : secours pour les images IA et la recherche web
    if config(_nom):
        os.environ[_nom] = config(_nom)

st.set_page_config(page_title=cerveau.NOM, page_icon=AVATAR_IA, layout="centered")


@st.cache_resource
def client_ia(cle: str, adresse: str) -> OpenAI:
    return OpenAI(api_key=cle, base_url=adresse, timeout=120, max_retries=1)


@st.cache_data
def logo_base64() -> str:
    with open(AVATAR_IA, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------------------------------------------- état de la session (propre à chaque visiteur)
for cle, defaut in {"messages": [], "galerie": [], "memoire": [], "discussions": [], "action": None,
                    "doc_texte": "", "doc_nom": "", "doc_id": ""}.items():
    st.session_state.setdefault(cle, defaut)
S = st.session_state

# ---------------------------------------------------------------- style
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&display=swap');
@keyframes entree{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes lueur{0%,100%{filter:drop-shadow(0 0 6px rgba(255,255,255,.35))}50%{filter:drop-shadow(0 0 18px rgba(190,180,255,.75))}}
[data-testid="stChatMessage"]{border-radius:20px;padding:12px 14px;animation:entree .5s ease-out both;border:1px solid rgba(255,255,255,.06)}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){background:rgba(157,140,255,.10)}
.bai-tete{display:flex;align-items:center;gap:14px;margin:4px 0 6px}
.bai-tete img{width:54px;height:54px;object-fit:cover;border-radius:16px;animation:lueur 4s ease-in-out infinite}
.bai-tete h1{font-family:'Space Grotesk',sans-serif;font-size:2.3rem;margin:0;padding:0;letter-spacing:-.02em}
.bai-tete p{margin:0;opacity:.7;font-size:.95rem}
.bai-accueil{border:1px solid rgba(255,255,255,.08);border-radius:22px;padding:18px 20px;margin:8px 0 14px;
  background:radial-gradient(120% 140% at 0% 0%,rgba(157,140,255,.16),transparent 60%),rgba(255,255,255,.02)}
.bai-accueil b{font-family:'Space Grotesk',sans-serif;font-size:1.15rem}
.bai-sources{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px}
.bai-sources a{display:inline-flex;align-items:center;gap:6px;max-width:100%;padding:5px 11px;border-radius:999px;font-size:.8rem;
  text-decoration:none;color:inherit;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}
.bai-sources a:hover{border-color:#9D8CFF;background:rgba(157,140,255,.14)}
.bai-sources b{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:#9D8CFF;color:#0B0B0F;font-size:.7rem}
.bai-sources span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:190px}
.bai-etiquette{font-size:.78rem;opacity:.65;margin:8px 0 2px}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- documents joints
def lire_fichier(f) -> tuple[str, str]:
    """Renvoie (texte, message). PDF : 40 premières pages ; texte brut sinon."""
    nom = f.name
    try:
        if nom.lower().endswith(".pdf"):
            lecteur = PdfReader(io.BytesIO(f.getvalue()))
            morceaux = [(p.extract_text() or "") for p in lecteur.pages[:40]]
            texte = "\n".join(morceaux).strip()
            if not texte:
                return "", "Ce PDF ne contient pas de texte lisible (c'est peut-être un scan)."
            suite = f" (40 premières pages sur {len(lecteur.pages)})" if len(lecteur.pages) > 40 else ""
        else:
            texte, suite = f.getvalue().decode("utf-8", errors="replace"), ""
        if len(texte) > MAX_CARACTERES_DOC:
            texte, suite = texte[:MAX_CARACTERES_DOC], suite + " (début du document seulement)"
        return texte, f"Document lu : {nom}{suite}."
    except Exception as e:
        return "", f"Lecture impossible ({type(e).__name__})."


# ---------------------------------------------------------------- discussions (comme un historique de conversations)
def titre_discussion(messages: list) -> str:
    premier = next((m["content"] for m in messages if m["role"] == "user"), "Discussion")
    return (premier[:38] + "…") if len(premier) > 40 else premier


def ranger_discussion() -> None:
    if S.messages:
        S.discussions.insert(0, {"titre": titre_discussion(S.messages), "messages": S.messages, "galerie": S.galerie})
        del S.discussions[MAX_DISCUSSIONS:]
    S.messages, S.galerie, S.action = [], [], None


# ---------------------------------------------------------------- menu latéral
with st.sidebar:
    st.image(AVATAR_IA, width=56)
    if st.button("✨ Nouvelle discussion", use_container_width=True, type="primary"):
        ranger_discussion()
        st.rerun()
    if S.discussions:
        st.caption("Discussions récentes")
        for i, d in enumerate(list(S.discussions)):
            if st.button(f"💬 {d['titre']}", key=f"disc-{i}", use_container_width=True):
                choisie = S.discussions.pop(i)
                ranger_discussion()
                S.messages, S.galerie = choisie["messages"], choisie["galerie"]
                st.rerun()

    st.divider()
    with st.expander("⚙️ Réglages"):
        creativite = st.slider("Créativité", 0.0, 1.3, 0.7, 0.1, help="Bas : réponses précises. Haut : réponses plus inventives.")
    if S.galerie:
        with st.expander(f"🖼️ Images de la discussion ({len(S.galerie)})"):
            cols = st.columns(3)
            for i, g in enumerate(S.galerie, start=1):
                cols[(i - 1) % 3].image(g["octets"], caption=f"Image {i}")
    with st.expander("📄 Document", expanded=bool(S.doc_nom)):
        if S.doc_nom:
            st.caption(f"En cours : **{S.doc_nom}**")
            if st.button("Retirer le document", use_container_width=True):
                S.doc_texte = S.doc_nom = S.doc_id = ""
                st.rerun()
        else:
            st.caption("Joins un PDF ou un fichier texte avec le trombone, dans la barre de message.")
    with st.expander("🧠 Ce que B.AI retient", expanded=bool(S.memoire)):
        if S.memoire:
            for i, fait in enumerate(list(S.memoire)):
                c1, c2 = st.columns([5, 1])
                c1.caption(fait)
                if c2.button("✕", key=f"oubli-{i}", help="Oublier"):
                    S.memoire.pop(i)
                    st.rerun()
            if st.button("Tout oublier", use_container_width=True):
                S.memoire = []
                st.rerun()
        else:
            st.caption("Rien pour l'instant. Dis-lui par exemple « retiens que je suis en terminale ». "
                       "Cette mémoire reste propre à toi et s'efface quand tu fermes la page.")
    st.caption(f"{cerveau.NOM} 2.1 · modèle {MODELE}")


# ---------------------------------------------------------------- affichage d'un message
def afficher_sources(sources: list) -> None:
    if not sources:
        return
    puces = "".join(
        f'<a href="{html.escape(s["url"])}" target="_blank" rel="noopener" title="{html.escape(s["titre"])}">'
        f'<b>{i}</b><span>{html.escape(urlparse(s["url"]).netloc.replace("www.", ""))}</span></a>'
        for i, s in enumerate(sources[:8], start=1) if s["url"].startswith("http"))
    st.markdown(f'<div class="bai-etiquette">Sources</div><div class="bai-sources">{puces}</div>', unsafe_allow_html=True)


def afficher_pieces(pieces: list, prefixe: str, dernier: bool) -> None:
    for j, p in enumerate(pieces):
        if p["type"] == "image":
            with st.container(border=True):
                if p.get("octets"):
                    st.image(p["octets"], caption=p.get("legende", ""))
                else:
                    st.image(p["url"], caption=p.get("legende", ""))
                c1, c2, c3 = st.columns(3)
                if p.get("octets"):
                    c1.download_button("📥 Télécharger", p["octets"], file_name=p.get("nom", "image.jpg"), mime="image/jpeg",
                                       key=f"{prefixe}-dl-{j}", use_container_width=True)
                elif p.get("url"):
                    c1.link_button("🔗 Ouvrir", p["url"], use_container_width=True)
                if p.get("ia") and p.get("description") and c2.button("🔁 Autre version", key=f"{prefixe}-av-{j}", use_container_width=True):
                    S.action = {"type": "image", "description": p["description"], "format": p.get("format", "carre")}
                    st.rerun()
                if p.get("lien"):
                    c3.link_button("Source", p["lien"], use_container_width=True)
        elif p["type"] == "fichier":
            taille = len(p["octets"]) / 1024
            icone = "📄" if p["nom"].endswith(".pdf") else "📊"
            st.download_button(f"{icone} Télécharger {p['nom']} · {taille:.0f} Ko", p["octets"], file_name=p["nom"], mime=p["mime"],
                               key=f"{prefixe}-f-{j}", type="primary", use_container_width=True)


def choisir_suite(cle: str, choix: dict) -> None:
    """Pastille touchée sous la dernière réponse : régénérer ou poser la question proposée."""
    valeur = st.session_state.get(cle)
    if valeur in choix:
        S.action = choix[valeur]


def afficher_message(i: int, m: dict, dernier: bool) -> None:
    with st.chat_message(m["role"], avatar=AVATAR_MOI if m["role"] == "user" else AVATAR_IA):
        if m.get("etapes"):
            with st.expander(f"🛠️ {len(m['etapes'])} outil{'s' if len(m['etapes']) > 1 else ''} utilisé{'s' if len(m['etapes']) > 1 else ''}"):
                for e in m["etapes"]:
                    st.caption(e)
        if m.get("erreur"):
            st.error(m["content"])
        else:
            st.markdown(m["content"])
        afficher_sources(m.get("sources", []))
        afficher_pieces(m.get("pieces", []), f"m{i}", dernier)
        if dernier and m["role"] == "assistant":
            choix_suite = {"🔁 Régénérer": {"type": "regen"}}
            choix_suite.update({f"↳ {s}": {"type": "ask", "texte": s} for s in m.get("suggestions", [])})
            st.pills("Pour continuer", list(choix_suite), key=f"suite-{i}-{len(S.messages)}", label_visibility="collapsed",
                     on_change=choisir_suite, args=(f"suite-{i}-{len(S.messages)}", choix_suite))


# ---------------------------------------------------------------- en-tête et accueil
st.markdown(f"""<div class="bai-tete"><img src="data:image/png;base64,{logo_base64()}" alt="">
<div><h1>{cerveau.NOM}</h1><p>Ton assistant personnel : il cherche, explique, crée des PDF, des PowerPoint et des images.</p></div></div>""",
            unsafe_allow_html=True)

if not CLE:
    st.warning("La clé DeepSeek n'est pas encore réglée. Sur Streamlit Cloud : *Manage app → Settings → Secrets*, "
               "puis ajoute la ligne `DEEPSEEK_API_KEY = \"ta-clé\"`. En local : fichier `.streamlit/secrets.toml`.")

SUGGESTIONS = [("🌤️", "Quel temps fait-il à Dakar ?"), ("📊", "Fais-moi un PowerPoint illustré sur le recyclage au Sénégal"),
               ("🎓", "Aide-moi à choisir mes études après le bac"), ("📄", "Fais-moi une fiche PDF illustrée sur le cœur humain")]
choix = None
if not S.messages:
    st.markdown('<div class="bai-accueil"><b>Salut, moi c\'est B.AI 👋</b><br>Pose-moi une question, ou demande-moi un document, '
                'une présentation, une image. Je peux aussi lire tes PDF.</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (icone, s) in enumerate(SUGGESTIONS):
        if cols[i % 2].button(f"{icone}  {s}", key=f"sugg-{i}", use_container_width=True):
            choix = s

for i, m in enumerate(S.messages):
    afficher_message(i, m, dernier=(i == len(S.messages) - 1))

saisie = st.chat_input(f"Écris à {cerveau.NOM}…", accept_file=True, file_type=["pdf", "txt", "md"], disabled=not CLE)


# ---------------------------------------------------------------- actions des boutons (autre version, régénérer, suite)
def autre_version(action: dict) -> None:
    """Nouvelle version d'une image IA, sans repasser par le modèle."""
    desc, fmt = action["description"], action.get("format", "carre")
    with st.chat_message("assistant", avatar=AVATAR_IA):
        with st.spinner("🎨 Nouvelle version de l'image…"):
            img = outils.image_ia(f"{desc}, variation {random.randint(2, 999)}", fmt)
        tour = cerveau.Tour(S.memoire, S.galerie)
        if img:
            n = cerveau._ajouter_galerie(tour, img, "Image créée par IA", desc, "ia")
            piece = {"type": "image", "octets": img, "legende": f"Image {n} · créée par IA", "description": desc, "format": fmt,
                     "ia": True, "nom": outils.nom_fichier(desc[:40], "jpg")}
            texte = f"Voici une autre version (image {n})."
        else:
            piece = {"type": "image", "url": outils.lien_image_ia(desc, fmt) + f"&seed={random.randint(10, 9999)}",
                     "legende": desc[:140], "description": desc, "format": fmt, "ia": True}
            texte = "Le service d'images était saturé : la nouvelle version se charge directement ici."
    S.messages.append({"role": "assistant", "content": texte, "pieces": [piece]})
    st.rerun()


texte = choix
regenerer = False
action, S.action = S.action, None
if action:
    if action["type"] == "image":
        autre_version(action)
    elif action["type"] == "ask":
        texte = action["texte"]
    elif action["type"] == "regen" and S.messages and S.messages[-1]["role"] == "assistant":
        S.messages.pop()
        if S.messages and S.messages[-1]["role"] == "user":
            texte, regenerer = S.messages[-1]["content"], True

if saisie is not None:
    texte = (saisie.text or "").strip()
    for f in saisie.files or []:
        if f.file_id != S.doc_id:
            contenu, info = lire_fichier(f)
            if contenu:
                S.doc_texte, S.doc_nom, S.doc_id = contenu, f.name, f.file_id
            st.toast(info)
            if not texte:
                texte = f"J'ai joint « {f.name} ». Résume-le en quelques points." if contenu else ""

# ---------------------------------------------------------------- nouveau message
if texte and CLE:
    if not regenerer:
        S.messages.append({"role": "user", "content": texte})
        with st.chat_message("user", avatar=AVATAR_MOI):
            st.markdown(texte)
    with st.chat_message("assistant", avatar=AVATAR_IA):
        etat = st.empty()
        tour = cerveau.Tour(S.memoire, S.galerie)
        historique = [{"role": m["role"], "content": m["content"]} for m in S.messages if not m.get("erreur")]
        systeme = cerveau.consignes(S.memoire, S.doc_texte, S.doc_nom, S.galerie)
        erreur, debut = False, time.time()
        try:
            with st.spinner(f"{cerveau.NOM} réfléchit…"):
                flux = cerveau.repondre(client_ia(CLE, ADRESSE), MODELE, historique, systeme, creativite,
                                        tour, lambda t: etat.info(t))
                reponse = st.write_stream(flux)
        except AuthenticationError:
            erreur, reponse = True, "🔑 Ma clé DeepSeek est refusée. Il faut la vérifier dans les réglages (Secrets) de l'appli."
        except APIStatusError as e:
            erreur = True
            if e.status_code == 402:
                reponse = "💳 Le crédit DeepSeek est épuisé. Il faut le recharger sur platform.deepseek.com."
            else:
                reponse = f"Le service IA a répondu une erreur ({e.status_code}). Réessaie dans un instant."
        except RateLimitError:
            erreur, reponse = True, "⏳ Trop de demandes en même temps. Réessaie dans une minute."
        except (APIConnectionError, APITimeoutError):
            erreur, reponse = True, "📡 Je n'arrive pas à joindre le service IA. Vérifie la connexion et réessaie."
        etat.empty()
        if not isinstance(reponse, str):
            reponse = "".join(map(str, reponse or []))
        if erreur:
            st.error(reponse)
        elif not reponse.strip():
            reponse = "Voilà !" if tour.pieces else "Je n'ai pas de réponse cette fois. Tu peux reformuler ?"
    S.messages.append({"role": "assistant", "content": reponse.strip(), "pieces": tour.pieces, "erreur": erreur,
                       "etapes": tour.etapes, "sources": tour.sources, "suggestions": tour.suggestions,
                       "duree": round(time.time() - debut)})
    st.rerun()  # réaffiche proprement : étapes, sources, images, boutons et menu à jour
