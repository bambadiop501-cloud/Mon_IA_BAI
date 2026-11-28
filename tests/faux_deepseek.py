"""Faux serveur DeepSeek pour tester B.AI sans clé ni crédit.

Il répond au même format que l'API (réponses en flux, appels d'outils) :
  python tests/faux_deepseek.py 8899
puis lancer l'appli avec DEEPSEEK_BASE_URL=http://127.0.0.1:8899 et DEEPSEEK_API_KEY=test.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUTILS = [
    ("météo", "meteo", {"ville": "Dakar"}),
    ("heure", "heure", {"ville": "Montréal"}),
    ("powerpoint", "creer_powerpoint", {"titre": "Le recyclage au Sénégal",
        "couverture": {"source": "ia", "description_en": "colorful recycled plastic bottles art in a sunny Dakar street, realistic photo"},
        "diapos": [
        {"titre": "Pourquoi recycler ?", "points": ["Moins de déchets", "Des emplois", "Une ville plus propre"],
         "illustration": {"source": "photo", "description_en": "Lake Retba Senegal", "legende": "Le lac Rose"}},
        {"titre": "Comment agir", "points": ["Trier", "Réutiliser", "Composter"]}]}),
    ("pdf", "creer_pdf", {"titre": "Fiche : le cœur humain", "contenu": "# Le cœur\nL’organe qui fait circuler le **sang**.\n[[image 1]]\n## Les cavités\n- 2 oreillettes\n- 2 ventricules",
                          "illustrations": [{"source": "photo", "description_en": "human heart diagram", "legende": "Schéma du cœur"}]}),
    ("image", "creer_image", {"description_en": "a colorful pirogue on a beach at sunset", "format_image": "paysage"}),
    ("photo", "photo_reelle", {"sujet_en": "Lake Retba Senegal"}),
    ("retiens", "retenir", {"fait": "Elle est en terminale à Thiès"}),
    ("actu", "recherche_web", {"requete": "baccalauréat Sénégal 2026", "actualites": True}),
]


def morceau(delta, fin=None):
    return {"id": "x", "object": "chat.completion.chunk", "created": int(time.time()), "model": "deepseek-chat",
            "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]}


class Faux(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        corps = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.headers.get("Authorization") == "Bearer mauvaise":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Authentication Fails", "type": "authentication_error"}}).encode())
            return
        msgs = corps.get("messages", [])
        dernier = msgs[-1]
        morceaux = []
        if dernier["role"] == "tool":
            texte = "Voilà ce que j'ai : " + dernier["content"][:160] + "\n>>> Fais-en un PDF | Explique plus simplement | Donne-moi un quiz"
            morceaux = [morceau({"role": "assistant", "content": texte[i:i + 12]}) for i in range(0, len(texte), 12)]
        else:
            q = dernier["content"].lower()
            outil = next((o for o in OUTILS if o[0] in q), None)
            if outil:
                args = json.dumps(outil[2], ensure_ascii=False)
                morceaux = [morceau({"role": "assistant", "content": "Je m'en occupe."}),
                            morceau({"tool_calls": [{"index": 0, "id": "appel_1", "type": "function",
                                                     "function": {"name": outil[1], "arguments": args[:10]}}]}),
                            morceau({"tool_calls": [{"index": 0, "function": {"arguments": args[10:]}}]})]
            else:
                nb = sum(1 for m in msgs if m["role"] == "user")
                texte = f"Bien reçu ! C'est ton message n°{nb} dans cette discussion. Le **contexte** est gardé."
                if "document fourni" in msgs[0]["content"].lower():
                    texte += " J'ai bien ton document sous les yeux."
                morceaux = [morceau({"role": "assistant", "content": texte[i:i + 10]}) for i in range(0, len(texte), 10)]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for m in morceaux + [morceau({}, "stop")]:
            self.wfile.write(f"data: {json.dumps(m, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.03)
        self.wfile.write(b"data: [DONE]\n\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"Faux DeepSeek sur http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Faux).serve_forever()
