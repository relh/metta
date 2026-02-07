import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { loadUsersByIds, UserInfo } from "@/lib/user";

const requestSchema = z.object({
  userIds: z.array(z.string()),
});

type Response =
  | {
      users: Record<string, UserInfo | null>;
    }
  | { error: string };

function typedResponse(
  response: Response,
  status: number = 200,
): NextResponse<Response> {
  return NextResponse.json(response, { status });
}

function safeCompare(a: string, b: string): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

export async function POST(request: NextRequest) {
  try {
    // Validate auth secret
    const authSecret = request.headers.get("X-Auth-Secret");
    const expectedSecret = process.env.OBSERVATORY_AUTH_SECRET;

    if (!expectedSecret) {
      console.error("OBSERVATORY_AUTH_SECRET not configured");
      return typedResponse({ error: "Server misconfigured" }, 500);
    }

    if (!authSecret || !safeCompare(authSecret, expectedSecret)) {
      return typedResponse({ error: "Unauthorized" }, 401);
    }

    // Parse and validate request body
    let json: unknown;
    try {
      json = await request.json();
    } catch {
      return typedResponse({ error: "Invalid JSON body" }, 400);
    }

    const parsed = requestSchema.safeParse(json);
    if (!parsed.success) {
      return typedResponse({ error: "Invalid request body" }, 400);
    }

    const { userIds } = parsed.data;

    // Resolve all users in bulk
    const usersMap = await loadUsersByIds(userIds);

    // Build response map (include null for missing users)
    const users: Record<string, UserInfo | null> = {};
    for (const id of userIds) {
      users[id] = usersMap.get(id) ?? null;
    }

    return typedResponse({ users });
  } catch (error) {
    console.error("User resolution error:", error);
    return typedResponse({ error: "Resolution failed" }, 500);
  }
}
