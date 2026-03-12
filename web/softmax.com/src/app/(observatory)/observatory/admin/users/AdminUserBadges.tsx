import clsx from "clsx";
import { FC } from "react";

export const AdminUserBadges: FC<{
  isSoftmaxTeamMember: boolean | null | undefined;
  isSoftmaxAdmin: boolean | null | undefined;
  className?: string;
}> = ({ isSoftmaxTeamMember, isSoftmaxAdmin, className }) => {
  const roles: string[] = [];
  if (isSoftmaxTeamMember) {
    roles.push("Team");
  }
  if (isSoftmaxAdmin) {
    roles.push("Admin");
  }

  if (roles.length === 0) {
    return null;
  }

  return (
    <div
      className={clsx("flex flex-wrap items-center gap-3 text-sm", className)}
    >
      {roles.map((role) => (
        <span key={role}>✓ {role}</span>
      ))}
    </div>
  );
};
