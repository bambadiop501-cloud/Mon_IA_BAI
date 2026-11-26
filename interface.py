import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from datetime import datetime
import requests
import os
from pypdf import PdfReader

# --- PARAMÈTRES DE VOTRE IA ---
AI_NAME = "B.AI" 
API_KEY = "sk-312b59e9c1d14998bbad5e040c580e8b" # <-- METTEZ VOTRE CLÉ ICI

# Sur internet, la clé sera cachée dans les secrets de Streamlit. En local, on la met ici.
try:
    API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    API_KEY = "sk-312b59e9c1d14998bbad5e040c580e8b" # <-- Votre clé en local
    
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")
# --- FONCTIONS DE MÉMOIRE ---
def lire_memoire():
    try:
        with open("memoire.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Aucune mémoire pour le moment."

def sauvegarder_memoire(texte):
    with open("memoire.txt", "a", encoding="utf-8") as f:
        f.write(texte + "\n")

# --- OUTILS ---
def get_meteo(ville):
    try:
        url = f"https://wttr.in/{ville}?format=3"
        response = requests.get(url)
        return response.text.strip() if response.status_code == 200 else "Météo indisponible."
    except: return "Erreur météo."

def chercher_internet(requete):
    try:
        with DDGS() as ddgs:
            resultats = list(ddgs.text(requete, max_results=3))
            return "".join([f"- {r['title']} : {r['body']}\n" for r in resultats]) if resultats else "Aucun résultat."
    except: return "Erreur recherche."

# --- INTERFACE & ANIMATIONS CSS ---
st.set_page_config(page_title=AI_NAME, page_icon="logo.png", layout="centered")

st.markdown("""
<style>
    @keyframes fadeIn { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }
    .stChatMessage { border-radius: 15px; padding: 10px; margin-bottom: 10px; animation: fadeIn 0.6s ease-out; }
</style>
""", unsafe_allow_html=True)

# Initialisation du stockage pour le texte du PDF
if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""

# --- MENU LATÉRAL (SIDEBAR) ---
with st.sidebar:
    try:
        st.image("logo.png", width=120)
    except:
        st.write("🤖")
        
    st.title("Paramètres")
    creativite = st.slider("Créativité de l'IA", 0.0, 1.0, 0.7)
    
    st.divider()
    
    # --- LECTEUR DE PDF ---
    st.subheader("📄 Analyser un document")
    uploaded_file = st.file_uploader("Chargez un fichier PDF", type="pdf")
    if uploaded_file is not None:
        try:
            reader = PdfReader(uploaded_file)
            texte = ""
            for page in reader.pages[:5]: 
                texte += page.extract_text()
            st.session_state.pdf_text = texte
            st.success("PDF lu avec succès !")
        except Exception as e:
            st.error(f"Erreur de lecture : {e}")
    
    st.divider()

    if st.button("🗑️ Effacer l'écran", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
        
    if st.button("🧠 Réinitialiser la mémoire", use_container_width=True):
        with open("memoire.txt", "w", encoding="utf-8") as f:
            f.write("")
        st.success("Mémoire effacée !")
        st.rerun()

# --- LOGIQUE DE CHAT ---
st.title(f"✨ {AI_NAME}")
st.caption("Votre assistant personnel intelligent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    avatar = "🧑‍💻" if message["role"] == "user" else "logo.png"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

if prompt := st.chat_input(f"Discutez avec {AI_NAME}..."):
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant", avatar="logo.png"):
        with st.spinner(f"{AI_NAME} réfléchit..."):
            try:
                memoire = lire_memoire()
                
                # On prépare le prompt de base
                prompt_sys = f"Mémoire : {memoire}. "

                # Si un PDF a été chargé, on l'ajoute au contexte
                if st.session_state.pdf_text:
                    prompt_sys += "\nVOICI LE CONTENU DU DOCUMENT FOURNI PAR L'UTILISATEUR :\n"
                    prompt_sys += st.session_state.pdf_text[:8000]
                    prompt_sys += "\n(Utilise ces informations pour répondre si la question s'y rapporte).\n"

                prompt_sys += "RÈGLE 1 : Si on te demande la météo, réponds EXACTEMENT [METEO: ville]. "
                prompt_sys += "RÈGLE 2 : Si on te demande l'heure, réponds EXACTEMENT [HEURE]. "
                prompt_sys += "RÈGLE 3 : Si on te demande l'actu, réponds EXACTEMENT [RECHERCHE: mot clé]."
                
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "system", "content": prompt_sys}, {"role": "user", "content": prompt}],
                    temperature=creativite
                )
                reply = response.choices[0].message.content
                
                # --- GESTION DES OUTILS ---
                
                if "[METEO:" in reply:
                    ville = reply.split("[METEO:")[1].split("]")[0].strip()
                    st.info(f"🌤️ Récupération de la météo pour : {ville}...")
                    infos = get_meteo(ville)
                    res = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": f"Météo : {infos}. Réponds naturellement."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    reply = res.choices[0].message.content

                elif "[HEURE]" in reply:
                    heure_act = datetime.now().strftime("%H:%M")
                    date_act = datetime.now().strftime("%d/%m/%Y")
                    res = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": f"Il est {heure_act}, le {date_act}. Réponds naturellement."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    reply = res.choices[0].message.content

                elif "[RECHERCHE:" in reply:
                    mot_cle = reply.split("[RECHERCHE:")[1].split("]")[0].strip()
                    st.info(f"🔍 Recherche web : {mot_cle}...")
                    infos = chercher_internet(mot_cle)
                    res = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "system", "content": f"Infos web : {infos}. Réponds naturellement."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    reply = res.choices[0].message.content

                # Affichage final et sauvegarde
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                sauvegarder_memoire(f"Utilisateur: {prompt}\nIA: {reply}")
                
            except Exception as e:
                st.error(f"Erreur : {e}")
