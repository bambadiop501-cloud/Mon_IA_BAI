import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from datetime import datetime
import requests
import os
from pypdf import PdfReader
from fpdf import FPDF
from pptx import Presentation
import io
import urllib.parse

# --- PARAMÈTRES DE VOTRE IA ---
AI_NAME = "B.AI"

# Gestion sécurisée de la clé API
try:
    API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    API_KEY = "COLLEZ_VOTRE_CLE_DEEPSEEK_ICI" # <-- METTEZ VOTRE CLÉ ICI

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
    except:
        return "Erreur météo."

def chercher_internet(requete):
    try:
        with DDGS() as ddgs:
            resultats = list(ddgs.text(requete, max_results=3))
            if not resultats:
                return "Aucun résultat."
            texte = ""
            for r in resultats:
                texte += f"- {r['title']} : {r['body']}\n"
            return texte
    except:
        return "Erreur recherche."

def creer_pdf(texte):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    texte_encode = texte.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, texte_encode)
    return bytes(pdf.output())

def creer_pptx(titre, contenu):
    prs = Presentation()
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = titre
    slide.placeholders[1].text = "Généré par B.AII"
    
    slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = titre
    tf = slide.placeholders[1].text_frame
    tf.text = contenu

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()

# --- INTERFACE & ANIMATIONS CSS ---
st.set_page_config(page_title=AI_NAME, page_icon="logo.png", layout="centered")

st.markdown("""
<style>
    @keyframes fadeIn { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }
    .stChatMessage { border-radius: 15px; padding: 10px; margin-bottom: 10px; animation: fadeIn 0.6s ease-out; }
</style>
""", unsafe_allow_html=True)

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

                prompt_sys += "Tu es B.AII, un assistant IA ultra-puissant et intelligent. "
                prompt_sys += "CONTRAIREMENT aux autres IA basiques, TU AS ACCÈS À DES OUTILS EN TEMPS RÉEL : tu peux générer des images, créer des fichiers PDF et PowerPoint, chercher sur internet et analyser des documents. "                # Si un PDF a été chargé, on l'ajoute au contexte
                if st.session_state.pdf_text:
                    prompt_sys += "\nVOICI LE CONTENU DU DOCUMENT FOURNI PAR L'UTILISATEUR :\n"
                    prompt_sys += st.session_state.pdf_text[:8000]
                    prompt_sys += "\n(Utilise ces informations pour répondre si la question s'y rapporte).\n"

                prompt_sys += "RÈGLE 1 : Si on te demande la météo, réponds EXACTEMENT [METEO: ville]. "
                prompt_sys += "RÈGLE 2 : Si on te demande l'heure, réponds EXACTEMENT [HEURE]. "
                prompt_sys += "RÈGLE 3 : Si on te demande l'actu, réponds EXACTEMENT [RECHERCHE: mot clé]. "
                prompt_sys += "RÈGLE 4 : Si on te demande un PDF, réponds EXACTEMENT [PDF: texte]. "
                prompt_sys += "RÈGLE 5 : Si on te demande un PowerPoint, réponds EXACTEMENT [PPTX: titre | texte]. "
                prompt_sys += "RÈGLE 6 : Si on te demande une image, réponds EXACTEMENT [IMAGE: description en anglais]. "
                
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
                    res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": f"Météo : {infos}. Réponds naturellement."}, {"role": "user", "content": prompt}])
                    reply = res.choices[0].message.content

                elif "[HEURE]" in reply:
                    heure_act = datetime.now().strftime("%H:%M")
                    date_act = datetime.now().strftime("%d/%m/%Y")
                    res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": f"Il est {heure_act}, le {date_act}. Réponds naturellement."}, {"role": "user", "content": prompt}])
                    reply = res.choices[0].message.content

                elif "[RECHERCHE:" in reply:
                    mot_cle = reply.split("[RECHERCHE:")[1].split("]")[0].strip()
                    st.info(f"🔍 Recherche web : {mot_cle}...")
                    infos = chercher_internet(mot_cle)
                    res = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "system", "content": f"Infos web : {infos}. Réponds naturellement."}, {"role": "user", "content": prompt}])
                    reply = res.choices[0].message.content

                elif "[IMAGE:" in reply:
                    description = reply.split("[IMAGE:")[1].split("]")[0].strip()
                    st.info(f"🎨 Génération de l'image : {description}...")
                    texte_encode = urllib.parse.quote(description)
                    image_url = f"https://image.pollinations.ai/prompt/{texte_encode}?width=1024&height=1024&nologo=true"
                    st.image(image_url, caption=description)
                    reply = "Voici l'image que j'ai générée pour vous ! Elle s'affiche ci-dessus."
                
                elif "[PDF:" in reply:
                    contenu_pdf = reply.split("[PDF:")[1].split("]")[0].strip()
                    fichier_pdf = creer_pdf(contenu_pdf)
                    st.download_button(label="📥 Télécharger le PDF", data=fichier_pdf, file_name="document_baii.pdf", mime="application/pdf")
                    reply = "J'ai préparé votre document PDF. Cliquez sur le bouton ci-dessus pour le télécharger."

                elif "[PPTX:" in reply:
                    contenu_pptx = reply.split("[PPTX:")[1].split("]")[0].strip()
                    try:
                        titre_pptx, texte_pptx = contenu_pptx.split("|", 1)
                        fichier_pptx = creer_pptx(titre_pptx.strip(), texte_pptx.strip())
                        st.download_button(label="📥 Télécharger le PowerPoint", data=fichier_pptx, file_name="presentation_baii.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
                        reply = "J'ai préparé votre présentation PowerPoint. Cliquez sur le bouton ci-dessus pour la télécharger."
                    except:
                        reply = "Désolé, je n'ai pas pu formater correctement la présentation."

                # Affichage final
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                sauvegarder_memoire(f"Utilisateur: {prompt}\nIA: {reply}")
                
            except Exception as e:
                st.error(f"Erreur : {e}")
