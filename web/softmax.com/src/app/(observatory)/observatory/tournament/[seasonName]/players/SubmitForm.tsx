"use client";
import { useRouter } from "next/navigation";
import { FC, use, useEffect, useMemo, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { AsyncSelect } from "@observatory/components/AsyncSelect";
import { Button } from "@observatory/components/Button";
import { Select } from "@observatory/components/Select";
import type { PolicyRow, PolicyVersionRow } from "@observatory/lib/api";
import { getDisplayMessage } from "@observatory/lib/error-classification";

type PolicyOption = {
  value: string;
  label: string;
  policy: PolicyRow;
};

type VersionOption = {
  value: string;
  label: string;
  version: PolicyVersionRow;
};

export const SubmitForm: FC<{
  seasonName: string;
  existingPolicyVersionIds: Set<string>;
}> = ({ seasonName, existingPolicyVersionIds }) => {
  const { repo } = use(AppContext);
  const [selectedPolicy, setSelectedPolicy] = useState<PolicyOption | null>(
    null,
  );
  const [versions, setVersions] = useState<VersionOption[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<VersionOption | null>(
    null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [locallySubmittedVersionIds, setLocallySubmittedVersionIds] = useState<
    Set<string>
  >(new Set());

  const seasonVersionMatch = seasonName.match(/^(.*?)(?::v|:)(\d+)$/);
  const seasonVersion = seasonVersionMatch
    ? Number(seasonVersionMatch[2])
    : null;
  const isVersionedSeason =
    seasonVersion !== null && Number.isFinite(seasonVersion);

  const router = useRouter();
  const submittedVersionIds = useMemo(() => {
    const merged = new Set(existingPolicyVersionIds);
    for (const id of locallySubmittedVersionIds) {
      merged.add(id);
    }
    return merged;
  }, [existingPolicyVersionIds, locallySubmittedVersionIds]);

  const loadPolicies = async (inputValue: string): Promise<PolicyOption[]> => {
    if (!inputValue) return [];
    const res = await repo.getPolicies({ name_fuzzy: inputValue, limit: 10 });
    return res.entries.map((p) => ({
      value: p.id,
      label: p.name,
      policy: p,
    }));
  };

  useEffect(() => {
    if (!selectedPolicy) {
      setVersions([]);
      setSelectedVersion(null);
      return;
    }
    let ignore = false;
    repo
      .getVersionsForPolicy(selectedPolicy.policy.id, { limit: 50 })
      .then((res) => {
        if (!ignore) {
          const versionOptions = res.entries.map((v) => ({
            value: v.id,
            label: `v${v.version}`,
            version: v,
          }));
          setVersions(versionOptions);
          if (versionOptions.length > 0) {
            setSelectedVersion(versionOptions[0]);
          }
        }
      });
    return () => {
      ignore = true;
    };
  }, [repo, selectedPolicy]);

  useEffect(() => {
    if (!submitSuccess && !submitError) return;
    const timer = setTimeout(() => {
      setSubmitSuccess(null);
      setSubmitError(null);
    }, 10000);
    return () => clearTimeout(timer);
  }, [submitSuccess, submitError]);

  const handleSubmit = async () => {
    if (isVersionedSeason) {
      setSubmitError("Submissions are only allowed on the current season.");
      return;
    }
    if (!selectedVersion) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const submittedVersionId = selectedVersion.version.id;
      const result = await repo.submitToSeason(seasonName, submittedVersionId);
      setSubmitSuccess(`Submitted to pools: ${result.pools.join(", ")}`);
      const nextSubmitted = new Set(submittedVersionIds);
      nextSubmitted.add(submittedVersionId);
      const nextVersion = versions.find(
        (option) => !nextSubmitted.has(option.version.id),
      );
      setLocallySubmittedVersionIds((prev) => {
        const next = new Set(prev);
        next.add(submittedVersionId);
        return next;
      });
      if (nextVersion) {
        setSelectedVersion(nextVersion);
      }
      router.refresh();
    } catch (err: unknown) {
      setSubmitError(
        err instanceof Error ? getDisplayMessage(err) : "Unknown error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const isAlreadySubmitted =
    selectedVersion && submittedVersionIds.has(selectedVersion.version.id);

  return (
    <div>
      <div className="text-foreground-muted mb-2 text-xs">
        Submit new player
      </div>
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <AsyncSelect<PolicyOption>
            instanceId="policy-select"
            value={selectedPolicy}
            onChange={setSelectedPolicy}
            loadOptions={loadPolicies}
            placeholder="Search policies..."
            isClearable
            cacheOptions
            defaultOptions={false}
            noOptionsMessage={({ inputValue }) =>
              inputValue ? "No policies found" : "Type to search..."
            }
          />
        </div>

        {selectedPolicy && versions.length > 0 && (
          <div className="w-28">
            <Select<VersionOption>
              instanceId="version-select"
              value={selectedVersion}
              onChange={setSelectedVersion}
              options={versions}
              isSearchable={false}
            />
          </div>
        )}

        <Button
          onClick={handleSubmit}
          theme="primary"
          disabled={
            !selectedVersion ||
            submitting ||
            !!isAlreadySubmitted ||
            isVersionedSeason
          }
        >
          {submitting ? "..." : "Submit"}
        </Button>
      </div>

      {isVersionedSeason && (
        <div className="mt-1 text-xs text-amber-600">
          Submissions are only allowed on the current season.
        </div>
      )}
      {isAlreadySubmitted && (
        <div className="mt-1 text-xs text-amber-600">Already in season</div>
      )}
      {submitError && (
        <div className="mt-1 text-xs text-red-600">{submitError}</div>
      )}
      {submitSuccess && (
        <div className="mt-1 text-xs text-green-600">{submitSuccess}</div>
      )}
    </div>
  );
};
