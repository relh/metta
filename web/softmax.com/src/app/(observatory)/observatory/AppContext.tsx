"use client";
import {
  createContext,
  FC,
  PropsWithChildren,
  useCallback,
  useMemo,
  useState,
} from "react";

import { addEntries } from "@observatory/lib/debug/request-log";
import { Repo } from "@observatory/lib/repo";

export const AppContext = createContext<{
  repo: Repo;
  apiBaseUrl: string;
  isSoftmaxTeamMember: boolean;
  isActuallySoftmaxTeamMember: boolean;
  actAsExternal: boolean;
  toggleActAsExternal: () => void;
}>({
  repo: new Repo(),
  apiBaseUrl: "http://localhost:8000",
  isSoftmaxTeamMember: false,
  isActuallySoftmaxTeamMember: false,
  actAsExternal: false,
  toggleActAsExternal: () => {},
});

export const AppProvider: FC<
  PropsWithChildren<{
    apiBaseUrl: string;
    isSoftmaxTeamMember: boolean;
  }>
> = ({
  children,
  apiBaseUrl,
  isSoftmaxTeamMember: isActuallySoftmaxTeamMember,
}) => {
  const [actAsExternal, setActAsExternal] = useState(false);
  const onRequest = useCallback(
    (entry: import("@observatory/lib/repo").RequestLogEntry) =>
      addEntries([entry]),
    [],
  );
  const repo = useMemo(
    () => new Repo(apiBaseUrl, null, onRequest, actAsExternal),
    [apiBaseUrl, onRequest, actAsExternal],
  );

  const toggleActAsExternal = useCallback(
    () => setActAsExternal((v) => !v),
    [],
  );
  const isSoftmaxTeamMember = isActuallySoftmaxTeamMember && !actAsExternal;

  return (
    <AppContext
      value={{
        repo,
        apiBaseUrl,
        isSoftmaxTeamMember,
        isActuallySoftmaxTeamMember,
        actAsExternal,
        toggleActAsExternal,
      }}
    >
      {children}
    </AppContext>
  );
};
