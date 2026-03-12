"use client";
import { FC, useDeferredValue, useState } from "react";

import { Input } from "@observatory/components/Input";
import { StyledLink } from "@observatory/components/StyledLink";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import type { AdminUserReportRow } from "@observatory/lib/repo";
import { adminUserRoute } from "@observatory/lib/routes";
import { formatDate, formatRelativeTime } from "@observatory/utils/datetime";

import { AdminUserRoles, getAdminUserRoleRank } from "./AdminUserRoles";

type SortKey =
  | "name"
  | "email"
  | "roles"
  | "created_at"
  | "first_policy_upload_at"
  | "last_policy_upload_at"
  | "first_tournament_submission_at"
  | "last_tournament_submission_at";

const SORTABLE_COLUMNS: Array<{ key: SortKey; label: string }> = [
  { key: "name", label: "Name" },
  { key: "email", label: "Email" },
  { key: "roles", label: "Roles" },
  { key: "created_at", label: "Signup Date" },
  { key: "first_policy_upload_at", label: "First Upload" },
  { key: "last_policy_upload_at", label: "Last Upload" },
  {
    key: "first_tournament_submission_at",
    label: "First Tournament Submission",
  },
  {
    key: "last_tournament_submission_at",
    label: "Last Tournament Submission",
  },
];

function displayName(user: AdminUserReportRow): string {
  return user.name?.trim() || user.email?.trim() || user.id;
}

function compareNullableString(
  a: string | null,
  b: string | null,
  direction: "asc" | "desc",
): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  const comparison = a.localeCompare(b);
  return direction === "asc" ? comparison : -comparison;
}

function compareNumber(a: number, b: number): number {
  if (a === b) {
    return 0;
  }
  return a < b ? -1 : 1;
}

function compareUsers(
  a: AdminUserReportRow,
  b: AdminUserReportRow,
  sortKey: SortKey,
  sortDirection: "asc" | "desc",
): number {
  const comparison =
    sortKey === "name"
      ? compareNullableString(
          displayName(a).toLowerCase(),
          displayName(b).toLowerCase(),
          sortDirection,
        )
      : sortKey === "email"
        ? compareNullableString(
            a.email?.toLowerCase() ?? null,
            b.email?.toLowerCase() ?? null,
            sortDirection,
          )
        : sortKey === "roles"
          ? compareNumber(
              getAdminUserRoleRank({
                isSoftmaxTeamMember: a.is_softmax_team_member,
                isSoftmaxAdmin: a.is_softmax_admin,
              }),
              getAdminUserRoleRank({
                isSoftmaxTeamMember: b.is_softmax_team_member,
                isSoftmaxAdmin: b.is_softmax_admin,
              }),
            ) * (sortDirection === "asc" ? 1 : -1)
          : compareNullableString(a[sortKey], b[sortKey], sortDirection);

  if (comparison !== 0) {
    return comparison;
  }

  return displayName(a)
    .toLowerCase()
    .localeCompare(displayName(b).toLowerCase());
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "—";
  }
  return formatRelativeTime(value);
}

const SortableHeader: FC<{
  label: string;
  column: SortKey;
  sortKey: SortKey;
  sortDirection: "asc" | "desc";
  onSort: (column: SortKey) => void;
}> = ({ label, column, sortKey, sortDirection, onSort }) => {
  const isActive = sortKey === column;
  const indicator = isActive ? (sortDirection === "asc" ? "^" : "v") : "";

  return (
    <TH>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="text-foreground-muted hover:text-foreground font-inherit inline-flex w-full cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-left text-inherit shadow-none transition-colors outline-none"
      >
        <span>{label}</span>
        <span className="w-2 text-[10px]">{indicator}</span>
      </button>
    </TH>
  );
};

export const AdminUsersTable: FC<{
  users: AdminUserReportRow[];
}> = ({ users }) => {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const deferredSearch = useDeferredValue(search);
  const normalizedSearch = deferredSearch.trim().toLowerCase();

  const filteredUsers = users.filter((user) => {
    if (!normalizedSearch) {
      return true;
    }
    return [user.name, user.email].some((value) =>
      value?.toLowerCase().includes(normalizedSearch),
    );
  });
  const sortedUsers = [...filteredUsers].sort((a, b) =>
    compareUsers(a, b, sortKey, sortDirection),
  );

  const handleSort = (column: SortKey) => {
    if (column === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(column);
    setSortDirection("asc");
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="w-full max-w-md">
          <label className="mb-2 block text-xs font-semibold tracking-wide uppercase">
            Search
          </label>
          <Input
            value={search}
            onChange={setSearch}
            placeholder="Search by name or email..."
          />
        </div>
        <p className="text-foreground-muted text-sm">
          {filteredUsers.length} of {users.length} users
        </p>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            {SORTABLE_COLUMNS.map((column) => (
              <SortableHeader
                key={column.key}
                label={column.label}
                column={column.key}
                sortKey={sortKey}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
            ))}
          </TableHeader>
          <TableBody>
            {sortedUsers.map((user) => (
              <TR key={user.id}>
                <TD className="font-medium">
                  <StyledLink href={adminUserRoute(user.id)} theme="muted">
                    {displayName(user)}
                  </StyledLink>
                </TD>
                <TD>{user.email || "—"}</TD>
                <TD>
                  <AdminUserRoles
                    isSoftmaxTeamMember={user.is_softmax_team_member}
                    isSoftmaxAdmin={user.is_softmax_admin}
                    className="text-sm"
                  />
                </TD>
                <TD title={formatDate(user.created_at)}>
                  {formatTimestamp(user.created_at)}
                </TD>
                <TD title={formatDate(user.first_policy_upload_at)}>
                  {formatTimestamp(user.first_policy_upload_at)}
                </TD>
                <TD title={formatDate(user.last_policy_upload_at)}>
                  {formatTimestamp(user.last_policy_upload_at)}
                </TD>
                <TD title={formatDate(user.first_tournament_submission_at)}>
                  {formatTimestamp(user.first_tournament_submission_at)}
                </TD>
                <TD title={formatDate(user.last_tournament_submission_at)}>
                  {formatTimestamp(user.last_tournament_submission_at)}
                </TD>
              </TR>
            ))}
          </TableBody>
        </Table>

        {sortedUsers.length === 0 && (
          <div className="text-foreground-muted p-5 text-center">
            {normalizedSearch
              ? "No users matched that search."
              : "No signed-up users found."}
          </div>
        )}
      </div>
    </div>
  );
};
