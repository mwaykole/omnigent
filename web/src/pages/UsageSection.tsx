import { useMemo, useState } from "react";
import { ArrowDownIcon, ArrowUpIcon, Loader2Icon } from "lucide-react";
import { useUsageReport } from "@/hooks/useUsageReport";
import type { SessionUsage } from "@/lib/usageApi";
import { shortModelName } from "@/components/CostRoutingControl";
import { cn } from "@/lib/utils";

function fmtCost(usd: number): string {
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function relativeTime(epochSec: number): string {
  const diffMs = Date.now() - epochSec * 1000;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

type SortField = "cost" | "date";
type SortDir = "asc" | "desc";

export function UsageSection() {
  const { data, isLoading, error } = useUsageReport();
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sortedSessions = useMemo(() => {
    if (!data) return [];
    const sessions = [...data.sessions];
    sessions.sort((a, b) => {
      const mul = sortDir === "desc" ? -1 : 1;
      if (sortField === "cost") return mul * (a.costUsd - b.costUsd);
      return mul * (a.updatedAt - b.updatedAt);
    });
    return sessions;
  }, [data, sortField, sortDir]);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  if (isLoading) {
    return (
      <section>
        <h1 className="text-2xl font-semibold">Usage</h1>
        <div className="mt-6 flex items-center gap-2 text-muted-foreground">
          <Loader2Icon className="size-4 animate-spin" />
          <span>Loading usage data…</span>
        </div>
      </section>
    );
  }

  if (error || !data) {
    return (
      <section>
        <h1 className="text-2xl font-semibold">Usage</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Track your spend across all sessions.
        </p>
        <p className="mt-6 text-ui text-muted-foreground">
          Unable to load usage data. The server may not support this endpoint.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Usage</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Track your spend across all sessions.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CostCard label="Today" cost={data.costToday} />
        <CostCard label="Last 7 days" cost={data.costLast7d} />
        <CostCard label="Last 30 days" cost={data.costLast30d} />
        <CostCard label="All time" cost={data.totalCostUsd} highlight />
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-medium">Sessions</h2>
        {sortedSessions.length === 0 ? (
          <p className="mt-3 text-ui text-muted-foreground">No session usage recorded yet.</p>
        ) : (
          <div className="mt-3 overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Session</th>
                  <th className="px-3 py-2 font-medium">Models</th>
                  <th className="px-3 py-2 font-medium">
                    <SortButton
                      label="Last active"
                      active={sortField === "date"}
                      dir={sortField === "date" ? sortDir : undefined}
                      onClick={() => toggleSort("date")}
                    />
                  </th>
                  <th className="px-3 py-2 text-right font-medium">
                    <SortButton
                      label="Cost"
                      active={sortField === "cost"}
                      dir={sortField === "cost" ? sortDir : undefined}
                      onClick={() => toggleSort("cost")}
                      className="justify-end"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedSessions.map((session) => (
                  <SessionRow key={session.id} session={session} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function CostCard({
  label,
  cost,
  highlight,
}: {
  label: string;
  cost: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3",
        highlight ? "border-primary/30 bg-primary/5" : "bg-muted/20",
      )}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={cn("mt-1 text-xl font-semibold tabular-nums", highlight && "text-primary")}>
        {fmtCost(cost)}
      </div>
    </div>
  );
}

function SortButton({
  label,
  active,
  dir,
  onClick,
  className,
}: {
  label: string;
  active: boolean;
  dir?: SortDir;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 transition-colors hover:text-foreground",
        active && "text-foreground",
        className,
      )}
    >
      {label}
      {active &&
        (dir === "asc" ? (
          <ArrowUpIcon className="size-3" />
        ) : (
          <ArrowDownIcon className="size-3" />
        ))}
    </button>
  );
}

function SessionRow({ session }: { session: SessionUsage }) {
  const models = Object.entries(session.models);
  return (
    <tr className="border-b last:border-b-0 hover:bg-muted/30">
      <td className="max-w-[16rem] truncate px-3 py-2 font-medium">
        {session.title ?? (
          <span className="text-muted-foreground italic">Untitled</span>
        )}
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {models.length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            models.map(([model, cost]) => (
              <span
                key={model}
                title={`${model}: ${fmtCost(cost)}`}
                className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
              >
                {shortModelName(model)}
              </span>
            ))
          )}
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
        {relativeTime(session.updatedAt)}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums font-medium">
        {fmtCost(session.costUsd)}
      </td>
    </tr>
  );
}
