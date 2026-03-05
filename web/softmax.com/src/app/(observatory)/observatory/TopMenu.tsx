"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  CSSProperties,
  FC,
  PropsWithChildren,
  use,
  useEffect,
  useState,
} from "react";

import { AutoRefreshBadge } from "@observatory/components/AutoRefreshBadge";
import {
  Dropdown,
  DropdownMenu,
  DropdownMenuItem,
} from "@observatory/components/Dropdown";
import { ThemeToggle } from "@observatory/components/ThemeToggle";
import {
  bardoRoute,
  chatpropRoute,
  diagnoseRoute,
  episodeJobsRoute,
  evalTasksRoute,
  pantheonRoute,
  policiesRoute,
  policyDashboardRoute,
  trainBoardRoute,
  smartPlugsRoute,
  sqlQueryRoute,
  tournamentRoute,
} from "@observatory/lib/routes";
import {
  seasonNameFromRef,
  seasonTabModeForTournamentType,
  type SeasonTabMode,
} from "@observatory/lib/tournament/tabMode";

import { AppContext } from "./AppContext";
import { UserDropdown } from "./UserDropdown";

const MenuLink: FC<
  PropsWithChildren<{
    href: string;
    isActive: boolean;
    className?: string;
    activeClassName?: string;
    inactiveClassName?: string;
    style?: CSSProperties;
  }>
> = ({
  href,
  children,
  isActive = false,
  className,
  activeClassName,
  inactiveClassName,
  style,
}) => {
  return (
    <Link
      href={href}
      style={style}
      className={clsx(
        "hover:bg-surface-alt border-b-2 px-5 py-4 no-underline transition-all duration-200",
        isActive
          ? (activeClassName ?? "border-blue-500 text-blue-500")
          : (inactiveClassName ??
              "text-foreground-muted hover:text-foreground border-transparent"),
        className,
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
  const { apiBaseUrl, isSoftmaxTeamMember, repo } = use(AppContext);

  const isPoliciesActive =
    pathname === "/" || pathname.startsWith("/observatory/policies");
  const isTournamentRoute = pathname.startsWith("/observatory/tournament");
  const modeParam = searchParams.get("mode");
  const [inferredMode, setInferredMode] = useState<SeasonTabMode | null>(null);

  useEffect(() => {
    let cancelled = false;

    if (modeParam === "freeplay" || modeParam === "tournament") {
      setInferredMode(modeParam);
      return () => {
        cancelled = true;
      };
    }

    if (!pathname.startsWith("/observatory/tournament/")) {
      setInferredMode(null);
      return () => {
        cancelled = true;
      };
    }

    const seasonSegment = pathname.split("/")[3];
    if (!seasonSegment) {
      setInferredMode(null);
      return () => {
        cancelled = true;
      };
    }

    let decoded = seasonSegment;
    try {
      decoded = decodeURIComponent(seasonSegment);
    } catch {
      decoded = seasonSegment;
    }
    const seasonName = seasonNameFromRef(decoded);

    repo
      .getSeason(seasonName)
      .then((season) => {
        if (!cancelled) {
          setInferredMode(
            seasonTabModeForTournamentType(season.tournament_type),
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInferredMode("freeplay");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [modeParam, pathname, repo]);

  const effectiveMode: SeasonTabMode =
    modeParam === "freeplay" || modeParam === "tournament"
      ? modeParam
      : (inferredMode ?? "freeplay");
  const isFreeplayActive = isTournamentRoute && effectiveMode === "freeplay";
  const isTournamentActive =
    isTournamentRoute && effectiveMode === "tournament";

  return (
    <nav className="border-border-strong bg-surface flex items-start justify-between border-b px-5">
      <div className="mx-auto flex max-w-7xl flex-col">
        <div className="flex">
          <MenuLink href={policiesRoute()} isActive={isPoliciesActive}>
            Policies
          </MenuLink>
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
                href={evalTasksRoute()}
                isActive={pathname.startsWith("/observatory/eval-tasks")}
              >
                Remote Jobs
              </MenuLink>
              <MenuLink
                href={smartPlugsRoute()}
                isActive={pathname.startsWith("/observatory/infra/smart-plugs")}
              >
                Smart Plugs
              </MenuLink>
            </>
          )}
        </div>
        {isSoftmaxTeamMember && (
          <div className="border-border-strong flex border-t">
            <MenuLink
              href={bardoRoute()}
              isActive={pathname.startsWith("/observatory/bardo")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Bardo
            </MenuLink>
            <MenuLink
              href={policyDashboardRoute()}
              isActive={pathname.startsWith("/observatory/policy-dashboard")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Policy Dashboard
            </MenuLink>
            <MenuLink
              href={diagnoseRoute()}
              isActive={pathname.startsWith("/observatory/diagnose")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Diagnose
            </MenuLink>
            <MenuLink
              href={pantheonRoute()}
              isActive={pathname.startsWith("/observatory/pantheon")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Pantheon
            </MenuLink>
            <MenuLink
              href={trainBoardRoute()}
              isActive={pathname.startsWith("/observatory/train-board")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Train Board
            </MenuLink>
            <MenuLink
              href={chatpropRoute()}
              isActive={pathname.startsWith("/observatory/chatprop")}
              className="tracking-wide italic"
              activeClassName="border-violet-500 text-violet-500"
              inactiveClassName="border-transparent text-violet-400 hover:text-violet-600"
              style={{
                fontFamily: "'Comic Sans MS', 'Marker Felt', cursive",
              }}
            >
              Chatprop
            </MenuLink>
          </div>
        )}
      </div>
      <div
        className={clsx(
          "flex items-center gap-3",
          isSoftmaxTeamMember && "pt-3",
        )}
      >
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
