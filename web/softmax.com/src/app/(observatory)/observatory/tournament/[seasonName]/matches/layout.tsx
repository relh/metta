import { Card } from "@observatory/components/Card";

export default function MatchesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <Card>{children}</Card>;
}

export async function generateMetadata({
  params,
}: PageProps<"/observatory/tournament/[seasonName]/matches">) {
  const { seasonName } = await params;
  return {
    title: `Matches for Season ${seasonName} | Observatory`,
  };
}
