import unittest

class OptionalTest(unittest.TestCase):
    @unittest.skip("optional backend unavailable")
    def test_optional_backend(self):
        self.fail("A skipped test must never reach this body")
