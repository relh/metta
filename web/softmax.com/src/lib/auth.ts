import "server-only";

import { PrismaAdapter } from "@auth/prisma-adapter";
import NextAuth, { NextAuthConfig } from "next-auth";
import { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";

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
    secret: process.env.NEXTAUTH_SECRET,
  };

  return config;
}

export const { handlers, signIn, signOut, auth } = NextAuth(buildAuthConfig());
