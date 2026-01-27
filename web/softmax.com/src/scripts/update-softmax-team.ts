#!/usr/bin/env node
import dotenv from "dotenv";
import jwt from "jsonwebtoken";
import { z } from "zod";

import { prisma } from "@/lib/db/prisma";

dotenv.config();

const ORG_NAME = "Metta-AI";

const OrgMembersResponseSchema = z.array(
  z.object({
    id: z.number(),
    login: z.string(),
  }),
);

type OrgMembersResponse = z.infer<typeof OrgMembersResponseSchema>;

type OrgMember = OrgMembersResponse[number];

/**
 * Generate a JWT for GitHub App authentication.
 */
function generateGitHubAppJWT(clientId: string, privateKeyPem: string): string {
  const now = Math.floor(Date.now() / 1000);

  return jwt.sign(
    {
      iat: now - 60, // Issued 60s ago for clock drift
      exp: now + 10 * 60, // Expires in 10 minutes (GitHub max)
      iss: clientId,
    },
    privateKeyPem,
    { algorithm: "RS256" },
  );
}

/**
 * Get an installation access token using the JWT.
 */
async function getInstallationAccessToken(
  appJwt: string,
  installationId: string,
): Promise<string> {
  const response = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${appJwt}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
    },
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to get installation access token: ${response.status} ${errorText}`,
    );
  }

  const data = await response.json();
  return data.token;
}

/**
 * Get all members of an organization.
 */
async function getOrgMembers(
  accessToken: string,
  org: string,
): Promise<OrgMember[]> {
  const members: OrgMember[] = [];
  let page = 1;
  const perPage = 100;

  while (true) {
    const response = await fetch(
      `https://api.github.com/orgs/${org}/members?per_page=${perPage}&page=${page}`,
      {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${accessToken}`,
          "X-GitHub-Api-Version": "2022-11-28",
        },
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Failed to get org members: ${response.status} ${errorText}`,
      );
    }

    const data = OrgMembersResponseSchema.parse(await response.json());
    if (data.length === 0) {
      break;
    }

    members.push(...data);

    if (data.length < perPage) {
      break;
    }
    page++;
  }

  return members;
}

async function fail(msg: string): Promise<never> {
  console.error(msg);
  await prisma.$disconnect();
  process.exit(1);
}

async function main() {
  try {
    const installationId = process.env.GITHUB_INSTALLATION_ID;
    const privateKey = process.env.GITHUB_APP_PEM;
    const clientId = process.env.GITHUB_CLIENT_ID;

    if (!installationId || !privateKey || !clientId) {
      return await fail("Missing required environment variables");
    }

    // Step 1: Generate JWT for GitHub App
    const appJwt = generateGitHubAppJWT(clientId, privateKey);

    // Step 2: Get installation access token
    const accessToken = await getInstallationAccessToken(
      appJwt,
      installationId,
    );

    // Step 3: Get org members
    const members = await getOrgMembers(accessToken, ORG_NAME);

    // Step 4: Update the database
    const currentUserIds = members.map((m) => m.id.toString());
    const currentLogins = new Set(members.map((m) => m.login));

    // Get existing members for comparison
    const existingMembers = await prisma.gitHubTeamMember.findMany();
    const existingUserIds = new Set(existingMembers.map((m) => m.userId));

    const [deleteResult] = await prisma.$transaction([
      // Delete members no longer in the org
      prisma.gitHubTeamMember.deleteMany({
        where: {
          userId: { notIn: currentUserIds },
        },
      }),
      // Upsert all current members
      ...members.map((member) =>
        prisma.gitHubTeamMember.upsert({
          where: { userId: member.id.toString() },
          update: { login: member.login },
          create: { userId: member.id.toString(), login: member.login },
        }),
      ),
    ]);

    // Calculate changes
    const added = members.filter((m) => !existingUserIds.has(m.id.toString()));
    const removed = existingMembers.filter((m) => !currentLogins.has(m.login));

    console.log(`✓ Synced ${ORG_NAME} team members`);
    console.log(`  Total: ${members.length} members`);
    if (added.length > 0) {
      console.log(
        `  Added (${added.length}): ${added.map((m) => m.login).join(", ")}`,
      );
    }
    if (deleteResult.count > 0) {
      console.log(
        `  Removed (${deleteResult.count}): ${removed.map((m) => m.login).join(", ")}`,
      );
    }
    if (added.length === 0 && deleteResult.count === 0) {
      console.log(`  No changes`);
    }
  } catch (error) {
    return await fail(`Error fetching org members: ${error}`);
  }
}

main();
