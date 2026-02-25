"use client";
import { useRouter } from "next/navigation";
import { FC, useCallback } from "react";

import { Button } from "./Button";
import { useResetError } from "./ResetErrorContext";

export const RefreshButton: FC = () => {
  const router = useRouter();
  const resetError = useResetError();
  const refresh = useCallback(() => {
    if (resetError) {
      resetError();
    } else {
      router.refresh();
    }
  }, [resetError, router]);

  return <Button onClick={refresh}>Refresh</Button>;
};
