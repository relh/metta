import { NextRequest, NextResponse } from "next/server";

import { getSeason } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ season: string }> },
) {
  const { season } = await params;

  try {
    const seasonDetail = await getSeason(season);
    return NextResponse.json(seasonDetail);
  } catch (error) {
    console.error("Failed to fetch season detail:", error);
    return NextResponse.json(
      { error: "Failed to fetch season detail" },
      { status: 500 },
    );
  }
}
