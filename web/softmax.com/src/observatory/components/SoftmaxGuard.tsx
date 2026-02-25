"use client";
import { FC, PropsWithChildren, use } from "react";

import { AppContext } from "@observatory-app/AppContext";

export const AccessDenied: FC = () => {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md text-center">
        <h1 className="text-foreground mb-3 text-2xl font-semibold">
          Access Restricted
        </h1>
        <p className="text-foreground-muted">
          This page is only available to Softmax team members.
        </p>
      </div>
    </div>
  );
};

export const SoftmaxGuard: FC<PropsWithChildren> = ({ children }) => {
  const { isSoftmaxTeamMember } = use(AppContext);

  if (!isSoftmaxTeamMember) {
    return <AccessDenied />;
  }

  return children;
};
