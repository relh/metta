"use client";

import clsx from "clsx";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FC, useTransition } from "react";

import { Spinner } from "@observatory/components/Spinner";
import type { StageStats } from "@observatory/lib/api";

import { stageLabel } from "./stageSelection";

export const StageTabs: FC<{ stages: StageStats[]; selectedStage: string }> = ({
  stages,
  selectedStage,
}) => {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const tabs = stages.map((s) => ({ id: s.name, label: stageLabel(s.name) }));

  return (
    <div className="flex items-center gap-2">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => {
            if (tab.id === selectedStage) return;
            startTransition(() => {
              const nextParams = new URLSearchParams(
                searchParams?.toString() ?? "",
              );
              nextParams.set("stage", tab.id);
              const query = nextParams.toString();
              router.replace(query ? `${pathname}?${query}` : pathname);
            });
          }}
          className={clsx(
            "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors",
            selectedStage === tab.id
              ? "border-blue-400 bg-blue-200 text-blue-800 dark:border-blue-700 dark:bg-blue-900 dark:text-blue-200"
              : "border-border-strong text-foreground-subtle hover:bg-surface-alt hover:text-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
      {isPending && <Spinner />}
    </div>
  );
};
