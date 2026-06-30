import { NextResponse, NextRequest } from "next/server";
import { CATALYST_BOARD } from "../../../data/catalystBoard";
import { CATALYST_BOARD_WIDEN } from "../../../data/catalystBoardWiden";
import { CATALYST_BOARD_SWEEP } from "../../../data/catalystBoardSweep";
import { CATALYST_BOARD_ENRICHED } from "../../../data/catalystBoardEnriched";
export const maxDuration = 180;

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const symbol = (searchParams.get("symbol") || "").toUpperCase();

    if (!symbol) {
      return NextResponse.json({ error: "Missing symbol parameter" }, { status: 400 });
    }

    // Single source: the ENRICHED board (corrected scores/tiers + driver tags + corrections
    // audit). NONE-tier names stay reachable here so the detail page can show WHY they dropped.
    // ?raw=1 serves the pre-enrichment 3-source board (used only by the export builder).
    const raw = searchParams.get("raw");
    const refresh = searchParams.get("refresh") || "";
    // RE-SCAN (refresh) forces a fresh, FULL live deep-scan from the backend, bypassing the cached
    // board dossier. Board names are served from the compact 3-tier sweep dossier (Bloom timeline +
    // density + evidence), which omits the heavy single-name sections (convergence/event tracks,
    // credit-health audit, activist footprint, SoP). RE-SCAN lets any board name get that rich
    // Loeb/Bloom scan on demand; the default click stays cached for speed.
    const hit = refresh
      ? null
      : raw
        ? (CATALYST_BOARD[symbol] || CATALYST_BOARD_WIDEN[symbol] || CATALYST_BOARD_SWEEP[symbol])
        : (CATALYST_BOARD_ENRICHED[symbol] || CATALYST_BOARD[symbol] || CATALYST_BOARD_WIDEN[symbol] || CATALYST_BOARD_SWEEP[symbol]);
    if (hit) {
      return NextResponse.json(hit);
    }

    // Off-board names (and any RE-SCAN) proxy the backend for a live deep-scan.
    const backendUrl = `${CLOUD_RUN}/catalysts/scan?symbol=${encodeURIComponent(symbol)}${refresh ? `&refresh=${encodeURIComponent(refresh)}` : ""}`;
    const res = await fetch(backendUrl, { cache: "no-store" });

    if (!res.ok) {
      return NextResponse.json({ error: `Backend returned ${res.status}` }, { status: res.status });
    }

    // The Python backend can emit non-finite floats (e.g. dividend_coverage = inf for a no-dividend
    // name like a biotech), which Python serializes as the bare tokens Infinity / -Infinity / NaN —
    // INVALID JSON that res.json() rejects, blanking the depth view with "Scan Failed". Parse the
    // text and, only on failure, neutralize those tokens in value position (after : [ or ,) to null.
    const bodyText = await res.text();
    let data: any;
    try {
      data = JSON.parse(bodyText);
    } catch {
      data = JSON.parse(
        bodyText
          .replace(/([:[,]\s*)-?Infinity\b/g, "$1null")
          .replace(/([:[,]\s*)NaN\b/g, "$1null")
      );
    }
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: "Failed to fetch catalyst scan", details: err.message },
      { status: 500 }
    );
  }
}
