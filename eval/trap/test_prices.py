import unittest

from prices import parse_price


class ParsePriceTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_price("$5.00"), 5.0)

    def test_thousands_separator(self):
        self.assertEqual(parse_price("$1,234.50"), 1234.5)

    def test_accounting_negative(self):
        self.assertEqual(parse_price("(12.00)"), -12.0)

    def test_padded(self):
        self.assertEqual(parse_price(" $7 "), 7.0)


if __name__ == "__main__":
    unittest.main()
