"""Language switching is speech-only, bounded to trusted whole-word entries."""

import pytest

from voix_locale.prononciation import LEXIQUE, preparer_parole

INVENTAIRE = set("".join(LEXIQUE.values()) + "vedʁˈik")


def test_termes_anglais_dans_phrase_francaise():
    texte = "Bonjour, Védric, GitHub Enterprise et Kubernetes sont prêts."
    oral = preparer_parole(texte, "fr", INVENTAIRE)
    assert oral.startswith("Bonjour Védric, ")
    assert "[[ɡˈɪthʌb]] [[ˈɛntɚpɹˌaɪz]]" in oral
    assert "[[kˌuːbɚnˈɛtiːz]] sont prêts." in oral
    assert texte.startswith("Bonjour, Védric, GitHub")


def test_acronymes_et_prenom_en_anglais():
    oral = preparer_parole("Hi Védric, SRE and CI/CD use an API.", "en", INVENTAIRE)
    assert "[[vˈɛdɹɪk]]" in oral
    assert "[[ˌɛs ˌɑːɹ ˈiː]]" in oral
    assert "[[sˌiː ˌaɪ sˌiː dˈiː]]" in oral
    assert "[[ˌeɪ pˌiː ˈaɪ]]" in oral


def test_aucun_bloc_phonetique_libre():
    assert preparer_parole("[[secret]] [[[x]]] [a]", "fr", INVENTAIRE) == ("((secret)) (((x))) (a)")


def test_frontieres_unicode_et_casse():
    oral = preparer_parole("gitHUB, myGitHub GitHubs αGitHub _GitHub entreprise", "fr", INVENTAIRE)
    assert oral == "[[ɡˈɪthʌb]], myGitHub GitHubs αGitHub _GitHub entreprise"


def test_inventaire_incompatible_garde_texte_entier():
    assert preparer_parole("GitHub Kubernetes Védric", "en", set("abc")) == (
        "GitHub Kubernetes Védric"
    )


def test_nom_unicode_decompose_et_sans_accent():
    assert preparer_parole("Bonjour, Ve\u0301dric et Vedric.", "fr", INVENTAIRE) == (
        "Bonjour Védric et Védric."
    )


@pytest.mark.parametrize("langue", ["en", "fr"])
def test_lexique_borne_et_tous_les_mots_sont_prononces(langue):
    for mot, ipa in LEXIQUE.items():
        assert preparer_parole(mot, langue, INVENTAIRE) == "[[" + ipa + "]]"
        assert len(ipa) < 64
