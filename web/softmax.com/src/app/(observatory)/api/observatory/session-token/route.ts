import crypto from "crypto";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";
import { loadUserById } from "@/lib/user";

const OBSERVATORY_SESSION_TOKEN_TTL_MS = 15 * 60 * 1000;
const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

export async function POST() {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 401, headers: NO_STORE_HEADERS },
    );
  }

  const user = await loadUserById(userId);
  if (!user?.isSoftmaxTeamMember) {
    return NextResponse.json(
      { error: "Observatory services are restricted to Softmax team members." },
      { status: 403, headers: NO_STORE_HEADERS },
    );
  }

  const token = crypto.randomBytes(32).toString("base64url");
  const tokenHash = crypto.createHash("sha256").update(token).digest("hex");
  const expirationTime = new Date(
    Date.now() + OBSERVATORY_SESSION_TOKEN_TTL_MS,
  );

  await prisma.machineToken.create({
    data: {
      userId,
      name: "Observatory Surface Session Token",
      tokenHash,
      expirationTime,
    },
  });

  return NextResponse.json(
    {
      token,
      expiresAt: expirationTime.toISOString(),
    },
    { headers: NO_STORE_HEADERS },
  );
}
