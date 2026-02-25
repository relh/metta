import { AccountSignInPrompt } from "@/components/account/AccountSignInPrompt";
import { H2 } from "@/components/H2";
import { HeroLayout } from "@/components/HeroLayout";
import { LinkButton } from "@/components/LinkButton";
import { auth } from "@/lib/auth";
import { S3_IMAGE_BASE } from "@/lib/constants";
import AlignmentLeague from "@/mdx/alignmentleague.mdx";

export const metadata = {
  title: "Softmax - Alignment League Benchmark",
  description:
    "Compete in the Alignment League Benchmark and contribute to AI alignment research.",
};

export default async function AlignmentLeaguePage() {
  const session = await auth();
  const isLoggedIn = !!session?.user;

  return (
    <HeroLayout
      image={`${S3_IMAGE_BASE}/deepspace.png`}
      fade
      sentence="the alignment league benchmark"
    >
      <div className="mb-8">
        <AlignmentLeague />

        {!isLoggedIn && (
          <section id="join-the-league" className="mt-8">
            <H2>Join the League</H2>
            <AccountSignInPrompt />
          </section>
        )}

        {isLoggedIn && (
          <section className="mt-8">
            <div className="flex gap-4">
              <LinkButton href="/account" theme="primary">
                Account Settings
              </LinkButton>
              <LinkButton href="/observatory">Observatory</LinkButton>
            </div>
          </section>
        )}
      </div>
    </HeroLayout>
  );
}
