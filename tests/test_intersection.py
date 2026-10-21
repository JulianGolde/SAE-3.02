import os
import sys
import unittest

# Permet d'importer les modules de src/ sans installer le projet
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation.intersection import IntersectionManager, CouleurFeu


def avancer(inter, secondes, pas=0.5):
    """Fait avancer le temps par petits pas (update ne change qu'une phase par appel)."""
    for _ in range(int(secondes / pas)):
        inter.update(pas)


class TestCycleNormal(unittest.TestCase):
    """Le cycle automatique : 12 s vert, 3 s orange, 1,5 s tout rouge, puis l'autre axe."""

    def test_etat_initial(self):
        i = IntersectionManager()
        self.assertEqual(i.feu_ns, CouleurFeu.VERT)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)

    def test_pas_de_changement_avant_12s(self):
        i = IntersectionManager()
        avancer(i, 11.5)
        self.assertEqual(i.feu_ns, CouleurFeu.VERT)

    def test_ns_orange_apres_12s(self):
        i = IntersectionManager()
        avancer(i, 12.0)
        self.assertEqual(i.feu_ns, CouleurFeu.ORANGE)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)

    def test_tout_rouge_apres_15s(self):
        i = IntersectionManager()
        avancer(i, 15.0)
        self.assertEqual(i.feu_ns, CouleurFeu.ROUGE)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)

    def test_eo_vert_apres_16_5s(self):
        i = IntersectionManager()
        avancer(i, 16.5)
        self.assertEqual(i.feu_ns, CouleurFeu.ROUGE)
        self.assertEqual(i.feu_eo, CouleurFeu.VERT)

    def test_cycle_complet_de_33s(self):
        """Après 2 x (12 + 3 + 1,5) = 33 s, on revient à l'état initial."""
        i = IntersectionManager()
        avancer(i, 33.0)
        self.assertEqual(i.feu_ns, CouleurFeu.VERT)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)

    def test_jamais_deux_verts_en_meme_temps(self):
        """Sécurité : les deux axes ne doivent jamais être verts simultanément."""
        i = IntersectionManager()
        for _ in range(200):  # 100 s simulées
            i.update(0.5)
            self.assertFalse(
                i.feu_ns == CouleurFeu.VERT and i.feu_eo == CouleurFeu.VERT
            )


class TestUrgenceVTA(unittest.TestCase):
    """Forçage du feu pour un véhicule prioritaire."""

    def test_vta_axe_x_donne_vert_a_est_ouest(self):
        i = IntersectionManager()
        i.forcer_passage_vta(True)
        self.assertEqual(i.feu_eo, CouleurFeu.VERT)
        self.assertEqual(i.feu_ns, CouleurFeu.ROUGE)

    def test_vta_axe_y_donne_vert_a_nord_sud(self):
        i = IntersectionManager()
        avancer(i, 16.5)  # on part d'un état où EO est vert
        i.forcer_passage_vta(False)
        self.assertEqual(i.feu_ns, CouleurFeu.VERT)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)

    def test_le_cycle_est_suspendu_pendant_l_urgence(self):
        i = IntersectionManager()
        i.forcer_passage_vta(True)
        avancer(i, 60.0)
        self.assertEqual(i.feu_eo, CouleurFeu.VERT)
        self.assertEqual(i.feu_ns, CouleurFeu.ROUGE)

    def test_annuler_urgence_reprend_le_cycle(self):
        i = IntersectionManager()
        i.forcer_passage_vta(True)
        i.annuler_urgence()
        # Le cycle repart de la phase en cours (phase 0 : NS vert, EO rouge)
        self.assertEqual(i.feu_ns, CouleurFeu.VERT)
        self.assertEqual(i.feu_eo, CouleurFeu.ROUGE)
        avancer(i, 12.0)
        self.assertEqual(i.feu_ns, CouleurFeu.ORANGE)

    def test_annuler_sans_urgence_ne_change_rien(self):
        i = IntersectionManager()
        avancer(i, 12.0)  # NS orange
        i.annuler_urgence()
        self.assertEqual(i.feu_ns, CouleurFeu.ORANGE)


class TestEtatReseau(unittest.TestCase):
    """Application de l'état reçu du serveur et lecture par voie."""

    def test_set_state(self):
        i = IntersectionManager()
        i.set_state(3, 1)  # NS rouge, EO vert
        self.assertEqual(i.feu_ns, CouleurFeu.ROUGE)
        self.assertEqual(i.feu_eo, CouleurFeu.VERT)

    def test_set_state_valeur_invalide(self):
        i = IntersectionManager()
        with self.assertRaises(ValueError):
            i.set_state(9, 9)

    def test_couleur_pour_voie(self):
        i = IntersectionManager()
        i.set_state(1, 3)  # NS vert, EO rouge
        self.assertEqual(i.get_couleur_pour_voie(False), CouleurFeu.VERT)   # axe N/S
        self.assertEqual(i.get_couleur_pour_voie(True), CouleurFeu.ROUGE)   # axe E/O


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestFeuxPietons(unittest.TestCase):
    def test_pieton_vert_quand_ns_vert(self):
        i = IntersectionManager()                     # NS vert, EO rouge
        self.assertEqual(i.get_couleur_pieton(False), CouleurFeu.VERT)
        self.assertEqual(i.get_couleur_pieton(True), CouleurFeu.ROUGE)

    def test_pieton_rouge_pendant_l_orange(self):
        i = IntersectionManager()
        avancer(i, 12.0)                              # NS orange
        self.assertEqual(i.get_couleur_pieton(False), CouleurFeu.ROUGE)
        self.assertEqual(i.get_couleur_pieton(True), CouleurFeu.ROUGE)
