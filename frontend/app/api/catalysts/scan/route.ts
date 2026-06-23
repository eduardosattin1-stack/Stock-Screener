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
    const hit = raw
      ? (CATALYST_BOARD[symbol] || CATALYST_BOARD_WIDEN[symbol] || CATALYST_BOARD_SWEEP[symbol])
      : (CATALYST_BOARD_ENRICHED[symbol] || CATALYST_BOARD[symbol] || CATALYST_BOARD_WIDEN[symbol] || CATALYST_BOARD_SWEEP[symbol]);
    if (hit) {
      return NextResponse.json(hit);
    }

    // Unknown symbols still proxy the backend.
    const refresh = searchParams.get("refresh") || "";
    const backendUrl = `${CLOUD_RUN}/catalysts/scan?symbol=${encodeURIComponent(symbol)}${refresh ? `&refresh=${encodeURIComponent(refresh)}` : ""}`;
    const res = await fetch(backendUrl, { cache: "no-store" });

    if (!res.ok) {
      return NextResponse.json({ error: `Backend returned ${res.status}` }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: "Failed to fetch catalyst scan", details: err.message },
      { status: 500 }
    );
  }
}
