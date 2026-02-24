import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { getPolicyLog } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string; policyIdx: string }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { jobId, policyIdx } = await params;
  const idx = parseInt(policyIdx, 10);
  if (isNaN(idx) || idx < 0) {
    return NextResponse.json(
      { error: "Invalid policy index" },
      { status: 400 },
    );
  }

  try {
    const log = await getPolicyLog(jobId, idx, session.user.id);
    return new NextResponse(log, {
      headers: { "Content-Type": "text/plain" },
    });
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.includes("do not have access")
    ) {
      return NextResponse.json({ error: error.message }, { status: 403 });
    }
    console.error("Failed to fetch policy log:", error);
    return NextResponse.json(
      { error: "Failed to fetch policy log" },
      { status: 500 },
    );
  }
}
