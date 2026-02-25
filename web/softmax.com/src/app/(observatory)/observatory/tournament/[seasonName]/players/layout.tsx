import { Suspense } from "react";

import { Card } from "@observatory/components/Card";
import { Spinner } from "@observatory/components/Spinner";

export default function PlayersLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Card>
      <Suspense
        fallback={
          <div className="grid min-h-80 place-items-center">
            <Spinner size="lg" />
          </div>
        }
      >
        {children}
      </Suspense>
    </Card>
  );
}

export async function generateMetadata({
  params,
}: LayoutProps<"/observatory/tournament/[seasonName]/players">) {
  const { seasonName } = await params;
  return {
    title: `Players for Season ${seasonName} | Observatory`,
  };
}
