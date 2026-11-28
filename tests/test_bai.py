"""Tests de B.AI sans internet ni clé : python tests/test_bai.py"""
import io
import os
import sys
from types import SimpleNamespace as N

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402

import cerveau  # noqa: E402
import outils  # noqa: E402


def morceau(contenu=None, appels=None):
    return N(choices=[N(delta=N(content=contenu, tool_calls=appels))])


def fausse_image(couleur=(200, 30, 40), taille=(400, 300), mode="RGB"):
    tampon = io.BytesIO()
    Image.new(mode, taille, couleur if mode == "RGB" else couleur + (128,)).save(tampon, "PNG")
    return tampon.getvalue()


class FauxClient:
    """Imite client.chat.completions.create(stream=True) : 1er tour = appel d'outil, 2e tour = texte + suggestions."""

    def __init__(self):
        self.tours = []
        self.chat = N(completions=N(create=self.create))

    def create(self, **kw):
        self.tours.append(kw)
        if kw["messages"][-1]["role"] == "tool":
            return iter([morceau("C'est "), morceau("fait !\n>"), morceau(">> Un PDF | Plus simple")])
        f1 = N(name="creer_powerpoint", arguments='{"titre": "Test", "diapos": [{"titre": "A", ')
        f2 = N(name=None, arguments='"points": ["un", "deux"], "illustration": {"source": "galerie", "numero": 1}}]}')
        return iter([morceau("Je prépare ça."),
                     morceau(appels=[N(index=0, id="c1", function=f1)]),
                     morceau(appels=[N(index=0, id=None, function=f2)])])


def test_boucle_outil_galerie_suggestions():
    tour = cerveau.Tour(memoire=[], galerie=[{"octets": fausse_image(), "legende": "x", "description": "red", "source": "ia"}])
    etapes = []
    texte = "".join(cerveau.repondre(FauxClient(), "deepseek-chat", [{"role": "user", "content": "un ppt"}],
                                     "consignes", 0.7, tour, etapes.append))
    assert texte.startswith("Je prépare ça.") and texte.rstrip().endswith("C'est fait !"), repr(texte)
    assert ">>>" not in texte and tour.suggestions == ["Un PDF", "Plus simple"], tour.suggestions
    assert tour.pieces and tour.pieces[0]["nom"] == "test-bai.pptx" and tour.pieces[0]["octets"][:2] == b"PK"
    assert etapes == ["📊 PowerPoint…"] and "1 illustration" in tour.etapes[0], tour.etapes


def test_pdf_illustrations_placees():
    illus = [{"octets": fausse_image(), "legende": "Schéma 1"}, {"octets": fausse_image((20, 40, 200), mode="RGBA"), "legende": "Image 2"}]
    pdf = outils.creer_pdf("L’œuvre — 12 500 €", "# Titre\nTexte **gras** 😀\n[[image 2]]\n- point", illus)
    assert pdf[:4] == b"%PDF" and len(pdf) > 8000


def test_pptx_illustrations():
    data = outils.creer_pptx("Titre", [{"titre": "A", "points": ["x"]}, {"titre": "B", "points": ["y"]}],
                             {1: {"octets": fausse_image(), "legende": "photo"}}, {"octets": fausse_image((0, 0, 0))})
    assert data[:2] == b"PK" and len(data) > 20000


def test_pertinence_et_sources():
    assert outils.pertinence("human heart diagram", "File:Diagram of the human heart (cropped).svg") >= 0.99
    assert outils.pertinence("Lake Retba Senegal", "File:Dakar market.jpg") < outils.SEUIL
    s = cerveau._sources("Résultats :\n- Campus France : texte [https://www.campusfrance.org/fr]\n- Autre (2026-01-01) : t [https://ex.org/a]")
    assert [x["url"] for x in s] == ["https://www.campusfrance.org/fr", "https://ex.org/a"]


def test_memoire_et_noms():
    tour = cerveau.Tour(memoire=[], galerie=[])
    assert cerveau.executer("retenir", {"fait": "Je vis à Thiès"}, tour) == "C'est retenu."
    assert tour.memoire == ["Je vis à Thiès"] and "Je vis à Thiès" in cerveau.consignes(tour.memoire)
    assert outils.nom_fichier("Révision : la cellule", "pdf") == "revision-la-cellule-bai.pdf"
    assert "Échec" in cerveau.executer("creer_powerpoint", {"titre": "X", "diapos": []}, tour)


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("OK ", nom)
