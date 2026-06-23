import json
from signal_tracker import _gcs_read_text, CYCLES_PREFIX, _load_cycle_state, _gcs_write

def recover():
    state = _load_cycle_state()
    cycle_ids = []
    if state.get("collecting_cycle_id"): cycle_ids.append(state["collecting_cycle_id"])
    cycle_ids.extend(state.get("resolving_cycle_ids", []))
    cycle_ids.extend(state.get("archived_cycle_ids", []))
    
    aapl_scans = []
    seen = set()
    
    for cid in cycle_ids:
        raw = _gcs_read_text(f"{CYCLES_PREFIX}/{cid}/predictions.jsonl", "")
        for line in raw.splitlines():
            line = line.strip()
            if not line: continue
            try:
                row = json.loads(line)
                if row.get("symbol") == "AAPL":
                    date = row.get("entry_date")
                    if date and date not in seen:
                        seen.add(date)
                        price = row.get("entry_price") or row.get("price") or 0
                        # Try to get component scores (the predictions json might have them or just composite)
                        comp = row.get("composite") or row.get("p20") or 0
                        fa = row.get("fa_score") or 0
                        cmp_us = row.get("cmp_score") or 0
                        cmp_gl = row.get("cmp_score") or 0
                        aapl_scans.append([date, price, comp, fa, cmp_us, cmp_gl])
            except: pass

    # Sort chronologically
    aapl_scans.sort(key=lambda x: x[0])
    
    if not aapl_scans:
        print("No AAPL scans found.")
        return
        
    print(f"Recovered {len(aapl_scans)} scans for AAPL.")
    for s in aapl_scans:
        print(s)
        
    # Write directly to stock_history/AAPL.json to restore it
    _gcs_write("stock_history/AAPL.json", aapl_scans)
    print("Restored to stock_history/AAPL.json!")

if __name__ == "__main__":
    recover()
