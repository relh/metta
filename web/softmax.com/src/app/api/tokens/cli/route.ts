import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const baseUrl = new URL(process.env.NEXTAUTH_URL || "https://localhost:3000");
  requestUrl.hostname = baseUrl.hostname;
  requestUrl.port = baseUrl.port;
  requestUrl.protocol = baseUrl.protocol;

  try {
    // Get callback URL from query parameters
    const { searchParams } = requestUrl;
    const callback = searchParams.get("callback");

    if (!callback) {
      return NextResponse.json(
        { error: "Missing callback parameter" },
        { status: 400 },
      );
    }

    // Validate callback URL - must be localhost or softmax-research.net
    const callbackUrl = new URL(callback);
    if (
      callbackUrl.hostname !== "127.0.0.1" &&
      callbackUrl.hostname !== "localhost" &&
      !callbackUrl.hostname.endsWith(".softmax-research.net")
    ) {
      return NextResponse.json(
        { error: "Invalid callback URL" },
        { status: 400 },
      );
    }

    // Check if user is authenticated
    const session = await auth();
    if (!session?.user?.id || !session?.user?.email) {
      const loginUrl = new URL("/cli-login", requestUrl);
      loginUrl.searchParams.set("callback", callback);
      return NextResponse.redirect(loginUrl.toString());
    }

    const dbUser = await prisma.user.findUnique({
      where: { id: session.user.id },
      select: { profileCompleted: true },
    });

    if (!dbUser?.profileCompleted) {
      const profileUrl = new URL("/cli-login", requestUrl);
      profileUrl.searchParams.set("callback", callback);
      return NextResponse.redirect(profileUrl.toString());
    }

    // Generate a secure random token
    const token = crypto.randomBytes(32).toString("base64url");

    // Hash the token for storage
    const tokenHash = crypto.createHash("sha256").update(token).digest("hex");

    // Set expiration time (365 days from now)
    const expirationTime = new Date();
    expirationTime.setDate(expirationTime.getDate() + 365);

    // Store the token in the database
    await prisma.machineToken.create({
      data: {
        userId: session.user.id,
        name: "CLI Token",
        tokenHash,
        expirationTime,
      },
    });

    // Build redirect URL with token parameter
    const redirectUrl = new URL(callback);
    redirectUrl.searchParams.set("token", token);

    // Redirect to callback with token
    return NextResponse.redirect(redirectUrl.toString());
  } catch (error) {
    console.error("Error creating CLI token:", error);
    return NextResponse.json(
      { error: "Failed to create CLI token" },
      { status: 500 },
    );
  }
}
