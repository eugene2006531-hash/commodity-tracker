import unittest

from update_prices import parse_bot_csv


SAMPLE = """幣別,現金匯率-本行買入,現金匯率-本行賣出,即期匯率-本行買入,即期匯率-本行賣出
美金 (USD),31.615,32.285,31.94,32.09
港幣 (HKD),3.924,4.128,4.045,4.115
歐元 (EUR),36.23,37.57,36.745,37.345
人民幣 (CNY),4.651,4.813,4.718,4.778
"""


class BankOfTaiwanRateTest(unittest.TestCase):
    def test_parses_requested_spot_rates_and_twd_conversion(self):
        rates = parse_bot_csv(SAMPLE)
        self.assertEqual(set(rates), {"USD", "CNY", "HKD", "EUR"})
        self.assertAlmostEqual(rates["USD"]["twd_to_foreign"], 1 / 32.09)
        self.assertEqual(rates["EUR"]["spot_buy"], 36.745)

    def test_rejects_missing_currency(self):
        with self.assertRaises(RuntimeError):
            parse_bot_csv(SAMPLE.replace("人民幣 (CNY),4.651,4.813,4.718,4.778\n", ""))


if __name__ == "__main__":
    unittest.main()
