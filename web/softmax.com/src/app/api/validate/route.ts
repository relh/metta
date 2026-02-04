import { NextRequest, NextResponse } from "next/server";

import { loadUserByMachineToken, UserInfo } from "@/lib/user";

type Response =
  | {
      valid: true;
      user: UserInfo;
    }
  | { valid: false; error: string };

function typedResponse(
  response: Response,
  status: number = 200,
): NextResponse<Response> {
  return NextResponse.json(response, { status });
}

export async function GET(request: NextRequest) {
  try {
    // First check for machine token in headers
    const authToken =
      request.headers.get("X-Auth-Token") ||
      request.headers.get("Authorization")?.replace(/^bearer /i, "");

    if (!authToken) {
      return typedResponse({ valid: false, error: "No token provided" }, 401);
    }

    const user = await loadUserByMachineToken(authToken);
    if (user) {
      return typedResponse({
        valid: true,
        user,
      });
    }

    // If token validation failed, return 401
    return typedResponse(
      { valid: false, error: "Invalid or expired token" },
      401,
    );
  } catch (error) {
    console.error("Session validation error:", error);
    return typedResponse({ valid: false, error: "Validation failed" }, 500);
  }
}
