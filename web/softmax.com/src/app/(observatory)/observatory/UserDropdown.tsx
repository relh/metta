"use client";
import { signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { FC, use } from "react";

import { AppContext } from "@observatory-app/AppContext";
import {
  Dropdown,
  DropdownMenu,
  DropdownMenuItem,
} from "@observatory/components/Dropdown";
import { useDebugPanelVisible } from "@observatory/lib/debug/useDebugPanelVisible";
import { serviceAccountsRoute } from "@observatory/lib/routes";

export const UserDropdown: FC<{ currentUser: string; devMode: boolean }> = ({
  currentUser,
  devMode,
}) => {
  const router = useRouter();
  const { isVisible: debugPanelVisible, toggle: toggleDebugPanel } =
    useDebugPanelVisible();
  const { isActuallySoftmaxTeamMember, actAsExternal, toggleActAsExternal } =
    use(AppContext);

  return (
    <Dropdown
      render={({ close }) => (
        <DropdownMenu>
          <DropdownMenuItem
            title={
              debugPanelVisible
                ? "Hide API requests panel"
                : "Show API requests panel"
            }
            onClick={() => {
              toggleDebugPanel();
              close();
            }}
          />
          {isActuallySoftmaxTeamMember && (
            <>
              <DropdownMenuItem
                title={
                  actAsExternal ? "Act as Softmax user" : "Act as external user"
                }
                onClick={() => {
                  toggleActAsExternal();
                  close();
                }}
              />
              {!actAsExternal && (
                <DropdownMenuItem
                  title="Service Accounts"
                  onClick={() => {
                    router.push(serviceAccountsRoute());
                  }}
                />
              )}
            </>
          )}
          {devMode ? (
            <div className="text-foreground-subtle max-w-48 px-3 py-2 text-xs">
              Auth is set via DEV_AUTH_TOKEN. Sign out is not available in dev
              mode.
            </div>
          ) : (
            <DropdownMenuItem
              title="Sign out"
              onClick={() => {
                close();
                signOut();
              }}
            />
          )}
        </DropdownMenu>
      )}
    >
      <span className="text-foreground-muted hover:text-foreground cursor-pointer text-sm transition-colors">
        {currentUser}
      </span>
    </Dropdown>
  );
};
