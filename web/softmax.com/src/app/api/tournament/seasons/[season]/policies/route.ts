import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { getPolicies } from "@/lib/observatoryClient";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ season: string }> },
) {
  const { season } = await params;

  try {
    const mine = request.nextUrl.searchParams.get("mine") === "true";
    let args: Parameters<typeof getPolicies>[0] = { seasonName: season };
    if (mine) {
      const session = await auth();
      if (!session?.user?.id) {
        return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
      }
      args = { ...args, userId: session.user.id, mine: true };
    }
    const policies = await getPolicies(args);
    return NextResponse.json(policies);
  } catch (error) {
    console.error("Failed to fetch policies:", error);
    return NextResponse.json(
      { error: "Failed to fetch policies" },
      { status: 500 },
    );
  }
}
