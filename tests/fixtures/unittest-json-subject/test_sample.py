import unittest


class SampleTests(unittest.TestCase):
    def test_alpha(self):
        self.assertTrue(True)

    def test_beta(self):
        self.assertEqual(2 + 2, 4)
