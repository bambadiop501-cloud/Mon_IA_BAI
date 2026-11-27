import streamlit as st
from openai import OpenAI
from duckduckgo_search import DDGS
from datetime import datetime
import requests
import os
from pypdf import PdfReader
from fpdf import FPDF
from pptx import Presentation
from pptx.util import Inches
import io
import urllib.parse
from PIL import Image

# --- PARAMÈTRES DE VOTRE IA ---
AI_NAME = "B.AII"

try:
    API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    API_KEY = "COLLEZ_VOTRE_CLE_DEEPSEEK_ICI" # <-- METTEZ VOTRE CLÉ ICI

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# --- INITIALISATION DE LA MÉMOIRE DE LA PAGE ---
if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""
if "file_to_download" not in st.session_state:
    st.session_state.file_to_download = None
if "file_name" not in st.session_state:
    st.session_state.file_name = ""
if "file_type" not in st.session_state:
    st.session_state.file_type = ""

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
    with open("memoire.txt", "r", encoding="utf-8") as f:
        lignes = f.readlines()
    if len(lignes) > 20:
        with open("memoire.txt", "w", encoding="utf-8") as f:
            f.writelines(lignes[-20:])

# --- OUTILS ---
@st.cache_data(ttl=3600)
def get_meteo(ville):
    try:
        url = f"https://wttr.in/{ville}?format=3"
        response = requests.get(url)
        return response.text.strip() if response.status_code == 200 else "Météo indisponible."
    except:
        return "Erreur météo."

@st.cache_data(ttl=86400)
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

def chercher_image_reelle(requete):
    try:
        # On ne garde que les 3 premiers mots pour que la recherche fonctionne bien
        requete_courte = " ".join(requete.split()[:3])
        with DDGS() as ddgs:
            resultats = list(ddgs.images(requete_courte, max_results=1))
            if resultats:
                return resultats[0]['image']
            return None
    except:
        return None

def get_image_bytes(prompt_image):
    try:
        texte_encode = urllib.parse.quote(prompt_image)
        image_url = f"https://image.pollinations.ai/prompt/{texte_encode}?width=1024&height=1024&nologo=true"
        response = requests.get(image_url)
        if response.status_code == 200:
            return response.content
        return None
    except:
        return None

# --- CRÉATION DE FICHIERS ---
def creer_pdf(texte, image_bytes=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    texte_encode = texte.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, texte_encode)
    
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img_path = "temp_pdf_image.png"
            img.save(img_path)
            pdf.add_page()
            pdf.image(img_path, x=10, y=30, w=180)
            os.remove(img_path)
        except:
            pass
    return bytes(pdf.output())

