import clsx from "clsx";
import { FC } from "react";

type AdminUserRoleFlags = {
  isSoftmaxTeamMember: boolean | null | undefined;
  isSoftmaxAdmin: boolean | null | undefined;
};

export function getAdminUserRoleRank({
  isSoftmaxTeamMember,
  isSoftmaxAdmin,
}: AdminUserRoleFlags): number {
  return (isSoftmaxAdmin ? 2 : 0) + (isSoftmaxTeamMember ? 1 : 0);
}

function getAdminUserRoles({
  isSoftmaxTeamMember,
  isSoftmaxAdmin,
}: AdminUserRoleFlags): string[] {
  const roles: string[] = [];
  if (isSoftmaxTeamMember) {
    roles.push("Team");
  }
  if (isSoftmaxAdmin) {
    roles.push("Admin");
  }
  return roles;
}

export const AdminUserRoles: FC<
  AdminUserRoleFlags & {
    className?: string;
  }
> = ({ isSoftmaxTeamMember, isSoftmaxAdmin, className }) => {
  const roles = getAdminUserRoles({ isSoftmaxTeamMember, isSoftmaxAdmin });

  if (roles.length === 0) {
    return <span className={clsx("text-foreground-muted", className)}>—</span>;
  }

  return (
    <div
      className={clsx("flex flex-wrap items-center gap-x-3 gap-y-1", className)}
    >
      {roles.map((role) => (
        <span key={role} className="whitespace-nowrap">
          ✓ {role}
        </span>
      ))}
    </div>
  );
};
