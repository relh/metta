import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { listPolicyLogs } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { jobId } = await params;

  try {
    const logs = await listPolicyLogs(jobId, session.user.id);
    return NextResponse.json(logs);
  } catch (error) {
    console.error("Failed to fetch policy logs:", error);
    return NextResponse.json(
      { error: "Failed to fetch policy logs" },
      { status: 500 },
    );
  }
}
