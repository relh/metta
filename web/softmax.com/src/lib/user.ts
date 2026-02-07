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

// used by /api/users/resolve for bulk user lookups
export async function loadUsersByIds(
  ids: string[],
): Promise<Map<string, UserInfo>> {
  if (ids.length === 0) {
    return new Map();
  }

  const dbUsers = await prisma.user.findMany({
    where: { id: { in: ids } },
    include: {
      accounts: true,
    },
  });

  // Collect all GitHub account IDs for a single team membership query
  const allGitHubAccountIds = dbUsers.flatMap((user) =>
    user.accounts
      .filter((a) => a.provider === "github")
      .map((a) => a.providerAccountId),
  );

  // Fetch all team memberships in one query
  const teamMembers = await prisma.gitHubTeamMember.findMany({
    where: {
      userId: { in: allGitHubAccountIds },
    },
    select: { userId: true },
  });

  const teamMemberIds = new Set(teamMembers.map((m) => m.userId));

  // Build result map
  const result = new Map<string, UserInfo>();
  for (const dbUser of dbUsers) {
    const gitHubAccountIds = dbUser.accounts
      .filter((a) => a.provider === "github")
      .map((a) => a.providerAccountId);

    const isSoftmaxTeamMember = gitHubAccountIds.some((id) =>
      teamMemberIds.has(id),
    );

    result.set(dbUser.id, {
      id: dbUser.id,
      email: dbUser.email,
      name: dbUser.name,
      isSoftmaxTeamMember,
    });
  }

  return result;
}