def creer_pptx(titre, contenu, image_bytes=None):
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

    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img_path = "temp_ppt_image.png"
            img.save(img_path)
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.shapes.add_picture(img_path, Inches(1), Inches(1), width=Inches(8))
            os.remove(img_path)
        except:
            pass

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
        st.session_state.file_to_download = None
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
                
                prompt_sys = f"Mémoire : {memoire}. "
                prompt_sys += "Tu es B.AII, un assistant IA sénégalais ultra-puissant, amical, un peu taquin et très intelligent. "
                prompt_sys += "INTERDICTION FORMELLE : Ne dis JAMAIS que tu ne peux pas générer de fichiers ou d'images. Tu en es parfaitement capable. "

                if st.session_state.pdf_text:
                    prompt_sys += "\nVOICI LE CONTENU DU DOCUMENT FOURNI PAR L'UTILISATEUR :\n"
                    prompt_sys += st.session_state.pdf_text[:8000]
                    prompt_sys += "\n(Utilise ces informations pour répondre si la question s'y rapporte).\n"

                prompt_sys += "RÈGLE 1 : Si on te demande la météo, réponds EXACTEMENT [METEO: ville]. "
                prompt_sys += "RÈGLE 2 : Si on te demande l'heure, réponds EXACTEMENT [HEURE]. "
                prompt_sys += "RÈGLE 3 : Si on te demande l'actu, réponds EXACTEMENT [RECHERCHE: mot clé]. "
                prompt_sys += "RÈGLE 4 : Si on te demande un PDF simple, réponds EXACTEMENT [PDF: texte]. "
                prompt_sys += "RÈGLE 5 : Si on te demande un PowerPoint simple, réponds EXACTEMENT [PPTX: titre | texte]. "
                prompt_sys += "RÈGLE 6 : Si on te demande de générer ou dessiner une image, réponds EXACTEMENT [IMAGE: description en anglais]. "
                prompt_sys += "RÈGLE 7 : Si on te demande un PDF AVEC une image, réponds EXACTEMENT [PDF_IMAGE: texte | prompt de l'image en anglais]. "
                prompt_sys += "RÈGLE 8 : Si on te demande un PowerPoint AVEC une image, réponds EXACTEMENT [PPTX_IMAGE: titre | texte | prompt de l'image en anglais]. "
                prompt_sys += "RÈGLE 9 : Si on te demande une VRAIE photo, réponds EXACTEMENT [IMAGE_REELLE: sujet en 2 ou 3 mots en anglais]. "
                
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

                elif "[IMAGE_REELLE:" in reply:
                    description = reply.split("[IMAGE_REELLE:")[1].split("]")[0].strip()
                    st.info(f"🔍 Recherche d'une vraie photo pour : {description}...")
                    image_url = chercher_image_reelle(description)
                    if image_url:
                        st.image(image_url, caption=description)
                        reply = "Voici une vraie photo trouvée sur internet pour votre demande."
                    else:
                        reply = "Désolé, je n'ai pas trouvé de vraie photo. Veux-tu que j'en génère une avec l'IA à la place ?"

                elif "[IMAGE:" in reply:
                    description = reply.split("[IMAGE:")[1].split("]")[0].strip()
                    st.info(f"🎨 Génération de l'image par IA : {description}...")
                    texte_encode = urllib.parse.quote(description)
                    image_url = f"https://image.pollinations.ai/prompt/{texte_encode}?width=1024&height=1024&nologo=true"
                    st.image(image_url, caption=description)
                    reply = "Voici l'image générée par l'IA."
                
                elif "[PDF:" in reply:
                    contenu_pdf = reply.split("[PDF:")[1].split("]")[0].strip()
                    st.session_state.file_to_download = creer_pdf(contenu_pdf)
                    st.session_state.file_name = "document_baii.pdf"
                    st.session_state.file_type = "application/pdf"
                    reply = "J'ai préparé votre document PDF. Le bouton de téléchargement apparaît en bas de l'écran."

                elif "[PDF_IMAGE:" in reply:
                    contenu = reply.split("[PDF_IMAGE:")[1].split("]")[0].strip()
                    try:
                        texte_pdf, prompt_img = contenu.split("|", 1)
                        st.info("🎨 Génération de l'image et intégration dans le PDF...")
                        img_bytes = get_image_bytes(prompt_img.strip())
                        st.session_state.file_to_download = creer_pdf(texte_pdf.strip(), img_bytes)
                        st.session_state.file_name = "document_illustre.pdf"
                        st.session_state.file_type = "application/pdf"
                        reply = "J'ai créé votre document PDF avec l'image intégrée. Le bouton est en bas !"
                    except:
                        reply = "Désolé, je n'ai pas pu formater le PDF avec l'image."

                elif "[PPTX:" in reply:
                    contenu_pptx = reply.split("[PPTX:")[1].split("]")[0].strip()
                    try:
                        titre_pptx, texte_pptx = contenu_pptx.split("|", 1)
                        st.session_state.file_to_download = creer_pptx(titre_pptx.strip(), texte_pptx.strip())
                        st.session_state.file_name = "presentation_baii.pptx"
                        st.session_state.file_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        reply = "J'ai préparé votre présentation PowerPoint. Le bouton est en bas !"
                    except:
                        reply = "Désolé, je n'ai pas pu formater correctement la présentation."

                elif "[PPTX_IMAGE:" in reply:
                    contenu = reply.split("[PPTX_IMAGE:")[1].split("]")[0].strip()
                    try:
                        titre_pptx, texte_pptx, prompt_img = contenu.split("|", 2)
                        st.info("🎨 Génération de l'image et intégration dans le PowerPoint...")
                        img_bytes = get_image_bytes(prompt_img.strip())
                        st.session_state.file_to_download = creer_pptx(titre_pptx.strip(), texte_pptx.strip(), img_bytes)
                        st.session_state.file_name = "presentation_illustree.pptx"
                        st.session_state.file_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        reply = "J'ai préparé votre PowerPoint avec l'image. Le bouton est en bas !"
                    except:
                        reply = "Désolé, je n'ai pas pu formater le PowerPoint avec l'image."

                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                sauvegarder_memoire(f"Utilisateur: {prompt}\nIA: {reply}")
                
            except Exception as e:
                st.error(f"Erreur : {e}")

# --- BOUTON DE TÉLÉCHARGEMENT PERSISTANT ---
# Ce bouton s'affiche tout en bas, en dehors du chat, pour ne jamais disparaître
if st.session_state.file_to_download is not None:
    st.divider()
    st.download_button(
        label=f"📥 Télécharger : {st.session_state.file_name}",
        data=st.session_state.file_to_download,
        file_name=st.session_state.file_name,
        mime=st.session_state.file_type
    )
