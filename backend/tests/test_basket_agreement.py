"""Agreement + plausibility ranking in screener_v6.save_methodology_picks (Bruno 2026-11-28).

Offline (FMP_OFFLINE=1). Run: python backend/tests/test_basket_agreement.py
"""
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["FMP_OFFLINE"] = "1"
logging.disable(logging.CRITICAL)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import screener_v6 as S  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def stock(**mos):
    base = {f: -1.0 for f in S.AGREE_MODELS}
    base["graham_revised_mos"] = -1.0
    base.update(mos)
    return SimpleNamespace(**base)


check("the plausibility ceiling is a fair value of 3x the price", abs(S.PLAUSIBLE_MOS_MAX - 2 / 3) < 1e-9)

s = stock(dcf_fcff_mos=0.30, epv_mos=0.25, acquirers_multiple_mos=0.12, owner_earnings_mos=0.05)
check("methods in the 10-67% band agree, a 5% discount does not", S._agreeing_models(s) == 3)
check("the basket's own method can be left out", S._agreeing_models(s, exclude="dcf_fcff_mos") == 2)

s = stock(dcf_fcff_mos=0.85, rd_capitalized_dcf_mos=0.90)
check("discounts above 67% (fair value >3x) never count as agreement", S._agreeing_models(s) == 0)

s = stock(graham_revised_mos=0.40)
check("graham is not one of the agreeing methods", S._agreeing_models(s) == 0)

check("graham stays a published basket but is agreement-ranked", "graham_revised" in S.AGREEMENT_RANKED)
check("the rank baskets keep their own order", not ({"acquirers_multiple", "ev_gp", "ev_gross_profit",
                                                     "earnings_yield_gap", "convergence"} & S.AGREEMENT_RANKED))
check("the spin-off check fails open offline", S._recent_spinoffs(["CTVA"]) == {})

# ordering: agreement first, capped discount second (mirrors the basket loop's sort key)
a = SimpleNamespace(symbol="A", _agree_rank=3, _temp_mos=0.25)   # three methods agree on 25%
b = SimpleNamespace(symbol="B", _agree_rank=1, _temp_mos=S.PLAUSIBLE_MOS_MAX)  # one method, capped
c = SimpleNamespace(symbol="C", _agree_rank=3, _temp_mos=0.40)
order = [x.symbol for x in sorted([a, b, c], key=lambda x: (x._agree_rank, x._temp_mos), reverse=True)]
check("agreement outranks a lone large discount", order == ["C", "A", "B"])

src = Path(S.__file__).read_text(encoding="utf-8")
check("the basket loop drops an implausible claim without two other methods",
      "eff_mos > PLAUSIBLE_MOS_MAX and n_other < 2" in src)
check("the basket loop drops a recent spin-off", 'getattr(s, "recent_spinoff", "")' in src)
check("each pick publishes its agreement count", '"methods_agree":' in src)

print("\nALL PASS" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
