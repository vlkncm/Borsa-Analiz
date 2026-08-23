import math
import unittest

from mobile_app import json_safe, normalize_symbol


class MobileAppTests(unittest.TestCase):
    def test_normalize_symbol(self):
        self.assertEqual(normalize_symbol(" thyao "), "THYAO.IS")
        self.assertEqual(normalize_symbol("eregl.is"), "EREGL.IS")

    def test_invalid_symbol(self):
        for value in ("", "?", "TOO-LONG"):
            with self.assertRaises(ValueError):
                normalize_symbol(value)

    def test_json_safe(self):
        value = json_safe({"nan": math.nan, "values": (1, 2)})
        self.assertEqual(value, {"nan": None, "values": [1, 2]})


if __name__ == "__main__":
    unittest.main()
