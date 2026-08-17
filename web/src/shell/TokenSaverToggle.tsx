import { ZapIcon, ZapOffIcon } from "lucide-react";
import { useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSession } from "@/hooks/useSession";
import { updateSession } from "@/lib/sessionsApi";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

const TOKEN_SAVER_LABEL_KEY = "omnigent.token_saver";
const TOKEN_SAVER_STATS_KEY = "omnigent.token_saver_stats";

interface AlgoDef {
  key: string;
  label: string;
  description: string;
}

const ALGOS: readonly AlgoDef[] = [
  {
    key: "json",
    label: "JSON Columnar",
    description: "Schema compilation for arrays-of-objects (TSCG)",
  },
  {
    key: "log",
    label: "Log Grouping",
    description: "Pattern-signature dedup for shell/log output (DeLog)",
  },
  {
    key: "delta",
    label: "Delta Encoding",
    description: "Emit diffs when same tool produces similar output",
  },
  {
    key: "listing",
    label: "Listing Compress",
    description: "Strip metadata from directory listings",
  },
  {
    key: "general",
    label: "General Cleanup",
    description: "Collapse blanks, strip trailing whitespace, head+tail cap",
  },
] as const;

const ALL_KEYS = new Set(ALGOS.map((a) => a.key));

interface TokenSaverStats {
  chars_saved: number;
  original_chars: number;
  compressions: number;
  tokens_saved: number;
  cost_saved_usd: number;
}

function parseLabelValue(value: string | undefined | null): Set<string> {
  if (!value || value === "off") return new Set();
  if (value === "all" || value === "1") return new Set(ALL_KEYS);
  return new Set(value.split(",").filter((k) => ALL_KEYS.has(k.trim())));
}

function toLabelValue(selected: Set<string>): string {
  if (selected.size === 0) return "off";
  if (selected.size === ALL_KEYS.size) return "all";
  return [...selected].join(",");
}

function parseStats(raw: string | undefined | null): TokenSaverStats | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as TokenSaverStats;
    if (typeof parsed.chars_saved !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

export function TokenSaverToggle({ conversationId }: { conversationId: string }) {
  const { session } = useSession(conversationId);
  const queryClient = useQueryClient();

  const selected = useMemo(
    () => parseLabelValue(session?.labels?.[TOKEN_SAVER_LABEL_KEY]),
    [session?.labels],
  );
  const enabled = selected.size > 0;
  const activeCount = selected.size;

  const stats = useMemo(
    () => parseStats(session?.labels?.[TOKEN_SAVER_STATS_KEY]),
    [session?.labels],
  );

  const refreshSession = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["session", conversationId] });
  }, [conversationId, queryClient]);

  const patchLabel = useCallback(
    async (next: Set<string>) => {
      try {
        const updated = await updateSession(conversationId, {
          labels: { [TOKEN_SAVER_LABEL_KEY]: toLabelValue(next) },
        });
        queryClient.setQueryData(["session", conversationId], updated);
      } catch {
        // Silent — the button state refreshes on next snapshot.
      }
    },
    [conversationId, queryClient],
  );

  const toggleAlgo = useCallback(
    (key: string) => {
      const next = new Set(selected);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      void patchLabel(next);
    },
    [selected, patchLabel],
  );

  const toggleAll = useCallback(() => {
    void patchLabel(enabled ? new Set() : new Set(ALL_KEYS));
  }, [enabled, patchLabel]);

  if (!session) return null;

  return (
    <DropdownMenu onOpenChange={(open) => open && refreshSession()}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Token saver settings"
              data-testid="token-saver-toggle"
              className={cn(
                "hidden gap-1 px-2 text-ui font-normal md:inline-flex",
                enabled
                  ? "text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {enabled ? <ZapIcon className="size-3.5" /> : <ZapOffIcon className="size-3.5" />}
              <span className="text-xs">
                Token Saver{enabled && activeCount < ALL_KEYS.size ? ` (${activeCount})` : ""}
              </span>
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {enabled
            ? `Token saver ON — ${activeCount}/${ALL_KEYS.size} algorithms active`
            : "Token saver OFF — click to configure"}
        </TooltipContent>
      </Tooltip>

      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Compression Algorithms</span>
          <button
            type="button"
            onClick={toggleAll}
            className="text-xs font-normal text-muted-foreground hover:text-foreground"
          >
            {enabled ? "Disable all" : "Enable all"}
          </button>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {ALGOS.map((algo) => (
          <DropdownMenuCheckboxItem
            key={algo.key}
            checked={selected.has(algo.key)}
            onCheckedChange={() => toggleAlgo(algo.key)}
            onSelect={(e) => e.preventDefault()}
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-ui font-medium">{algo.label}</span>
              <span className="text-xs text-muted-foreground">{algo.description}</span>
            </div>
          </DropdownMenuCheckboxItem>
        ))}

        {stats && stats.compressions > 0 && (
          <>
            <DropdownMenuSeparator />
            <div className="px-2 py-2">
              <div className="text-xs font-medium text-muted-foreground mb-1.5">
                Session Savings
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    {formatTokens(stats.tokens_saved)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">tokens saved</div>
                </div>
                <div>
                  <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    {formatCost(stats.cost_saved_usd)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">cost saved</div>
                </div>
                <div>
                  <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    {stats.compressions}
                  </div>
                  <div className="text-[10px] text-muted-foreground">compressions</div>
                </div>
              </div>
              {stats.original_chars > 0 && (
                <div className="mt-1.5 text-[10px] text-muted-foreground text-center">
                  {Math.round((stats.chars_saved / stats.original_chars) * 100)}% reduction
                  ({(stats.chars_saved / 1000).toFixed(1)}K chars saved)
                </div>
              )}
            </div>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
