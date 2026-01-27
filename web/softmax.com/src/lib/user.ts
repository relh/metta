import crypto from "crypto";

import { prisma } from "@/lib/db/prisma";

export type UserInfo = {
  id: string;
  email: string | null;
  name: string | null;
  isSoftmaxTeamMember: boolean;
};

// used by /api/validate
export async function loadUserByMachineToken(
  token: string,
): Promise<UserInfo | null> {
  // Hash the token to compare with stored hash
  const tokenHash = crypto.createHash("sha256").update(token).digest("hex");

  // Find the token in the database
  const machineToken = await prisma.machineToken.findUnique({
    where: { tokenHash },
    include: {
      user: {
        include: {
          accounts: true,
        },
      },
    },
  });

  // Check if token exists and is not expired
  if (!machineToken || machineToken.expirationTime < new Date()) {
    return null;
  }

  // Update last used timestamp
  await prisma.machineToken.update({
    where: { id: machineToken.id },
    data: { lastUsedAt: new Date() },
  });

  const isSoftmaxTeamMember = !!(await prisma.gitHubTeamMember.findFirst({
    where: {
      userId: {
        in: machineToken.user.accounts
          .filter((a) => a.provider === "github")
          .map((a) => a.providerAccountId),
      },
    },
  }));

  return {
    id: machineToken.user.id,
    email: machineToken.user.email,
    name: machineToken.user.name,
    isSoftmaxTeamMember,
  };
}

// used by observatoryClient.ts to pass X-User-* headers to observatory API
export async function loadUserById(id: string): Promise<UserInfo | null> {
  const dbUser = await prisma.user.findUnique({
    where: { id },
    include: {
      accounts: true,
    },
  });

  if (!dbUser) {
    return null;
  }

  const isSoftmaxTeamMember = !!(await prisma.gitHubTeamMember.findFirst({
    where: {
      userId: {
        in: dbUser.accounts
          .filter((a) => a.provider === "github")
          .map((a) => a.providerAccountId),
      },
    },
  }));

  return {
    id: dbUser.id,
    email: dbUser.email,
    name: dbUser.name,
    isSoftmaxTeamMember,
  };
}
