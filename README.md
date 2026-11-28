# B.AI : ton assistant personnel

B.AI est un assistant IA sénégalais, chaleureux et un peu taquin. Il tourne sur **DeepSeek**, avec une interface **Streamlit**.

## Ce qu'il sait faire
- **Discuter en gardant le fil** de la conversation.
- **Météo** de n'importe quelle ville, maintenant et sur 3 jours (Open-Meteo, avec wttr.in en secours).
- **Heure et date** à Dakar ou ailleurs.
- **Recherche sur internet** et dans l'actualité, avec les liens des sources.
- **Images créées par IA** (Pollinations) et **vraies photos libres de droits** (Wikimedia Commons, auteur crédité).
- **PDF** soignés : titres, listes, gras, accents, « œ », « € », avec une illustration si on la demande.
- **PowerPoint** de plusieurs diapositives au format 16:9, avec une illustration si on la demande.
- **Lire un PDF** ou un fichier texte joint avec le trombone, puis répondre à partir de son contenu.
- **Retenir** ce que tu lui dis sur toi, pendant la session. Tout se voit et s'efface dans le menu de gauche.
- **Coach d'études** pour les élèves et étudiants (orientation, révisions, budget). C'est aussi l'assistant de l'appli My Futur.

## Ta clé DeepSeek : jamais dans le code
Le dépôt est public : une clé écrite dans `interface.py` peut être lue et utilisée par n'importe qui.
1. Si une clé a déjà été publiée, supprime-la sur https://platform.deepseek.com, dans **API Keys**.
2. Crée une nouvelle clé.
3. Mets-la **uniquement** dans les secrets :
   - **Streamlit Cloud** : *Manage app → Settings → Secrets*, puis colle `DEEPSEEK_API_KEY = "ta-clé"`.
   - **Sur ton ordinateur** : copie `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml` et remplis-le. Ce fichier est ignoré par Git.

## Mettre en ligne (Streamlit Community Cloud, gratuit)
1. Va sur https://share.streamlit.io, puis **Create app**.
2. Choisis le dépôt `Mon_IA_BAI`, la branche, et le fichier `interface.py`.
3. Dans **Advanced settings → Secrets**, colle ta clé comme ci-dessus.
4. Clique sur **Deploy**. Après chaque modification envoyée sur GitHub, l'appli se met à jour seule.

## Lancer sur ton ordinateur
```bash
pip install -r requirements.txt
streamlit run interface.py
```

## Tester sans clé ni crédit
```bash
python tests/test_bai.py
python tests/faux_deepseek.py 8899
DEEPSEEK_API_KEY=test DEEPSEEK_BASE_URL=http://127.0.0.1:8899 streamlit run interface.py
```
La première ligne vérifie la boucle de réponse, le PDF et la mémoire. Les deux suivantes lancent l'appli avec une fausse IA locale qui répond comme DeepSeek, outils compris.

## Les fichiers
| Fichier | Rôle |
|---|---|
| `interface.py` | l'écran : discussion, menu, téléchargements |
| `cerveau.py` | la personnalité de B.AI, la description des outils, la boucle de réponse |
| `outils.py` | météo, heure, recherche, images, PDF, PowerPoint |
| `fonts/` | police DejaVu (accents et symboles dans les PDF), licence libre jointe |
| `tests/` | tests sans internet et faux serveur DeepSeek |

## Bon à savoir
- **La mémoire est propre à chaque visiteur** et s'efface quand on ferme la page. Personne ne voit ce que les autres ont dit.
- Les services gratuits d'images et de recherche sont parfois saturés. B.AI réessaie, puis le dit simplement.
- Les images de Pollinations portent parfois une petite mention « pollinations.ai » dans un coin.
- Réglages facultatifs dans les secrets : `DEEPSEEK_MODEL` (par défaut `deepseek-chat`) et `DEEPSEEK_BASE_URL`.
