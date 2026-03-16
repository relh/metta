"use client";
import { use, useEffect, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { Spinner } from "@observatory/components/Spinner";
import { getDisplayMessage } from "@observatory/lib/error-classification";
import { SmartPlugStatus } from "@observatory/lib/repo";

export default function SmartPlugsPage() {
  const { repo } = use(AppContext);
  const [plugs, setPlugs] = useState<SmartPlugStatus[]>([]);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await repo.getSmartPlugStatus();
      setPlugs(response.items);
      setRefreshedAt(response.refreshed_at);
    } catch (err: any) {
      setError(
        err instanceof Error
          ? getDisplayMessage(err)
          : "Failed to load smart plug status",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleToggle = async (plug: SmartPlugStatus, on: boolean) => {
    setBusyKey(plug.key);
    setError(null);
    try {
      await repo.setSmartPlugPower({ key: plug.key, on });
      await refresh();
    } catch (err: any) {
      setError(
        err instanceof Error
          ? getDisplayMessage(err)
          : "Failed to update smart plug power",
      );
    } finally {
      setBusyKey(null);
    }
  };

  if (loading && plugs.length === 0) {
    return (
      <SoftmaxGuard>
        <div className="text-foreground-muted p-6">
          <h2 className="mb-2 text-xl font-semibold">Smart Plugs</h2>
          <Spinner size="lg" />
        </div>
      </SoftmaxGuard>
    );
  }

  if (error) {
    return (
      <SoftmaxGuard>
        <div className="p-6">
          <h2 className="mb-2 text-xl font-semibold">Smart Plugs</h2>
          <div className="mb-4 text-red-600">{error}</div>
          <Button onClick={refresh} theme="primary">
            Retry
          </Button>
        </div>
      </SoftmaxGuard>
    );
  }

  return (
    <SoftmaxGuard>
      <div className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">Smart Plugs</h2>
            <p className="text-foreground-muted text-sm">
              Actions require Softmax access and are logged.
            </p>
            {refreshedAt && (
              <p className="text-foreground-muted text-xs">
                Last refresh: {refreshedAt}
              </p>
            )}
          </div>
          <button
            className="bg-foreground text-surface rounded px-3 py-2"
            onClick={refresh}
            disabled={loading}
          >
            Refresh
          </button>
        </div>

        <div className="bg-surface border-border overflow-hidden rounded-lg border">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-alt text-foreground-muted text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Location</th>
                <th className="px-4 py-3 text-left">Alias</th>
                <th className="px-4 py-3 text-left">Online</th>
                <th className="px-4 py-3 text-left">Power</th>
                <th className="px-4 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {plugs.map((plug) => {
                const onlineLabel =
                  plug.online == null
                    ? "Unknown"
                    : plug.online
                      ? "Online"
                      : "Offline";
                const onlineDot =
                  plug.online == null
                    ? "bg-foreground-muted"
                    : plug.online
                      ? "bg-green-500"
                      : "bg-red-500";
                const powerLabel =
                  plug.is_on == null ? "Unknown" : plug.is_on ? "On" : "Off";
                const apowerLabel =
                  plug.apower == null ? "—" : `${plug.apower.toFixed(1)} W`;
                const isBusy = busyKey === plug.key;

                return (
                  <tr key={plug.key} className="border-border-subtle border-t">
                    <td className="px-4 py-3">
                      <div className="text-foreground font-medium">
                        {plug.label}
                      </div>
                    </td>
                    <td className="text-foreground-subtle px-4 py-3">
                      {plug.alias || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${onlineDot}`} />
                        {onlineLabel}
                      </span>
                    </td>
                    <td className="text-foreground-subtle px-4 py-3">
                      {powerLabel}
                      <div className="text-foreground-muted text-xs">
                        {apowerLabel}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          className="border-border-strong text-foreground-subtle rounded border px-3 py-1 disabled:opacity-50"
                          onClick={() => handleToggle(plug, true)}
                          disabled={isBusy || loading}
                        >
                          Turn On
                        </button>
                        <button
                          className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
                          onClick={() => handleToggle(plug, false)}
                          disabled={isBusy || loading}
                        >
                          Turn Off
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </SoftmaxGuard>
  );
}
