import { Prisma } from "@/generated/prisma/client";
import { NextResponse } from "next/server";
import { z } from "zod";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";

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
});

export async function GET() {
  try {
    const session = await auth();

    if (!session?.user) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    return NextResponse.json({
      user: {
        id: session.user.id,
        name: session.user.name,
        email: session.user.email,
        image: session.user.image,
      },
    });
  } catch (error) {
    console.error("Error fetching user:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

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

  const { name, email, institution, hasAcceptedTos } = parsed.data;

  const profileCompleted =
    hasAcceptedTos &&
    name.trim().length > 0 &&
    email.trim().length > 0 &&
    institution.trim().length > 0;

  try {
    const updatedUser = await prisma.user.update({
      where: { id: session.user.id },
      data: {
        name,
        email,
        institution,
        profileCompleted,
      },
      select: {
        name: true,
        email: true,
        institution: true,
        profileCompleted: true,
      },
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
