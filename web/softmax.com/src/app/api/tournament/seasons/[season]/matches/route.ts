import { NextRequest, NextResponse } from "next/server";

import { getMatches } from "@/lib/observatoryClient";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ season: string }> },
) {
  const { season } = await params;

  const searchParams = request.nextUrl.searchParams;
  const limit = parseInt(searchParams.get("limit") ?? "20", 10);
  const offset = parseInt(searchParams.get("offset") ?? "0", 10);
  const poolName = searchParams.get("pool") ?? undefined;
  const policyIds = searchParams.get("policies")?.split(",").filter(Boolean);

  try {
    const matches = await getMatches(season, {
      limit,
      offset,
      poolNames: poolName ? [poolName] : undefined,
      policyVersionIds: policyIds,
    });
    return NextResponse.json(matches);
  } catch (error) {
    console.error("Failed to fetch matches:", error);
    return NextResponse.json(
      { error: "Failed to fetch matches" },
      { status: 500 },
    );
  }
}
