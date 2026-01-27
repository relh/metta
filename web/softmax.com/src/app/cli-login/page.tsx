import { redirect } from "next/navigation";

import { AccountCard } from "@/components/account/AccountCard";
import { AccountSignInPrompt } from "@/components/account/AccountSignInPrompt";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/db/prisma";

export const dynamic = "force-dynamic";

export default async function CliLoginPage({
  searchParams,
}: {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}) {
  const callbackParam = String((await searchParams).callback);

  if (!callbackParam) {
    redirect("/alignmentleague");
  }

  let callback: string;
  try {
    const callbackUrl = new URL(callbackParam);
    if (
      callbackUrl.hostname !== "127.0.0.1" &&
      callbackUrl.hostname !== "localhost" &&
      !callbackUrl.hostname.endsWith(".softmax-research.net")
    ) {
      redirect("/alignmentleague");
    }
    callback = callbackUrl.toString();
  } catch {
    redirect("/alignmentleague");
  }

  const session = await auth();

  if (!session?.user?.id) {
    return (
      <main className="flex min-h-screen flex-col items-center px-4 py-16">
        <div className="w-full max-w-lg space-y-8">
          <header className="space-y-3 text-center">
            <h1 className="text-3xl font-semibold lowercase">
              sign in to continue
            </h1>
            <p className="text-sm text-[#4a5f8c]">
              You&apos;ll return to the CLI as soon as you complete your
              profile.
            </p>
          </header>
          <AccountSignInPrompt />
        </div>
      </main>
    );
  }

  const dbUser = await prisma.user.findUnique({
    where: { id: session.user.id },
    select: {
      name: true,
      email: true,
      institution: true,
      profileCompleted: true,
    },
  });

  if (dbUser?.profileCompleted) {
    redirect(`/api/tokens/cli?callback=${encodeURIComponent(callback)}`);
  }

  const hydratedUser = {
    name: dbUser?.name ?? session.user.name ?? "",
    email: dbUser?.email ?? session.user.email ?? "",
    institution: dbUser?.institution ?? "",
    profileCompleted: dbUser?.profileCompleted ?? false,
  };

  return (
    <div className="min-h-screen bg-[#fffdf4] text-[#0e2758]">
      <main className="flex flex-col items-center px-4 py-16">
        <div className="w-full max-w-xl space-y-8">
          <header className="space-y-3 text-center">
            <h1 className="text-3xl font-semibold lowercase">
              complete your profile
            </h1>
            <p className="text-sm text-[#4a5f8c]">
              Fill in the details below. We&apos;ll finish signing you in once
              everything is complete.
            </p>
          </header>
          <AccountCard user={hydratedUser} />
          <p className="text-center text-xs text-[#4a5f8c]">
            Keep this window open. As soon as your profile is complete,
            we&apos;ll send the confirmation back to the CLI.
          </p>
        </div>
      </main>
    </div>
  );
}
