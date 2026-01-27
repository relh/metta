import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const episodeIds: string[] = body.episode_ids ?? [];

    if (episodeIds.length === 0) {
      return NextResponse.json({ episodes: [] });
    }

    const response = await fetch(
      `${process.env.OBSERVATORY_API_URL}/stats/episodes/query`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ episode_ids: episodeIds }),
      },
    );

    if (!response.ok) {
      throw new Error("Failed to fetch episodes");
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch episodes:", error);
    return NextResponse.json(
      { error: "Failed to fetch episodes" },
      { status: 500 },
    );
  }
}
