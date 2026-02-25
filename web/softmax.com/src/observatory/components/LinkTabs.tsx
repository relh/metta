"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { FC, PropsWithChildren } from "react";

export type LinkTab = {
  id: string;
  label: string;
  href: string;
  isActive?: boolean;
  allowedStageKinds?: string[];
};

type LinkTabsProps = PropsWithChildren<{
  tabs: LinkTab[];
  stageKindsByPool?: Record<string, string>;
  defaultStage?: string | null;
}>;

export const LinkTabs: FC<LinkTabsProps> = ({
  tabs,
  stageKindsByPool,
  defaultStage,
}) => {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedStage = searchParams?.get("stage");
  const hasRequestedStageKind = !!(
    requestedStage && stageKindsByPool?.[requestedStage]
  );
  const selectedStage = hasRequestedStageKind
    ? requestedStage
    : (defaultStage ?? requestedStage ?? null);
  const selectedStageKind =
    selectedStage && stageKindsByPool ? stageKindsByPool[selectedStage] : null;

  const visibleTabs = tabs.filter((tab) => {
    if (!tab.allowedStageKinds || tab.allowedStageKinds.length === 0)
      return true;
    if (!selectedStageKind) return false;
    return tab.allowedStageKinds.includes(selectedStageKind);
  });

  if (selectedStageKind === "sample_teams") {
    return null;
  }

  const hrefWithStage = (href: string): string => {
    if (!selectedStage) return href;
    const [path, query = ""] = href.split("?");
    const nextParams = new URLSearchParams(query);
    nextParams.set("stage", selectedStage);
    const nextQuery = nextParams.toString();
    return nextQuery ? `${path}?${nextQuery}` : path;
  };

  return (
    <div className="flex gap-2">
      {visibleTabs.map((tab) => (
        <Link
          key={tab.id}
          href={hrefWithStage(tab.href)}
          className={clsx(
            "rounded-full border px-4 py-2 text-sm font-medium no-underline",
            pathname === tab.href.split("?")[0]
              ? "border-blue-400 bg-blue-200 text-blue-800 dark:border-blue-700 dark:bg-blue-900 dark:text-blue-200"
              : "border-border-strong text-foreground-subtle hover:bg-surface-alt hover:text-foreground border",
          )}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
};
