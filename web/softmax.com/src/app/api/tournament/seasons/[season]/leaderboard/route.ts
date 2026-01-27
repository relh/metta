import { NextRequest, NextResponse } from "next/server";

import { getLeaderboard } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ season: string }> },
) {
  const { season } = await params;

  try {
    const leaderboard = await getLeaderboard(season);
    return NextResponse.json(leaderboard);
  } catch (error) {
    console.error("Failed to fetch leaderboard:", error);
    return NextResponse.json(
      { error: "Failed to fetch leaderboard" },
      { status: 500 },
    );
  }
}
