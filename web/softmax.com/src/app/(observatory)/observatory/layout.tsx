import "@observatory/style.css";

import { Metadata } from "next";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { PropsWithChildren } from "react";
import { ToastContainer } from "react-toastify";

import { AccountSignInPrompt } from "@/components/account/AccountSignInPrompt";
import { auth } from "@/lib/auth";
import { loadUserById } from "@/lib/user";
import { AppProvider } from "@observatory-app/AppContext";
import { TopMenu } from "@observatory-app/TopMenu";
import { AutoRefreshProvider } from "@observatory/components/AutoRefreshProvider";
import { ResetErrorProvider } from "@observatory/components/ResetErrorContext";
import { ThemeProvider } from "@observatory/components/ThemeProvider";
import { config } from "@observatory/config";
import { RequestDebugPanel } from "@observatory/lib/debug/RequestDebugPanel";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";

export default async function RootLayout({ children }: PropsWithChildren) {
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) {
    return (
      <html lang="en">
        <body className="overflow-y-scroll">
          <ThemeProvider>
            <div className="bg-background mx-auto flex min-h-screen flex-col items-center justify-center">
              <h1 className="text-foreground mb-0 text-2xl font-semibold">
                Softmax Observatory
              </h1>
              <div className="max-w-lg p-6">
                <AccountSignInPrompt />
              </div>
            </div>
          </ThemeProvider>
        </body>
      </html>
    );
  }

  const user = await loadUserById(userId);
  if (!user?.email) {
    throw new Error(`User not found: ${userId}`);
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body className="overflow-y-scroll">
        <ThemeProvider>
          <NuqsAdapter>
            <AppProvider
              apiBaseUrl="/api/observatory"
              isSoftmaxTeamMember={user?.isSoftmaxTeamMember}
            >
              <AutoRefreshProvider>
                <ResetErrorProvider>
                  <div className="flex min-h-screen flex-col font-sans">
                    <TopMenu
                      currentUser={user.email}
                      devMode={!!config.authToken}
                    />
                    <div className="bg-background flex-1">{children}</div>
                  </div>
                  <ServerDebugDrain />
                  <RequestDebugPanel />
                  <ToastContainer stacked />
                </ResetErrorProvider>
              </AutoRefreshProvider>
            </AppProvider>
          </NuqsAdapter>
        </ThemeProvider>
      </body>
    </html>
  );
}

export const metadata: Metadata = {
  title: "Observatory",
};

// Opt out of all static rendering
export const dynamic = "force-dynamic";
