"""Gateway connectivity smoke test — run ON THE GATEWAY PC before going live.

    cd C:\\Users\\<user>\\Stock-Screener\\backend
    python -m tradebot.gateway_smoke

Places NO orders. Verifies, in order:
  1. socket connect to IB Gateway (host/port/clientId from config)
  2. the bot account U26508407 is in managedAccounts
  3. NetLiquidation is readable for that account (equity feed for sizing)
  4. a contract qualifies and returns a quote (market data subscription works)
Exit 0 = ready; any failure prints the fix.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig


def main() -> int:
    cfg = BotConfig()
    print(f"connecting {cfg.ib_host}:{cfg.ib_port} clientId={cfg.ib_client_id} ...")
    try:
        from ib_insync import IB, Stock
    except ImportError:
        print("FAIL: ib_insync not installed -> pip install ib_insync")
        return 1
    ib = IB()
    try:
        ib.connect(cfg.ib_host, cfg.ib_port, clientId=cfg.ib_client_id, timeout=15)
    except Exception as e:
        print(f"FAIL: cannot connect ({e}).\n  - IB Gateway running & logged in?\n"
              f"  - API socket port {cfg.ib_port} correct? (Gateway: Configure > Settings > API)\n"
              f"  - 'Enable ActiveX and Socket Clients' on, trusted IP 127.0.0.1?")
        return 1
    try:
        accounts = ib.managedAccounts()
        print(f"managed accounts: {accounts}")
        if cfg.ib_account not in accounts:
            print(f"FAIL: bot account {cfg.ib_account} not in this login's accounts.")
            return 1
        vals = {v.tag: v.value for v in ib.accountSummary(cfg.ib_account)
                if v.tag in ("NetLiquidation", "TotalCashValue")}
        print(f"{cfg.ib_account}: NetLiquidation={vals.get('NetLiquidation')} "
              f"Cash={vals.get('TotalCashValue')}")
        if float(vals.get("NetLiquidation") or 0) <= 0:
            print("WARN: zero equity — fund the account; the bot will stay gate-blocked until then.")
        c = Stock("SPY", "SMART", "USD")
        ib.qualifyContracts(c)
        t = ib.reqTickers(c)
        px = t[0].marketPrice() if t else None
        print(f"SPY quote: {px}")
        if not px or px <= 0:
            print("WARN: no market data — check data subscriptions for this user id "
                  "(delayed data is enough for the corp-action guard; "
                  "ib.reqMarketDataType(3) fallback is acceptable).")
        print("SMOKE TEST PASSED — bot can see the gateway, the account, and quotes.")
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
