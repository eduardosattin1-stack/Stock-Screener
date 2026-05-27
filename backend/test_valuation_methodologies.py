#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from screener_v6 import get_value, Stock, save_methodology_picks

class TestValuationMethodologies(unittest.TestCase):
    
    @patch('screener_v6.get_fx_rate')
    @patch('screener_v6.cached_fmp')
    @patch('screener_v6.fmp')
    def test_valuation_calculations(self, mock_fmp, mock_cached_fmp, mock_get_fx_rate):
        # Set up mock FX rates
        mock_get_fx_rate.return_value = 1.0
        
        # Bypass cache and call lambda function directly
        mock_cached_fmp.side_effect = lambda endpoint, symbol, fetcher: fetcher()
        
        # Define mock FMP endpoint return values with full 5-year history
        def fmp_side_effect(endpoint, params=None):
            if endpoint == "income-statement":
                return [
                    {
                        "date": f"202{i}-12-31",
                        "reportedCurrency": "USD",
                        "revenue": 1000.0,
                        "epsDiluted": 5.0,
                        "grossProfit": 600.0,
                        "operatingIncome": 200.0,
                        "netIncome": 150.0,
                        "researchAndDevelopmentExpenses": 50.0,
                        "weightedAverageShsOutDil": 100.0,
                    } for i in range(1, 6) # 5 years of data
                ]
            elif endpoint == "balance-sheet-statement":
                return [
                    {
                        "date": f"202{i}-12-31",
                        "totalAssets": 2000.0,
                        "totalStockholdersEquity": 1000.0,
                        "totalCurrentAssets": 600.0,
                        "totalCurrentLiabilities": 300.0,
                        "longTermDebt": 500.0,
                    } for i in range(1, 6) # 5 years of data
                ]
            elif endpoint == "cash-flow-statement":
                return [
                    {
                        "date": f"202{i}-12-31",
                        "netCashProvidedByOperatingActivities": 220.0,
                        "capitalExpenditure": -100.0,
                        "depreciationAndAmortization": 40.0,
                    } for i in range(1, 6) # 5 years of data
                ]
            elif endpoint == "ratios":
                return [
                    {
                        "date": f"202{i}-12-31",
                        "capitalExpenditureCoverageTTM": 2.2,
                        "peRatio": 15.0,
                        "pegRatio": 1.2,
                        "priceToBookRatio": 2.5,
                        "priceToSalesRatio": 1.5,
                        "priceEarningsToGrowthRatio": 1.2,
                    } for i in range(1, 6) # 5 years of data
                ]
            elif endpoint == "key-metrics":
                return [
                    {
                        "date": f"202{i}-12-31",
                        "tangibleAssetValue": 1500.0,
                        "netDebt": 200.0,
                        "workingCapital": 150.0,
                        "payoutRatio": 0.3,
                        "receivablesTurnover": 8.0,
                        "inventoryTurnover": 6.0,
                    } for i in range(1, 6) # 5 years of data
                ]
            elif endpoint == "analyst-estimates":
                return []
            elif endpoint == "price-target-summary":
                return []
            return None

        mock_fmp.side_effect = fmp_side_effect
        
        # Test get_value calculations
        v = get_value("TESTY", price=50.0, price_currency="USD")
        
        # Assertions to verify the calculations are genuine and match the implemented math
        self.assertIsNotNone(v)
        self.assertFalse(v["_insufficient_history"])
        self.assertEqual(v["net_debt_local"], 200.0) # 500 debt - (600 - 300) = 200
        self.assertEqual(v["ebit_local"], 200.0)
        self.assertEqual(v["depreciation_local"], 40.0)
        
        # Check Graham Revised
        # Expected = eps * (8.5 + 2 * g)
        # here eps = 5.0, g = 0.0 since eps growth is 0 (negative/zero growth → g=0).
        # value = 5.0 * (8.5 + 2 * 0) = 42.5
        self.assertAlmostEqual(v["graham_revised"], 42.5)
        self.assertAlmostEqual(v["graham_revised_mos"], 1.0 - (50.0 / 42.5))  # -0.1765...
        
        # Check Owner Earnings
        # OE = 13.437176200189615, MoS = -2.7210198969702013
        self.assertAlmostEqual(v["owner_earnings"], 13.437176200189615)
        self.assertAlmostEqual(v["owner_earnings_mos"], -2.7210198969702013)
        
        # Check R&D Capitalized DCF
        # R&D Capitalized DCF = 29.272032100011394, MoS = -0.7081150987115971
        self.assertAlmostEqual(v["rd_capitalized_dcf"], 29.272032100011394)
        self.assertAlmostEqual(v["rd_capitalized_dcf_mos"], -0.7081150987115971)

        # Check EPV
        # EPV = 5.9, MoS = -7.47457627118644
        self.assertAlmostEqual(v["epv_value"], 5.9)
        self.assertAlmostEqual(v["epv_mos"], -7.47457627118644)
        
    def test_save_methodology_picks(self):
        # Create a list of mock Stock objects
        stocks = []
        sectors = ["Technology", "Financials", "Healthcare", "Industrials"]
        
        # Populate 20 mock Stock objects
        for i in range(20):
            s = Stock(
                symbol=f"SYM{i}",
                company_name=f"Stock {i}",
                price=10.0,
                sector=sectors[i % len(sectors)],
                market_cap=1000.0,
                volume=500000,
                rsi=50.0,
                net_debt_local=100.0 if i % 2 == 0 else 400.0, # leverage gate candidates
                ebit_local=100.0,
                depreciation_local=50.0, # EBITDA = 150. Net debt = 100 -> ratio = 0.67 < 3.0. Net debt = 400 -> ratio = 2.67 < 3.0.
                net_debt=100.0 if i % 2 == 0 else 400.0,
                ebit=100.0,
                depreciation=50.0,
                gross_profit=400.0,
                total_assets=1000.0,
                eps_latest=1.0,
                fx_to_report=1.0,
                fx_to_price=1.0,
            )
            
            # Make EBITDA negative for some to test the EBITDA <= 0 logic
            if i == 5:
                s.ebit_local = -50.0
                s.depreciation_local = 20.0 # EBITDA = -30 <= 0. Net debt = 400 > 0 -> Should FAIL leverage gate.
                s.ebit = -50.0
                s.depreciation = 20.0
                
            # Assign dummy MoS values for our methodologies
            s.dcf_fcff_mos = 0.5 - (i * 0.05) # SYM0 has 0.5, SYM1 has 0.45, etc.
            s.rd_capitalized_dcf_mos = 0.5 - (i * 0.05)
            s.owner_earnings_mos = 0.5 - (i * 0.05)
            s.epv_mos = 0.5 - (i * 0.05)
            s.graham_revised_mos = 0.5 - (i * 0.05)
            s.iv15_deep_value_mos = 0.5 - (i * 0.05)
            
            stocks.append(s)
            
        # Run save_methodology_picks (with no_gcs=True so it only writes locally)
        save_methodology_picks(stocks, no_gcs=True)
        
        # Verify that the local JSON file exists
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public", "methodology_picks.json")
        self.assertTrue(os.path.exists(local_path))
        
        import json
        with open(local_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertIn("last_updated", data)
        self.assertIn("methodologies", data)
        
        # Check dcf_fcff picks
        dcf_picks = data["methodologies"]["dcf_fcff"]["picks"]
        self.assertTrue(len(dcf_picks) > 0)
        self.assertTrue(len(dcf_picks) <= 20)
        
        # Verify leverage gate: SYM5 must not be in the picks
        symbols_picked = [p["symbol"] for p in dcf_picks]
        self.assertNotIn("SYM5", symbols_picked)
        
        # Verify sector cap: no single sector can exceed 50% of the picks
        sector_counts = {}
        for p in dcf_picks:
            sec = p["sector"]
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            
        limit = max(1, len(dcf_picks) // 2)
        for sec, cnt in sector_counts.items():
            self.assertTrue(cnt <= limit, f"Sector {sec} has count {cnt} which exceeds limit {limit} for portfolio of size {len(dcf_picks)}")

if __name__ == "__main__":
    unittest.main()
