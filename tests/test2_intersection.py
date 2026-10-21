"""
Tests du comportement des piétons (attendre au vert, traverser une fois, disparaître).

Lancement depuis la racine du projet :
    python tests/test_pietons.py

Pas besoin de PyQt6 ni du réseau.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation.intersection import IntersectionManager, CouleurFeu
from simulation.vehicules import Vehicule, TypeVehicule

BORD = Vehicule.BORD


def mettre_a_jour_pieton(pieton, intersection):
    pieton.mettre_a_jour_pieton(intersection)

DT = 0.05


def nouveau_pieton(pos_x, pos_y, cap):
    p = Vehicule(id_vehicule="p1", v_type=TypeVehicule.PIETON)
    p.pos_x, p.pos_y, p.cap, p.vitesse = pos_x, pos_y, cap, 0.0
    return p


def pas(pieton, intersection):
    """Un pas de temps : comportement du piéton, feux, puis déplacement (comme le moteur)."""
    mettre_a_jour_pieton(pieton, intersection)
    intersection.update(DT)
    pieton.pos_x += pieton.vitesse * math.cos(pieton.cap) * DT
    pieton.pos_y += pieton.vitesse * math.sin(pieton.cap) * DT


def avancer_feux(intersection, secondes):
    for _ in range(int(round(secondes / DT))):
        intersection.update(DT)


def avancer_jusqu_au_vert_eo(intersection):
    """Avance jusqu'au vert des véhicules E/O (= vert pour les piétons qui marchent selon x)."""
    for _ in range(int(120 / DT)):
        if intersection.feu_eo == CouleurFeu.VERT:
            return
        intersection.update(DT)
    raise AssertionError("le feu E/O n'est jamais passé au vert")


class TestAttenteEtTraversee(unittest.TestCase):

    def test_attend_quand_le_feu_est_rouge(self):
        # NS vert au départ : un piéton qui marche selon x (il traverse la route N/S) a un feu rouge
        i = IntersectionManager()
        p = nouveau_pieton(-5.0, 9.0, 0.0)
        for _ in range(40):                      # 2 s
            pas(p, i)
        self.assertEqual(p.vitesse, 0.0)
        self.assertEqual(p.etat_traversee, "attente")
        self.assertAlmostEqual(p.pos_x, -BORD, places=2)

    def test_part_quand_le_feu_passe_au_vert(self):
        i = IntersectionManager()
        avancer_jusqu_au_vert_eo(i)              # feu vert pour qui marche selon x
        p = nouveau_pieton(-5.0, 9.0, 0.0)
        pas(p, i)
        self.assertEqual(p.etat_traversee, "traverse")
        self.assertGreater(p.vitesse, 0.0)

    def test_traverse_une_seule_fois_puis_est_supprime(self):
        i = IntersectionManager()
        avancer_jusqu_au_vert_eo(i)
        p = nouveau_pieton(-5.0, 9.0, 0.0)
        for _ in range(int(15 / DT)):            # 15 s, largement de quoi traverser
            pas(p, i)
            if getattr(p, "a_supprimer", False):
                break
        self.assertTrue(getattr(p, "a_supprimer", False))
        self.assertGreater(p.pos_x, BORD)        # il est bien de l'autre côté
        self.assertEqual(p.cap, 0.0)             # il n'a jamais fait demi-tour

    def test_pas_d_aller_retour(self):
        """Le cap ne change jamais pendant la traversée."""
        i = IntersectionManager()
        avancer_jusqu_au_vert_eo(i)
        p = nouveau_pieton(5.0, -9.0, math.pi)   # part de l'autre bord
        caps = set()
        for _ in range(int(15 / DT)):
            pas(p, i)
            caps.add(round(p.cap, 3))
            if getattr(p, "a_supprimer", False):
                break
        self.assertEqual(len(caps), 1)

    def test_pieton_deja_sur_la_chaussee_finit_sa_traversee(self):
        i = IntersectionManager()                # feu rouge pour lui, mais il est déjà engagé
        p = nouveau_pieton(0.0, 9.0, 0.0)
        for _ in range(int(10 / DT)):
            pas(p, i)
            if getattr(p, "a_supprimer", False):
                break
        self.assertTrue(getattr(p, "a_supprimer", False))
        self.assertGreater(p.pos_x, BORD)

    def test_passage_est_ouest_marche_selon_y(self):
        i = IntersectionManager()                # NS vert : feu vert pour qui marche selon y
        p = nouveau_pieton(9.0, -5.0, math.pi / 2)
        pas(p, i)
        self.assertEqual(p.etat_traversee, "traverse")
        self.assertGreater(p.vitesse, 0.0)

    def test_pieton_place_au_bord_depuis_le_loin(self):
        """Un piéton posé loin du passage est ramené au bord le plus proche."""
        i = IntersectionManager()
        p = nouveau_pieton(-15.0, 15.0, 0.0)     # position du scénario « heure de pointe »
        pas(p, i)
        self.assertAlmostEqual(p.pos_x, -BORD, places=2)
        self.assertAlmostEqual(p.pos_y, 9.0)


class TestSecurite(unittest.TestCase):
    """Un piéton ne doit jamais être sur la chaussée quand les véhicules croisés ont le vert."""

    def conflits(self, durees):
        total = 0
        for decalage in range(0, 400):           # 0 à 40 s : toutes les arrivées possibles
            i = IntersectionManager()
            i._IntersectionManager__durees = durees
            avancer_feux(i, decalage * 0.1)
            p = nouveau_pieton(-5.0, 9.0, 0.0)   # marche selon x : croise les véhicules N/S
            for _ in range(int(40 / DT)):
                pas(p, i)
                sur_la_route = abs(p.pos_x) < BORD
                if sur_la_route and i.feu_ns == CouleurFeu.VERT:
                    total += 1
                    break
                if getattr(p, "a_supprimer", False):
                    break
        return total

    def test_degagement_de_3_secondes_suffit(self):
        self.assertEqual(self.conflits([12.0, 3.0, 3.0, 12.0, 3.0, 3.0]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
