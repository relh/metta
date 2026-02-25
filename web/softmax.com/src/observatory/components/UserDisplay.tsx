"use client";
import { FC } from "react";

import { UserRow } from "@observatory/lib/repo";

import { Tooltip } from "./Tooltip";

export const UserDisplay: FC<{ user?: UserRow | null; userId: string }> = ({
  user,
  userId,
}) => {
  const displayName = user?.name ?? userId;

  return (
    <Tooltip
      placement="bottom-start"
      render={() => (
        <div className="flex min-w-[160px] flex-col gap-1 text-xs">
          <div className="text-foreground-muted font-mono">{userId}</div>
          {user?.name && (
            <div className="text-foreground font-medium">{user.name}</div>
          )}
          {user?.email && (
            <div className="text-foreground-muted">{user.email}</div>
          )}
          {user?.is_softmax_team_member && (
            <span className="inline-flex items-center self-start rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300">
              Softmax Team
            </span>
          )}
        </div>
      )}
    >
      <span className="text-foreground-subtle cursor-default">
        {displayName}
      </span>
    </Tooltip>
  );
};
