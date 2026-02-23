import { Prisma } from "@/generated/prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";
import { CURRENT_TOS_VERSION } from "@/lib/tos";

const updateProfileSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  email: z
    .string()
    .trim()
    .min(1, "Email is required")
    .max(320)
    .email("Email must be valid"),
  institution: z.string().trim().min(1, "Institution is required").max(200),
  hasAcceptedTos: z.boolean(),
  consentServiceUpdates: z.boolean().optional(),
  consentMarketing: z.boolean().optional(),
});

export async function GET() {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const dbUser = await prisma.user.findUnique({
    where: { id: session.user.id },
    select: {
      name: true,
      email: true,
      image: true,
      institution: true,
      profileCompleted: true,
      tosAcceptedAt: true,
      tosVersion: true,
      consentServiceUpdates: true,
      consentMarketing: true,
    },
  });

  if (!dbUser) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  return NextResponse.json({
    user: {
      id: session.user.id,
      name: dbUser.name,
      email: dbUser.email,
      image: dbUser.image,
      institution: dbUser.institution,
      profileCompleted: dbUser.profileCompleted,
      tosAcceptedAt: dbUser.tosAcceptedAt,
      tosVersion: dbUser.tosVersion,
      consentServiceUpdates: dbUser.consentServiceUpdates,
      consentMarketing: dbUser.consentMarketing,
    },
  });
}

export async function POST(request: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const userId = session.user.id;

  let json: unknown;
  try {
    json = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const parsed = updateProfileSchema.safeParse(json);
  if (!parsed.success) {
    const { fieldErrors, formErrors } = parsed.error.flatten();
    return NextResponse.json(
      {
        error: "Invalid input",
        details: { fieldErrors, formErrors },
      },
      { status: 400 },
    );
  }

  const {
    name,
    email,
    institution,
    hasAcceptedTos,
    consentServiceUpdates,
    consentMarketing,
  } = parsed.data;

  const ipAddress =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? null;
  const userAgent = request.headers.get("user-agent") ?? null;

  const currentUser = await prisma.user.findUnique({
    where: { id: userId },
    select: {
      tosAcceptedAt: true,
      tosVersion: true,
      consentServiceUpdates: true,
      consentMarketing: true,
    },
  });

  if (!currentUser) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  const consentRecords: Prisma.ConsentRecordCreateManyInput[] = [];

  // ToS consent: record when newly accepting or re-accepting for a new version
  const isNewTosAcceptance =
    hasAcceptedTos &&
    (!currentUser.tosAcceptedAt ||
      currentUser.tosVersion !== CURRENT_TOS_VERSION);

  if (isNewTosAcceptance) {
    consentRecords.push({
      userId,
      consentType: "tos",
      granted: true,
      version: CURRENT_TOS_VERSION,
      ipAddress,
      userAgent,
    });
  }

  // Communication consent: only record changes
  if (
    consentServiceUpdates !== undefined &&
    consentServiceUpdates !== currentUser.consentServiceUpdates
  ) {
    consentRecords.push({
      userId,
      consentType: "comms_service",
      granted: consentServiceUpdates,
      ipAddress,
      userAgent,
    });
  }

  if (
    consentMarketing !== undefined &&
    consentMarketing !== currentUser.consentMarketing
  ) {
    consentRecords.push({
      userId,
      consentType: "comms_marketing",
      granted: consentMarketing,
      ipAddress,
      userAgent,
    });
  }

  const tosAcceptedAt = isNewTosAcceptance
    ? new Date()
    : currentUser.tosAcceptedAt;
  const tosVersion = isNewTosAcceptance
    ? CURRENT_TOS_VERSION
    : currentUser.tosVersion;

  const profileCompleted =
    tosAcceptedAt !== null &&
    name.trim().length > 0 &&
    email.trim().length > 0 &&
    institution.trim().length > 0;

  try {
    const updatedUser = await prisma.$transaction(async (tx) => {
      if (consentRecords.length > 0) {
        await tx.consentRecord.createMany({ data: consentRecords });
      }

      return tx.user.update({
        where: { id: userId },
        data: {
          name,
          email,
          institution,
          profileCompleted,
          tosAcceptedAt,
          tosVersion,
          consentServiceUpdates:
            consentServiceUpdates ?? currentUser.consentServiceUpdates,
          consentMarketing: consentMarketing ?? currentUser.consentMarketing,
        },
        select: {
          name: true,
          email: true,
          institution: true,
          profileCompleted: true,
          tosAcceptedAt: true,
          tosVersion: true,
          consentServiceUpdates: true,
          consentMarketing: true,
        },
      });
    });

    return NextResponse.json({ user: updatedUser });
  } catch (error) {
    console.error("Failed to update user profile:", error);
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === "P2002"
    ) {
      return NextResponse.json(
        { error: "That email is already in use. Please choose another." },
        { status: 400 },
      );
    }
    return NextResponse.json(
      { error: "Unable to update profile" },
      { status: 500 },
    );
  }
}
