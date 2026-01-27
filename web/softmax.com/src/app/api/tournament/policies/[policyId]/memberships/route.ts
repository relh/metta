import { NextRequest, NextResponse } from "next/server";

import { getPolicyMemberships } from "@/lib/observatoryClient";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ policyId: string }> },
) {
  const { policyId } = await params;

  try {
    const memberships = await getPolicyMemberships(policyId);
    return NextResponse.json(memberships);
  } catch (error) {
    console.error("Failed to fetch policy memberships:", error);
    return NextResponse.json(
      { error: "Failed to fetch memberships" },
      { status: 500 },
    );
  }
}
