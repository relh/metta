import { Suspense } from "react";

import { AccountCard } from "@/components/account/AccountCard";
import { AccountSignInPrompt } from "@/components/account/AccountSignInPrompt";
import { H2 } from "@/components/H2";
import { HeroLayout } from "@/components/HeroLayout";
import { ScrollToButton } from "@/components/ScrollToButton";
import { auth } from "@/lib/auth";
import { S3_IMAGE_BASE } from "@/lib/constants";
import { prisma } from "@/lib/db/prisma";
import {
  findDefaultSeason,
  getPolicies,
  getSeasons,
  type PolicySummary,
} from "@/lib/observatoryClient";
import AlignmentLeague from "@/mdx/alignmentleague.mdx";

import { LeaderboardWithFilters } from "./LeaderboardWithFilters";
import { RecentMatches } from "./RecentMatches";
import { YourPolicies } from "./YourPolicies";

export const metadata = {
  title: "Softmax - Alignment League Benchmark",
  description:
    "Compete in the Alignment League Benchmark and contribute to AI alignment research.",
};

export default async function AlignmentLeaguePage() {
  const session = await auth();
  const dbUser = session?.user?.id
    ? await prisma.user.findUnique({
        where: { id: session.user.id },
        select: {
          name: true,
          email: true,
          institution: true,
          profileCompleted: true,
          tosVersion: true,
          consentServiceUpdates: true,
          consentMarketing: true,
        },
      })
    : null;

  const isLoggedIn = !!session?.user;
  const profileCompleted = dbUser?.profileCompleted ?? false;

  let myPolicies: PolicySummary[] = [];
  if (isLoggedIn && profileCompleted && session?.user?.id) {
    try {
      const seasons = await getSeasons();
      const defaultSeason = findDefaultSeason(seasons);
      if (defaultSeason) {
        myPolicies = await getPolicies({
          seasonName: defaultSeason.name,
          userId: session.user.id,
          mine: true,
        });
      }
    } catch (error) {
      console.error("Failed to fetch policies:", error);
    }
  }

  return (
    <HeroLayout
      image={`${S3_IMAGE_BASE}/deepspace.png`}
      fade
      sentence="the alignment league benchmark"
    >
      <div className="mb-8">
        <AlignmentLeague />

        {!isLoggedIn && (
          <div className="my-8">
            <ScrollToButton targetId="join-the-league" theme="primary">
              Join the league
            </ScrollToButton>
          </div>
        )}

        <Suspense fallback={<div className="text-[#4a5f8c]">Loading...</div>}>
          <LeaderboardWithFilters />
        </Suspense>

        <Suspense fallback={<div className="text-[#4a5f8c]">Loading...</div>}>
          <RecentMatches />
        </Suspense>

        {isLoggedIn && profileCompleted && (
          <Suspense fallback={<div className="text-[#4a5f8c]">Loading...</div>}>
            <YourPolicies policies={myPolicies} />
          </Suspense>
        )}

        {!isLoggedIn && (
          <section id="join-the-league" className="mt-8">
            <H2>Join the League</H2>
            <AccountSignInPrompt />
          </section>
        )}

        {isLoggedIn && !profileCompleted && (
          <section className="mt-8">
            <H2>Complete Your Profile</H2>
            <div className="mt-4 rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
              <p className="text-[#4a5f8c]">
                Please complete your profile to participate in the Alignment
                League.
              </p>
              <div className="mt-4">
                <AccountCard
                  user={{
                    name: dbUser?.name ?? session.user?.name ?? "",
                    email: dbUser?.email ?? session.user?.email ?? "",
                    institution: dbUser?.institution ?? "",
                    profileCompleted: false,
                    tosVersion: dbUser?.tosVersion ?? null,
                    consentServiceUpdates:
                      dbUser?.consentServiceUpdates ?? false,
                    consentMarketing: dbUser?.consentMarketing ?? false,
                  }}
                />
              </div>
            </div>
          </section>
        )}

        {isLoggedIn && profileCompleted && (
          <section className="mt-8">
            <H2>Your Account</H2>
            <div className="mt-4">
              <AccountCard
                user={{
                  name: dbUser?.name ?? session.user?.name ?? "",
                  email: dbUser?.email ?? session.user?.email ?? "",
                  institution: dbUser?.institution ?? "",
                  profileCompleted: true,
                  tosVersion: dbUser?.tosVersion ?? null,
                  consentServiceUpdates: dbUser?.consentServiceUpdates ?? false,
                  consentMarketing: dbUser?.consentMarketing ?? false,
                }}
              />
            </div>
          </section>
        )}
      </div>
    </HeroLayout>
  );
}
