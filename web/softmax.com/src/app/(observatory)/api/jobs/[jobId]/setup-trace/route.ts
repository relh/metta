import { NextRequest } from "next/server";

import { fetchTraceArtifact, traceOptions } from "../traceProxy";

export const OPTIONS = traceOptions;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  return fetchTraceArtifact(request, params, "setup_trace", true);
}

export async function HEAD(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  return fetchTraceArtifact(request, params, "setup_trace", false);
}
