"""B.AI : interface de discussion (Streamlit).

Lancer en local :   streamlit run interface.py
Clé DeepSeek : dans .streamlit/secrets.toml (DEEPSEEK_API_KEY = "...") ou dans la variable
d'environnement DEEPSEEK_API_KEY. Jamais dans le code.
"""
from __future__ import annotations

import base64
import io
import os

import streamlit as st
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
                    OpenAI, RateLimitError)
from pypdf import PdfReader

import cerveau

ICI = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(ICI, "logo.png")
LOGO_PETIT = os.path.join(ICI, "logo-petit.png")
AVATAR_IA = LOGO_PETIT if os.path.exists(LOGO_PETIT) else LOGO
AVATAR_MOI = "🧑🏾‍💻"
MAX_CARACTERES_DOC = 20000


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
    return OpenAI(api_key=cle, base_url=adresse, timeout=90, max_retries=1)


@st.cache_data
def logo_base64() -> str:
    with open(AVATAR_IA, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------------------------------------------- mémoire de la session (propre à chaque visiteur)
for cle, defaut in {"messages": [], "memoire": [], "doc_texte": "", "doc_nom": "", "doc_id": ""}.items():
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
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- documents
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


# ---------------------------------------------------------------- menu latéral
with st.sidebar:
    st.image(LOGO_PETIT if os.path.exists(LOGO_PETIT) else LOGO, width=64)
    if st.button("✨ Nouvelle discussion", use_container_width=True):
        S.messages = []
        st.rerun()
    creativite = st.slider("Créativité", 0.0, 1.3, 0.7, 0.1, help="Bas : réponses précises. Haut : réponses plus inventives.")

    st.divider()
    st.subheader("📄 Document")
    if S.doc_nom:
        st.caption(f"En cours : **{S.doc_nom}**")
        if st.button("Retirer le document", use_container_width=True):
            S.doc_texte = S.doc_nom = S.doc_id = ""
            st.rerun()
    else:
        st.caption("Joins un PDF ou un fichier texte avec le trombone, dans la barre de message.")

    st.divider()
    st.subheader("🧠 Ce que B.AI retient")
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
                   "La mémoire reste propre à toi et s'efface quand tu fermes la page.")
    st.divider()
    st.caption(f"{cerveau.NOM} 2.0 · modèle {MODELE}")


# ---------------------------------------------------------------- affichage
def afficher_pieces(pieces: list, prefixe: str) -> None:
    for j, p in enumerate(pieces):
        if p["type"] == "image" and not p.get("octets"):
            st.image(p["url"], caption=p.get("legende", ""))
            st.caption(f"[Ouvrir l'image en grand]({p['url']})")
            continue
        if p["type"] == "image":
            st.image(p["octets"], caption=p.get("legende", ""))
            if p.get("lien"):
                st.caption(f"[Voir la source]({p['lien']})")
            st.download_button("📥 Télécharger l'image", p["octets"], file_name=p.get("nom", "image.jpg"),
                               mime="image/jpeg", key=f"{prefixe}-{j}")
        else:
            st.download_button(f"📥 Télécharger {p['nom']}", p["octets"], file_name=p["nom"], mime=p["mime"],
                               key=f"{prefixe}-{j}", type="primary")


st.markdown(f"""<div class="bai-tete"><img src="data:image/png;base64,{logo_base64()}" alt="">
<div><h1>{cerveau.NOM}</h1><p>Ton assistant personnel : il cherche, explique, crée des PDF, des PowerPoint et des images.</p></div></div>""",
            unsafe_allow_html=True)

if not CLE:
    st.warning("La clé DeepSeek n'est pas encore réglée. Sur Streamlit Cloud : *Manage app → Settings → Secrets*, "
               "puis ajoute la ligne `DEEPSEEK_API_KEY = \"ta-clé\"`. En local : fichier `.streamlit/secrets.toml`.")

SUGGESTIONS = ["Quel temps fait-il à Dakar ?", "Fais-moi un PowerPoint sur le recyclage au Sénégal",
               "Aide-moi à choisir mes études après le bac", "Crée une image d'une pirogue au coucher du soleil"]
choix = None
if not S.messages:
    st.markdown('<div class="bai-accueil"><b>Salut, moi c\'est B.AI 👋</b><br>Pose-moi une question, '
                'ou demande-moi un document, une présentation, une image. Je peux aussi lire tes PDF.</div>',
                unsafe_allow_html=True)
    cols = st.columns(2)
    for i, s in enumerate(SUGGESTIONS):
        if cols[i % 2].button(s, key=f"sugg-{i}", use_container_width=True):
            choix = s

for i, m in enumerate(S.messages):
    with st.chat_message(m["role"], avatar=AVATAR_MOI if m["role"] == "user" else AVATAR_IA):
        st.markdown(m["content"])
        afficher_pieces(m.get("pieces", []), f"h{i}")

saisie = st.chat_input(f"Écris à {cerveau.NOM}…", accept_file=True, file_type=["pdf", "txt", "md"], disabled=not CLE)

# ---------------------------------------------------------------- nouveau message
texte = choix
doc_avant = S.doc_nom
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

if texte and CLE:
    S.messages.append({"role": "user", "content": texte})
    with st.chat_message("user", avatar=AVATAR_MOI):
        st.markdown(texte)
    with st.chat_message("assistant", avatar=AVATAR_IA):
        etat = st.empty()
        pieces: list = []
        avant = (list(S.memoire), S.doc_nom, len(S.messages))
        historique = [{"role": m["role"], "content": m["content"]} for m in S.messages if not m.get("erreur")]
        erreur = False
        systeme = cerveau.consignes(S.memoire, S.doc_texte, S.doc_nom)
        try:
            with st.spinner(f"{cerveau.NOM} réfléchit…"):
                flux = cerveau.repondre(client_ia(CLE, ADRESSE), MODELE, historique, systeme, creativite,
                                        pieces, S.memoire, lambda t: etat.caption(t))
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
        if erreur:
            st.error(reponse)
        elif not isinstance(reponse, str):
            reponse = "".join(map(str, reponse or []))
        if not reponse.strip():
            reponse = "Voilà !" if pieces else "Je n'ai pas de réponse cette fois. Tu peux reformuler ?"
            st.markdown(reponse)
        afficher_pieces(pieces, f"n{len(S.messages)}")
    S.messages.append({"role": "assistant", "content": reponse, "pieces": pieces, "erreur": erreur})
    if avant[0] != S.memoire or avant[1] != doc_avant or avant[2] == 1:  # menu et accueil à jour
        st.rerun()
