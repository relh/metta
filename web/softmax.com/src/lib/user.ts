import crypto from "crypto";
import { Prisma } from "@/generated/prisma/client";

import { prisma } from "@/lib/db/prisma";
import { isDevMode } from "@/observatory/config";

export type UserInfo = {
  id: string;
  email: string | null;
  name: string | null;
  discordId: string | null;
  isSoftmaxTeamMember: boolean;
};

type DbUserWithAccounts = Prisma.UserGetPayload<{
  include: { accounts: true };
}>;

async function getSoftmaxTeamMemberIds(
  dbUsers: DbUserWithAccounts[],
): Promise<Set<string>> {
  const allGitHubAccountIds = dbUsers.flatMap((user) =>
    user.accounts
      .filter((a) => a.provider === "github")
      .map((a) => a.providerAccountId),
  );

  const teamMembers = await prisma.gitHubTeamMember.findMany({
    where: {
      userId: { in: allGitHubAccountIds },
    },
    select: { userId: true },
  });

  return new Set(teamMembers.map((member) => member.userId));
}

function buildUserInfo(
  dbUser: DbUserWithAccounts,
  teamMemberIds: Set<string>,
): UserInfo {
  const gitHubAccountIds = dbUser.accounts
    .filter((a) => a.provider === "github")
    .map((a) => a.providerAccountId);

  let isSoftmaxTeamMember = gitHubAccountIds.some((id) =>
    teamMemberIds.has(id),
  );
  if (isDevMode()) {
    isSoftmaxTeamMember = true;
  }

  const discordId =
    dbUser.accounts.find((a) => a.provider === "discord")?.providerAccountId ??
    null;

  return {
    id: dbUser.id,
    email: dbUser.email,
    name: dbUser.name,
    discordId,
    isSoftmaxTeamMember,
  };
}

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
  const teamMemberIds = await getSoftmaxTeamMemberIds([machineToken.user]);
  return buildUserInfo(machineToken.user, teamMemberIds);
}

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
  const teamMemberIds = await getSoftmaxTeamMemberIds([dbUser]);
  return buildUserInfo(dbUser, teamMemberIds);
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
  const teamMemberIds = await getSoftmaxTeamMemberIds(dbUsers);

  // Build result map
  const result = new Map<string, UserInfo>();
  for (const dbUser of dbUsers) {
    result.set(dbUser.id, buildUserInfo(dbUser, teamMemberIds));
  }

  return result;
}

export async function loadAllUsers(): Promise<UserInfo[]> {
  const dbUsers = await prisma.user.findMany({
    include: {
      accounts: true,
    },
  });
  const teamMemberIds = await getSoftmaxTeamMemberIds(dbUsers);
  return dbUsers.map((dbUser) => buildUserInfo(dbUser, teamMemberIds));
}
