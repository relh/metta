"use client";

import { useEffect, useState } from "react";

const TOKEN_REFRESH_CHECK_MS = 60_000;
const TOKEN_REFRESH_LEAD_MS = 2 * 60_000;

type SessionTokenPayload = {
  token?: unknown;
  expiresAt?: unknown;
};

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

type SurfaceEmbedProps = {
  src: string;
  serviceName: string;
  iframeTitle?: string;
};

export function SurfaceEmbed({
  src,
  serviceName,
  iframeTitle,
}: SurfaceEmbedProps) {
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [themedSrc, setThemedSrc] = useState<string | null>(null);

  useEffect(() => {
    let observer: MutationObserver | null = null;
    let refreshInterval: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;
    let authToken: string | null = null;
    let authTokenExpiresAtMs = 0;

    const resolvedServiceName =
      serviceName.trim().length > 0 ? serviceName.trim() : "Service";
    const serviceNameLower = resolvedServiceName.toLowerCase();

    function resolveThemedSrc(authToken: string | null): string {
      try {
        const url = new URL(src, window.location.origin);
        const isDark = document.documentElement.classList.contains("dark");
        url.hash = authToken ? encodeURIComponent(authToken) : "";
        url.searchParams.set("theme", isDark ? "dark" : "light");
        return url.toString();
      } catch {
        return src;
      }
    }

    const fetchSessionToken = async (): Promise<{
      authToken: string;
      expiresAtMs: number;
    }> => {
      const response = await fetch("/api/observatory/session-token", {
        method: "POST",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(
          `Failed to create ${serviceNameLower} token (${response.status})`,
        );
      }

      const payload = (await response.json()) as SessionTokenPayload;
      const nextToken = String(payload.token ?? "").trim();
      if (!nextToken) {
        throw new Error("Session token API returned an empty token");
      }
      const expiresAtRaw = String(payload.expiresAt ?? "").trim();
      const expiresAtMs = Date.parse(expiresAtRaw);
      if (!Number.isFinite(expiresAtMs)) {
        throw new Error("Session token API returned an invalid expiration");
      }
      return { authToken: nextToken, expiresAtMs };
    };

    const updateThemedSrc = () => setThemedSrc(resolveThemedSrc(authToken));

    const refreshSessionTokenIfNeeded = async () => {
      if (
        !authToken ||
        Date.now() + TOKEN_REFRESH_LEAD_MS < authTokenExpiresAtMs
      )
        return;
      const next = await fetchSessionToken();
      authToken = next.authToken;
      authTokenExpiresAtMs = next.expiresAtMs;
      updateThemedSrc();
    };

    const bootstrap = async () => {
      setThemedSrc(null);
      setBootstrapError(null);

      try {
        const next = await fetchSessionToken();
        authToken = next.authToken;
        authTokenExpiresAtMs = next.expiresAtMs;

        updateThemedSrc();

        observer = new MutationObserver(updateThemedSrc);
        observer.observe(document.documentElement, {
          attributes: true,
          attributeFilter: ["class"],
        });
        refreshInterval = setInterval(() => {
          void refreshSessionTokenIfNeeded().catch((error: unknown) => {
            if (!cancelled) {
              setBootstrapError(toErrorMessage(error));
            }
          });
        }, TOKEN_REFRESH_CHECK_MS);
      } catch (error) {
        if (!cancelled) {
          setThemedSrc(resolveThemedSrc(null));
          setBootstrapError(toErrorMessage(error));
        }
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
      observer?.disconnect();
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
    };
  }, [serviceName, src]);

  const resolvedServiceName =
    serviceName.trim().length > 0 ? serviceName.trim() : "Service";
  const serviceNameLower = resolvedServiceName.toLowerCase();

  if (!themedSrc) {
    return (
      <div className="text-foreground-muted flex h-full w-full items-center justify-center">
        Preparing {serviceNameLower} session...
      </div>
    );
  }

  return (
    <>
      {bootstrapError ? (
        <div className="mb-2 rounded bg-red-500/15 px-3 py-2 text-sm text-red-500">
          Unable to prepare {serviceNameLower} authentication: {bootstrapError}
        </div>
      ) : null}
      <iframe
        title={iframeTitle ?? resolvedServiceName}
        src={themedSrc}
        className="bg-background h-full w-full border-0"
        referrerPolicy="no-referrer"
      />
    </>
  );
}
