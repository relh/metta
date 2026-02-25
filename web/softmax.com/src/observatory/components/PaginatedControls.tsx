"use client";
import { parseAsInteger, useQueryState } from "nuqs";
import { FC, useTransition } from "react";

import { Button } from "./Button";
import { Spinner } from "./Spinner";

export const PaginatedControls: FC<{
  paramName?: string;
  isLastPage?: boolean;
}> = ({ paramName = "page", isLastPage }) => {
  const [isPending, startTransition] = useTransition();
  const [page, setPage] = useQueryState(
    paramName,
    parseAsInteger.withDefault(0).withOptions({
      shallow: false,
      history: "replace",
      startTransition,
    }),
  );
  return (
    <div className="mx-auto flex justify-center">
      <div className="relative flex items-center gap-2 py-5">
        <Button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0 || isPending}
        >
          Previous
        </Button>
        <span className="px-3 py-2 text-sm">Page {page + 1}</span>
        <Button
          onClick={() => setPage((p) => p + 1)}
          disabled={isLastPage || isPending}
        >
          Next
        </Button>
        {isPending && (
          <div className="absolute -right-6">
            <Spinner />
          </div>
        )}
      </div>
    </div>
  );
};
