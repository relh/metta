import "server-only";

import NextAuth, { NextAuthConfig } from "next-auth";
import { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import Discord from "next-auth/providers/discord";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";

import { PrismaAdapter } from "@auth/prisma-adapter";

import { announceNewSoftmaxSignup } from "@/lib/discord-announcements";
import { prisma } from "./db/prisma";

function buildAuthConfig(): NextAuthConfig {
  const providers: Provider[] = [];

  if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET) {
    providers.push(
      GitHub({
        clientId: process.env.GITHUB_CLIENT_ID,
        clientSecret: process.env.GITHUB_CLIENT_SECRET,
      }),
    );
  }
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
    providers.push(
      Google({
        clientId: process.env.GOOGLE_CLIENT_ID,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      }),
    );
  }
  if (process.env.DISCORD_CLIENT_ID && process.env.DISCORD_CLIENT_SECRET) {
    providers.push(
      Discord({
        clientId: process.env.DISCORD_CLIENT_ID,
        clientSecret: process.env.DISCORD_CLIENT_SECRET,
        authorization: { params: { scope: "identify" } },
      }),
    );
  }
  if (providers.length === 0) {
    console.warn(
      "No OAuth providers configured. Using disabled placeholder provider so build can proceed.",
    );
    providers.push(
      Credentials({
        id: "auth-disabled",
        name: "Authentication Disabled",
        credentials: {},
        async authorize() {
          throw new Error("Authentication is not configured.");
        },
      }),
    );
  }

  const config: NextAuthConfig = {
    // @auth/prisma-adapter types expect PrismaClient from @prisma/client,
    // which Prisma 7 no longer exports (generated client lives at @/generated/prisma/client).
    // Runtime API is compatible; cast until the adapter ships Prisma 7 support.
    adapter: PrismaAdapter(prisma as any),
    providers,
    callbacks: {
      async signIn({ account }) {
        if (account?.provider === "discord") {
          const { auth: getSession } = await import("@/lib/auth");
          const session = await getSession();
          if (!session?.user?.id) return false;

          // special case: used only for linking discord account to a user account
          await prisma.account.upsert({
            where: {
              provider_providerAccountId: {
                provider: account.provider,
                providerAccountId: account.providerAccountId,
              },
            },
            update: { userId: session.user.id },
            create: {
              userId: session.user.id,
              type: account.type,
              provider: account.provider,
              providerAccountId: account.providerAccountId,
              access_token: account.access_token as string | undefined,
              refresh_token: account.refresh_token as string | undefined,
              expires_at: account.expires_at,
              token_type: account.token_type,
              scope: account.scope,
            },
          });

          return "/account";
        }
        return true;
      },
      async session({ session, user }) {
        if (session.user) {
          session.user.id = user.id;
        }
        return session;
      },
      async redirect({ url, baseUrl }) {
        try {
          const target = new URL(url, baseUrl);
          if (target.origin === baseUrl) {
            return target.toString();
          }
        } catch (_) {
          // fall through to default
        }
        return baseUrl;
      },
    },
    events: {
      async signIn({ user, account, profile, isNewUser }) {
        if (!isNewUser || !account) {
          return;
        }
        await announceNewSoftmaxSignup({ user, account, profile });
      },
    },
    secret: process.env.NEXTAUTH_SECRET,
  };

  return config;
}

export const { handlers, signIn, signOut, auth } = NextAuth(buildAuthConfig());
