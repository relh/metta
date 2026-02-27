"use client";

import {
  useRouter,
  useSearchParams,
  useSelectedLayoutSegment,
} from "next/navigation";
import { FC, use, useEffect, useMemo, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import { Select } from "@observatory/components/Select";
import type { SeasonSummary, SeasonVersionInfo } from "@observatory/lib/api";
import { seasonRoute } from "@observatory/lib/routes";
import {
  type SeasonTabMode,
  seasonTabModeForName,
} from "@observatory/lib/tournament/tabMode";
import { parseDatetime } from "@observatory/utils/datetime";

type SeasonOption = { value: string; label: string };
type VersionOption = { value: number; label: string; canonical: boolean };
type CompatVersionOption = { value: string; label: string };

const parseSeasonRef = (seasonRef: string | null) => {
  if (!seasonRef) {
    return { name: null, version: null };
  }
  const vIdx = seasonRef.lastIndexOf(":v");
  if (vIdx > 0) {
    const name = seasonRef.slice(0, vIdx);
    const version = Number(seasonRef.slice(vIdx + 2));
    if (Number.isFinite(version)) {
      return { name, version };
    }
  }
  const colonIdx = seasonRef.lastIndexOf(":");
  if (colonIdx > 0) {
    const name = seasonRef.slice(0, colonIdx);
    const version = Number(seasonRef.slice(colonIdx + 1));
    if (Number.isFinite(version)) {
      return { name, version };
    }
  }
  return { name: seasonRef, version: null };
};

const formatSeasonRef = (
  name: string,
  version: number | null,
  canonical: boolean,
) => (version && !canonical ? `${name}:v${version}` : name);

const formatSeasonVersionLabel = (version: SeasonVersionInfo): string => {
  const createdAt = parseDatetime(version.created_at);
  if (!createdAt) {
    return `Season ${version.version}`;
  }

  const dateLabel = createdAt.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
  const timeLabel = createdAt
    .toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    .toLowerCase();
  const seasonLabel = `${dateLabel}, ${timeLabel} season`;
  return seasonLabel;
};

export const SeasonSelect: FC<{ seasons: SeasonSummary[] }> = ({ seasons }) => {
  const seasonRef = useSelectedLayoutSegment();
  const searchParams = useSearchParams();
  const { repo, isSoftmaxTeamMember } = use(AppContext);
  const [rollError, setRollError] = useState<string | null>(null);
  const [updateCompatError, setUpdateCompatError] = useState<string | null>(
    null,
  );
  const [compatVersionError, setCompatVersionError] = useState<string | null>(
    null,
  );
  const [isRolling, setIsRolling] = useState(false);
  const [isUpdatingCurrentCompat, setIsUpdatingCurrentCompat] = useState(false);
  const [rollCompatVersion, setRollCompatVersion] = useState("");
  const [updateCompatVersion, setUpdateCompatVersion] = useState("");
  const [compatVersionOptions, setCompatVersionOptions] = useState<
    CompatVersionOption[]
  >([]);
  const [isLoadingCompatVersions, setIsLoadingCompatVersions] = useState(false);
  const [rollMigrateActivePlayers, setRollMigrateActivePlayers] =
    useState(false);
  const [activePlayersToMigrateCount, setActivePlayersToMigrateCount] =
    useState<number | null>(null);
  const [
    isLoadingActivePlayersToMigrateCount,
    setIsLoadingActivePlayersToMigrateCount,
  ] = useState(false);
  const [isRollDialogOpen, setIsRollDialogOpen] = useState(false);
  const [isUpdateCompatDialogOpen, setIsUpdateCompatDialogOpen] =
    useState(false);

  const decodedSeasonRef = useMemo(() => {
    if (!seasonRef) {
      return null;
    }
    try {
      return decodeURIComponent(seasonRef);
    } catch {
      return seasonRef;
    }
  }, [seasonRef]);

  const { name: selectedSeasonName, version: selectedSeasonVersion } = useMemo(
    () => parseSeasonRef(decodedSeasonRef),
    [decodedSeasonRef],
  );

  const selectedSeason = useMemo(
    () => seasons.find((season) => season.name === selectedSeasonName) ?? null,
    [seasons, selectedSeasonName],
  );

  const freeplaySeasons = useMemo(
    () =>
      seasons.filter(
        (season) => seasonTabModeForName(season.name) === "freeplay",
      ),
    [seasons],
  );

  const tournamentSeasons = useMemo(
    () =>
      seasons.filter(
        (season) => seasonTabModeForName(season.name) === "tournament",
      ),
    [seasons],
  );

  const selectedMode: SeasonTabMode = useMemo(() => {
    const modeParam = searchParams.get("mode");
    if (modeParam === "freeplay" || modeParam === "tournament") {
      return modeParam;
    }
    if (selectedSeason) {
      return seasonTabModeForName(selectedSeason.name);
    }
    if (freeplaySeasons.length > 0) {
      return "freeplay";
    }
    return "tournament";
  }, [freeplaySeasons.length, searchParams, selectedSeason]);

  const tabSeasons =
    selectedMode === "freeplay" ? freeplaySeasons : tournamentSeasons;

  const seasonOptions: SeasonOption[] = useMemo(() => {
    const options = tabSeasons.map((season) => ({
      value: season.name,
      label: season.public
        ? season.display_name
        : `${season.display_name} (private)`,
    }));
    if (
      selectedSeasonName &&
      !options.some((option) => option.value === selectedSeasonName)
    ) {
      const isPublic = selectedSeason?.public ?? true;
      const displayName = selectedSeason?.display_name ?? selectedSeasonName;
      options.unshift({
        value: selectedSeasonName,
        label: isPublic ? displayName : `${displayName} (private)`,
      });
    }
    return options;
  }, [selectedSeason, selectedSeasonName, tabSeasons]);
  const [versions, setVersions] = useState<SeasonVersionInfo[]>([]);
  const [isLoadingVersions, setIsLoadingVersions] = useState(false);
  const [versionsRefreshNonce, setVersionsRefreshNonce] = useState(0);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    setIsLoadingCompatVersions(true);
    setCompatVersionError(null);
    repo
      .getAvailableCompatVersions()
      .then((versions) => {
        if (cancelled) {
          return;
        }
        const options = versions.map((version) => ({
          value: version,
          label: version,
        }));
        setCompatVersionOptions(options);
        setRollCompatVersion((current) => {
          if (options.length === 0) {
            return "";
          }
          return options.some((option) => option.value === current)
            ? current
            : options[0].value;
        });
        setUpdateCompatVersion((current) => {
          if (options.length === 0) {
            return "";
          }
          return options.some((option) => option.value === current)
            ? current
            : options[0].value;
        });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setCompatVersionOptions([]);
        setRollCompatVersion("");
        setUpdateCompatVersion("");
        setCompatVersionError(
          error instanceof Error
            ? error.message
            : "Failed to load compat versions",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingCompatVersions(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedSeasonName) {
      setVersions([]);
      return;
    }
    setVersions([]);
    setIsLoadingVersions(true);
    repo
      .getSeasonVersions(selectedSeasonName)
      .then((data) => {
        if (!cancelled) {
          setVersions(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setVersions([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingVersions(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo, selectedSeasonName, versionsRefreshNonce]);

  useEffect(() => {
    if (isSoftmaxTeamMember) {
      return;
    }
    setIsRollDialogOpen(false);
    setIsUpdateCompatDialogOpen(false);
  }, [isSoftmaxTeamMember]);

  useEffect(() => {
    let cancelled = false;
    if (selectedMode !== "freeplay" || !selectedSeasonName) {
      setActivePlayersToMigrateCount(null);
      setIsLoadingActivePlayersToMigrateCount(false);
      return;
    }
    setIsLoadingActivePlayersToMigrateCount(true);
    repo
      .getSeason(selectedSeasonName)
      .then((seasonDetail) => {
        if (!cancelled) {
          setActivePlayersToMigrateCount(seasonDetail.active_entrant_count);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setActivePlayersToMigrateCount(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingActivePlayersToMigrateCount(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repo, selectedMode, selectedSeasonName, versionsRefreshNonce]);

  const versionOptions: VersionOption[] = useMemo(
    () =>
      versions
        .slice()
        .sort((a, b) => b.version - a.version)
        .map((v) => ({
          value: v.version,
          canonical: v.canonical,
          label: formatSeasonVersionLabel(v),
        })),
    [versions],
  );

  const selectedVersion = useMemo(() => {
    if (!selectedSeasonName || versionOptions.length === 0) {
      return null;
    }
    if (selectedSeasonVersion) {
      return (
        versionOptions.find(
          (option) => option.value === selectedSeasonVersion,
        ) ?? null
      );
    }
    return (
      versionOptions.find((option) => option.canonical) ?? versionOptions[0]
    );
  }, [selectedSeasonName, selectedSeasonVersion, versionOptions]);

  const handleSeasonChange = (option: SeasonOption | null) => {
    if (option) {
      router.push(seasonRoute(option.value, { mode: selectedMode }));
    }
  };

  const handleVersionChange = (option: VersionOption | null) => {
    if (!selectedSeasonName) {
      return;
    }
    if (!option) {
      router.push(seasonRoute(selectedSeasonName, { mode: selectedMode }));
      return;
    }
    router.push(
      seasonRoute(
        formatSeasonRef(selectedSeasonName, option.value, option.canonical),
        { mode: selectedMode },
      ),
    );
  };

  const nextVersion = useMemo(() => {
    if (versions.length === 0) {
      return null;
    }
    return Math.max(...versions.map((version) => version.version)) + 1;
  }, [versions]);

  const selectedRollCompatVersion = useMemo(
    () =>
      compatVersionOptions.find(
        (option) => option.value === rollCompatVersion,
      ) ?? null,
    [compatVersionOptions, rollCompatVersion],
  );

  const selectedUpdateCompatVersion = useMemo(
    () =>
      compatVersionOptions.find(
        (option) => option.value === updateCompatVersion,
      ) ?? null,
    [compatVersionOptions, updateCompatVersion],
  );

  const isRollingBusy =
    isRolling || isLoadingVersions || isLoadingCompatVersions;
  const isUpdatingCompatBusy =
    isUpdatingCurrentCompat || isLoadingCompatVersions;
  const currentCompatVersionLabel = selectedSeason?.compat_version ?? "none";

  const migratePlayersLabel = useMemo(() => {
    if (isLoadingActivePlayersToMigrateCount) {
      return "Migrate active players (loading count...)";
    }
    if (activePlayersToMigrateCount === null) {
      return "Migrate active players";
    }
    return `Migrate active players (${activePlayersToMigrateCount})`;
  }, [activePlayersToMigrateCount, isLoadingActivePlayersToMigrateCount]);

  const openRollDialog = () => {
    setRollError(null);
    setRollMigrateActivePlayers(false);
    setIsRollDialogOpen(true);
  };

  const closeRollDialog = () => {
    if (isRolling) {
      return;
    }
    setIsRollDialogOpen(false);
  };

  const openUpdateCompatDialog = () => {
    setUpdateCompatError(null);
    setIsUpdateCompatDialogOpen(true);
  };

  const closeUpdateCompatDialog = () => {
    if (isUpdatingCurrentCompat) {
      return;
    }
    setIsUpdateCompatDialogOpen(false);
  };

  const handleRollSeason = async () => {
    if (
      !isSoftmaxTeamMember ||
      !selectedSeasonName ||
      !selectedSeason?.id ||
      nextVersion === null
    ) {
      return;
    }
    const compatVersion = rollCompatVersion.trim();
    if (!compatVersion) {
      setRollError("Compat version is required");
      return;
    }
    setIsRolling(true);
    setRollError(null);
    try {
      const newSeason = await repo.rollSeason(
        selectedSeason.id,
        compatVersion,
        rollMigrateActivePlayers,
      );
      setRollCompatVersion(compatVersion);
      setRollMigrateActivePlayers(false);
      setIsRollDialogOpen(false);
      setVersionsRefreshNonce((current) => current + 1);
      router.push(
        seasonRoute(newSeason.name, {
          mode: seasonTabModeForName(newSeason.name),
        }),
      );
      router.refresh();
    } catch (error: unknown) {
      setRollError(
        error instanceof Error ? error.message : "Failed to roll season",
      );
    } finally {
      setIsRolling(false);
    }
  };

  const handleUpdateCurrentCompatVersion = async () => {
    if (!isSoftmaxTeamMember || !selectedSeason?.id) {
      return;
    }
    const compatVersion = updateCompatVersion.trim();
    if (!compatVersion) {
      setUpdateCompatError("Compat version is required");
      return;
    }
    setIsUpdatingCurrentCompat(true);
    setUpdateCompatError(null);
    try {
      await repo.updateCurrentSeasonCompatVersion(
        selectedSeason.id,
        compatVersion,
      );
      setUpdateCompatVersion(compatVersion);
      setIsUpdateCompatDialogOpen(false);
      setVersionsRefreshNonce((current) => current + 1);
      router.refresh();
    } catch (error: unknown) {
      setUpdateCompatError(
        error instanceof Error
          ? error.message
          : "Failed to update current season compat version",
      );
    } finally {
      setIsUpdatingCurrentCompat(false);
    }
  };

  return (
    <div className="space-y-3">
      {compatVersionError && (
        <div className="text-sm text-red-500">{compatVersionError}</div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          options={seasonOptions}
          value={
            seasonOptions.find(
              (option) => option.value === selectedSeasonName,
            ) ?? null
          }
          onChange={handleSeasonChange}
          size="lg"
          isSearchable={false}
          placeholder={`Select ${selectedMode === "freeplay" ? "freeplay" : "tournament"} season...`}
          instanceId="season-select"
        />
        <Select
          options={versionOptions}
          value={selectedVersion}
          onChange={handleVersionChange}
          size="lg"
          isSearchable={false}
          placeholder={
            selectedSeasonName ? "Select version..." : "Select season first"
          }
          instanceId="season-version-select"
          isDisabled={!selectedSeasonName || isLoadingVersions}
        />
        {isSoftmaxTeamMember && selectedSeasonName && selectedSeason?.id && (
          <>
            <Button
              onClick={openUpdateCompatDialog}
              size="sm"
              disabled={
                isUpdatingCompatBusy || compatVersionOptions.length === 0
              }
            >
              Update compat version
            </Button>
            <Button
              onClick={openRollDialog}
              size="sm"
              disabled={
                isRollingBusy ||
                nextVersion === null ||
                compatVersionOptions.length === 0
              }
            >
              Make new season
            </Button>
          </>
        )}
      </div>
      {isSoftmaxTeamMember && isRollDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-surface border-border w-full max-w-lg space-y-4 rounded-lg border p-6 shadow-xl">
            <h2 className="text-base font-semibold">
              {nextVersion === null
                ? "Make new season"
                : `Make new season (v${nextVersion})`}
            </h2>
            <div className="space-y-1.5">
              <label className="text-foreground-muted text-xs font-bold tracking-[0.04em] uppercase">
                Compat version
              </label>
              <Select
                options={compatVersionOptions}
                value={selectedRollCompatVersion}
                onChange={(option) => setRollCompatVersion(option?.value ?? "")}
                size="sm"
                isSearchable={false}
                placeholder={
                  isLoadingCompatVersions
                    ? "Loading compat versions..."
                    : "Select compat version..."
                }
                instanceId="season-roll-compat-version-dialog-select"
                isDisabled={isRollingBusy || compatVersionOptions.length === 0}
              />
            </div>
            <label className="text-foreground-muted inline-flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={rollMigrateActivePlayers}
                onChange={(event) =>
                  setRollMigrateActivePlayers(event.target.checked)
                }
                className="h-3.5 w-3.5"
                disabled={isRolling}
              />
              {migratePlayersLabel}
            </label>
            {rollError && <p className="text-xs text-red-600">{rollError}</p>}
            <div className="flex justify-end gap-2">
              <Button
                onClick={closeRollDialog}
                theme="tertiary"
                disabled={isRolling}
              >
                Cancel
              </Button>
              <Button
                onClick={handleRollSeason}
                theme="primary"
                disabled={
                  isRollingBusy ||
                  !rollCompatVersion.trim() ||
                  compatVersionOptions.length === 0 ||
                  nextVersion === null
                }
              >
                {isRolling ? "Creating..." : "Make new season"}
              </Button>
            </div>
          </div>
        </div>
      )}
      {isSoftmaxTeamMember && isUpdateCompatDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-surface border-border w-full max-w-lg space-y-4 rounded-lg border p-6 shadow-xl">
            <h2 className="text-base font-semibold">
              Update current season compat version
            </h2>
            <p className="text-foreground-muted text-sm">
              Current compat version:{" "}
              <span className="font-mono">{currentCompatVersionLabel}</span>
            </p>
            <div className="space-y-1.5">
              <label className="text-foreground-muted text-xs font-bold tracking-[0.04em] uppercase">
                Compat version
              </label>
              <Select
                options={compatVersionOptions}
                value={selectedUpdateCompatVersion}
                onChange={(option) =>
                  setUpdateCompatVersion(option?.value ?? "")
                }
                size="sm"
                isSearchable={false}
                placeholder={
                  isLoadingCompatVersions
                    ? "Loading compat versions..."
                    : "Select compat version..."
                }
                instanceId="season-update-compat-version-dialog-select"
                isDisabled={
                  isUpdatingCompatBusy || compatVersionOptions.length === 0
                }
              />
            </div>
            {updateCompatError && (
              <p className="text-xs text-red-600">{updateCompatError}</p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                onClick={closeUpdateCompatDialog}
                theme="tertiary"
                disabled={isUpdatingCurrentCompat}
              >
                Cancel
              </Button>
              <Button
                onClick={handleUpdateCurrentCompatVersion}
                theme="primary"
                disabled={
                  isUpdatingCompatBusy ||
                  !updateCompatVersion.trim() ||
                  compatVersionOptions.length === 0
                }
              >
                {isUpdatingCurrentCompat ? "Updating..." : "Update compat"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
