import { AccountCard } from "@/components/account/AccountCard";
import { AccountSignInPrompt } from "@/components/account/AccountSignInPrompt";
import { H2 } from "@/components/H2";
import { LinkButton } from "@/components/LinkButton";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";

export const metadata = {
  title: "Softmax - Account Settings",
  description: "Manage your profile and account settings.",
};

export default async function AccountPage() {
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

  const discordEnabled = !!(
    process.env.DISCORD_CLIENT_ID && process.env.DISCORD_CLIENT_SECRET
  );
  const discordAccount = session?.user?.id
    ? await prisma.account.findFirst({
        where: { userId: session.user.id, provider: "discord" },
        select: { providerAccountId: true },
      })
    : null;

  return (
    <main className="mx-auto w-full max-w-[760px] px-4 py-10 sm:px-6 md:py-14">
      {!isLoggedIn && (
        <section>
          <H2>Sign In</H2>
          <p className="mb-4 text-[#4a5f8c]">Sign in to manage your account.</p>
          <AccountSignInPrompt />
        </section>
      )}

      {isLoggedIn && (
        <section>
          <H2>{profileCompleted ? "Your Account" : "Complete Your Profile"}</H2>
          <div className="mt-4 mb-8">
            {!profileCompleted && (
              <div className="mb-4 rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
                <p className="text-[#4a5f8c]">
                  Please complete your profile to participate in the Alignment
                  League.
                </p>
              </div>
            )}
            <AccountCard
              user={{
                name: dbUser?.name ?? session.user?.name ?? "",
                email: dbUser?.email ?? session.user?.email ?? "",
                institution: dbUser?.institution ?? "",
                profileCompleted,
                tosVersion: dbUser?.tosVersion ?? null,
                consentServiceUpdates: dbUser?.consentServiceUpdates ?? false,
                consentMarketing: dbUser?.consentMarketing ?? false,
              }}
              discordUserId={discordAccount?.providerAccountId}
              discordEnabled={discordEnabled}
            />
          </div>
          <div className="flex gap-4">
            {profileCompleted && (
              <LinkButton href="/observatory" theme="primary">
                Open Observatory
              </LinkButton>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
