"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { FC, PropsWithChildren, use } from "react";

import { AutoRefreshBadge } from "@observatory/components/AutoRefreshBadge";
import {
  Dropdown,
  DropdownMenu,
  DropdownMenuItem,
} from "@observatory/components/Dropdown";
import { ThemeToggle } from "@observatory/components/ThemeToggle";
import {
  episodeJobsRoute,
  evalTasksRoute,
  policiesRoute,
  policyDashboardRoute,
  smartPlugsRoute,
  sqlQueryRoute,
  tournamentRoute,
} from "@observatory/lib/routes";
import {
  seasonNameFromRef,
  seasonTabModeForName,
  type SeasonTabMode,
} from "@observatory/lib/tournament/tabMode";

import { AppContext } from "./AppContext";
import { UserDropdown } from "./UserDropdown";

const MenuLink: FC<PropsWithChildren<{ href: string; isActive: boolean }>> = ({
  href,
  children,
  isActive = false,
}) => {
  return (
    <Link
      href={href}
      className={clsx(
        "hover:bg-surface-alt border-b-2 px-5 py-4 no-underline transition-all duration-200",
        isActive
          ? "border-blue-500 text-blue-500"
          : "text-foreground-muted hover:text-foreground border-transparent",
      )}
    >
      {children}
    </Link>
  );
};

export const TopMenu: FC<{ currentUser: string; devMode: boolean }> = ({
  currentUser,
  devMode,
}) => {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { apiBaseUrl, isSoftmaxTeamMember } = use(AppContext);

  const isPoliciesActive =
    pathname === "/" || pathname.startsWith("/observatory/policies");
  const isTournamentRoute = pathname.startsWith("/observatory/tournament");
  const modeParam = searchParams.get("mode");
  let effectiveMode: SeasonTabMode = "freeplay";
  if (modeParam === "freeplay" || modeParam === "tournament") {
    effectiveMode = modeParam;
  } else if (pathname.startsWith("/observatory/tournament/")) {
    const seasonSegment = pathname.split("/")[3];
    if (seasonSegment) {
      const decoded = decodeURIComponent(seasonSegment);
      effectiveMode = seasonTabModeForName(seasonNameFromRef(decoded));
    }
  }
  const isFreeplayActive = isTournamentRoute && effectiveMode === "freeplay";
  const isTournamentActive =
    isTournamentRoute && effectiveMode === "tournament";

  return (
    <nav className="border-border-strong bg-surface flex items-center justify-between border-b px-5">
      <div className="mx-auto flex max-w-7xl items-center">
        <div className="flex">
          <MenuLink href={policiesRoute()} isActive={isPoliciesActive}>
            Policies
          </MenuLink>
          {isSoftmaxTeamMember && (
            <MenuLink
              href={policyDashboardRoute()}
              isActive={pathname.startsWith("/observatory/policy-dashboard")}
            >
              Policy Dashboard
            </MenuLink>
          )}
          <MenuLink
            href={tournamentRoute({ mode: "freeplay" })}
            isActive={isFreeplayActive}
          >
            Freeplay
          </MenuLink>
          <MenuLink
            href={tournamentRoute({ mode: "tournament" })}
            isActive={isTournamentActive}
          >
            Tournament
          </MenuLink>
          {isSoftmaxTeamMember && (
            <>
              <MenuLink
                href={episodeJobsRoute()}
                isActive={pathname.startsWith("/observatory/episode-job")}
              >
                Episode Jobs
              </MenuLink>
              <MenuLink
                href={sqlQueryRoute()}
                isActive={pathname === "/observatory/sql-query"}
              >
                SQL Query
              </MenuLink>
              <MenuLink
                href={smartPlugsRoute()}
                isActive={pathname.startsWith("/observatory/infra/smart-plugs")}
              >
                Smart Plugs
              </MenuLink>
              <MenuLink
                href={evalTasksRoute()}
                isActive={pathname.startsWith("/observatory/eval-task")}
              >
                Remote Jobs
              </MenuLink>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <AutoRefreshBadge />
        <Dropdown
          render={({ close }) => (
            <DropdownMenu>
              <DropdownMenuItem
                title="Public API"
                onClick={() => {
                  window.open(`${apiBaseUrl}/docs`, "_blank");
                  close();
                }}
              />
              {isSoftmaxTeamMember && (
                <DropdownMenuItem
                  title="Internal API"
                  onClick={() => {
                    window.open("/api/observatory/internal/docs", "_blank");
                    close();
                  }}
                />
              )}
            </DropdownMenu>
          )}
        >
          <span className="text-foreground-muted hover:text-foreground border-border-strong cursor-pointer rounded border px-2 py-1 text-sm transition-colors">
            API Docs
          </span>
        </Dropdown>
        <UserDropdown currentUser={currentUser} devMode={devMode} />
        <ThemeToggle />
      </div>
    </nav>
  );
};
