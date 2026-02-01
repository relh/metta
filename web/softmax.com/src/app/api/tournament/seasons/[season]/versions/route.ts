import { NextRequest, NextResponse } from "next/server";

import { getSeasonVersions } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ season: string }> },
) {
  const { season } = await params;

  try {
    const versions = await getSeasonVersions(season);
    return NextResponse.json(versions);
  } catch (error) {
    console.error("Failed to fetch season versions:", error);
    return NextResponse.json(
      { error: "Failed to fetch season versions" },
      { status: 500 },
    );
  }
}
