import { Metadata } from "next";
import { createLoader, parseAsInteger, parseAsString } from "nuqs/server";
import { Suspense } from "react";

import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { SearchParamInput } from "@observatory/components/SearchParamInput";
import { Spinner } from "@observatory/components/Spinner";

import { PoliciesTable } from "./PoliciesTable";

const nuqsParams = {
  q: parseAsString.withDefault(""),
  page: parseAsInteger.withDefault(0),
};

const parseSearchParams = createLoader(nuqsParams);

export default async function PoliciesPage({
  searchParams: rawSearchParams,
}: PageProps<"/observatory/policies">) {
  const { q: nameFilter, page } = await parseSearchParams(rawSearchParams);

  return (
    <StandardPageLayout>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-foreground text-2xl font-semibold">Policies</h1>
          <p className="text-foreground-muted text-sm">
            All policies ordered by creation date
          </p>
        </div>
      </div>

      <div className="bg-surface border-border rounded-lg border shadow-sm">
        <div className="p-5">
          <div className="mb-6 w-full max-w-xs">
            <SearchParamInput paramName="q" placeholder="Search by name..." />
          </div>
          <Suspense
            fallback={
              <div className="grid min-h-80 place-items-center">
                <Spinner size="lg" />
              </div>
            }
          >
            <PoliciesTable nameFilter={nameFilter} page={page} />
          </Suspense>
        </div>
      </div>
    </StandardPageLayout>
  );
}

export const metadata: Metadata = {
  title: "Policies | Observatory",
};
