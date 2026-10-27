import unittest
from moyenne import moyenne

class TestMoyenne(unittest.TestCase):
    def test_valeurs_positives(self):
        self.assertEqual(moyenne([2, 4, 6]), 4)
    def test_valeurs_negatives(self):
        self.assertEqual(moyenne([-2, -4]), -3)
    def test_liste_vide(self):
        self.assertEqual(moyenne([]), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
