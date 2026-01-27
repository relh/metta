import { NextResponse } from "next/server";

import { getSeasons } from "@/lib/observatoryClient";

export async function GET() {
  try {
    const seasons = await getSeasons();
    return NextResponse.json(seasons);
  } catch (error) {
    console.error("Failed to fetch seasons:", error);
    return NextResponse.json(
      { error: "Failed to fetch seasons" },
      { status: 500 },
    );
  }
}
