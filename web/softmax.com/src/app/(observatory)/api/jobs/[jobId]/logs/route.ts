import { NextRequest, NextResponse } from "next/server";

import { getRepo } from "@observatory/lib/repo/server";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  try {
    const repo = await getRepo();
    const logs = await repo.getJobArtifact(jobId, "logs");
    return new NextResponse(logs, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  } catch {
    return new NextResponse("Logs not available", { status: 404 });
  }
}
