import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";

import { loadAllUsers, UserInfo } from "@/lib/user";

type Response =
  | {
      users: UserInfo[];
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

export async function GET(request: NextRequest) {
  try {
    const authSecret = request.headers.get("X-Auth-Secret");
    const expectedSecret = process.env.OBSERVATORY_AUTH_SECRET;

    if (!expectedSecret) {
      console.error("OBSERVATORY_AUTH_SECRET not configured");
      return typedResponse({ error: "Server misconfigured" }, 500);
    }

    if (!authSecret || !safeCompare(authSecret, expectedSecret)) {
      return typedResponse({ error: "Unauthorized" }, 401);
    }

    const users = await loadAllUsers();
    return typedResponse({ users });
  } catch (error) {
    console.error("User listing error:", error);
    return typedResponse({ error: "Listing failed" }, 500);
  }
}
