import { NextResponse, NextRequest } from "next/server";
import { CATALYST_CANDIDATES } from "../../../data/catalystBoard";
import { CATALYST_CANDIDATES_WIDEN } from "../../../data/catalystBoardWiden";
import { CATALYST_CANDIDATES_SWEEP } from "../../../data/catalystBoardSweep";
import { CATALYST_CANDIDATES_ENRICHED } from "../../../data/catalystBoardEnriched";
export const maxDuration = 60;

// Single source of truth: the ENRICHED board (raw 3-source merge → _post_board pass:
// §3 lane tilt, resolution-driver tags, REFUTED/sub-floor → NONE drops, R/R hygiene).
// Pre-sorted by board_priority within tier and NONE-excluded.
// ?raw=1 returns the pre-enrichment 3-source dedup merge (manual > widen > sweep) — used
// only by the export builder (_export_candidates.py) to avoid a build cycle.
export async function GET(req: NextRequest) {
  const raw = new URL(req.url).searchParams.get("raw");
  if (!raw) return NextResponse.json(CATALYST_CANDIDATES_ENRICHED);
  const all = [...CATALYST_CANDIDATES, ...CATALYST_CANDIDATES_WIDEN, ...CATALYST_CANDIDATES_SWEEP];
  const seen = new Set<string>();
  const deduped = all.filter((c: any) => {
    if (!c || seen.has(c.symbol)) return false;
    seen.add(c.symbol);
    return true;
  });
  return NextResponse.json(deduped);
}
