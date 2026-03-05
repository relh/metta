import { NextRequest, NextResponse } from "next/server";

import { getRepo } from "@observatory/lib/repo/server";
import { loadBardoWorldState } from "@observatory/lib/bardoWorldState";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

export async function GET(request: NextRequest) {
  const nameFilter = request.nextUrl.searchParams.get("q")?.trim() || undefined;

  try {
    const repo = await getRepo();
    const worldState = await loadBardoWorldState({ repo, nameFilter });
    return NextResponse.json(worldState, { headers: NO_STORE_HEADERS });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      { error: `Failed to load bardo world state: ${detail}` },
      { status: 502, headers: NO_STORE_HEADERS },
    );
  }
}
