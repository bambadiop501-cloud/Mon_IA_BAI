"""Tests de B.AI sans internet ni clé : python tests/test_bai.py"""
import os
import sys
from types import SimpleNamespace as N

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cerveau  # noqa: E402
import outils  # noqa: E402


def morceau(contenu=None, appels=None):
    return N(choices=[N(delta=N(content=contenu, tool_calls=appels))])


class FauxClient:
    """Imite client.chat.completions.create(stream=True) : 1er tour = appel d'outil, 2e tour = texte."""

    def __init__(self):
        self.tours = []
        self.chat = N(completions=N(create=self.create))

    def create(self, **kw):
        self.tours.append(kw)
        if kw["messages"][-1]["role"] == "tool":
            return iter([morceau("C'est "), morceau("fait !")])
        f1 = N(name="creer_powerpoint", arguments='{"titre": "Test", "diapos": [{"titre": "A", ')
        f2 = N(name=None, arguments='"points": ["un", "deux"]}]}')
        return iter([morceau("Je prépare ça."),
                     morceau(appels=[N(index=0, id="c1", function=f1)]),
                     morceau(appels=[N(index=0, id=None, function=f2)])])


def test_boucle_avec_outil():
    client, pieces, memoire, etapes = FauxClient(), [], [], []
    texte = "".join(cerveau.repondre(client, "deepseek-chat", [{"role": "user", "content": "un ppt"}],
                                     "consignes", 0.7, pieces, memoire, etapes.append))
    assert texte.startswith("Je prépare ça.") and texte.endswith("C'est fait !"), texte
    assert len(client.tours) == 2
    assert pieces and pieces[0]["nom"] == "test-bai.pptx" and pieces[0]["octets"][:2] == b"PK"
    assert etapes == ["📊 PowerPoint…"]
    outil = client.tours[1]["messages"][-1]
    assert outil["role"] == "tool" and "PowerPoint" in outil["content"]


def test_pdf_unicode():
    pdf = outils.creer_pdf("L’œuvre — 12 500 €", "# Titre\nTexte **gras**, « guillemets », cœur 😀\n- point")
    assert pdf[:4] == b"%PDF" and len(pdf) > 5000


def test_memoire_et_noms():
    memoire = []
    assert cerveau.executer("retenir", {"fait": "Je vis à Thiès"}, [], memoire) == "C'est retenu."
    assert memoire == ["Je vis à Thiès"]
    assert "Je vis à Thiès" in cerveau.consignes(memoire)
    assert outils.nom_fichier("Révision : la cellule", "pdf") == "revision-la-cellule-bai.pdf"
    assert "Échec" in cerveau.executer("creer_powerpoint", {"titre": "X", "diapos": []}, [], [])


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("OK ", nom)
