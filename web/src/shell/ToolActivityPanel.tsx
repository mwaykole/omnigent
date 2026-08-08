import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDownIcon,
  ChevronUpIcon,
  CheckCircle2Icon,
  Loader2Icon,
  TerminalIcon,
  XCircleIcon,
  ChevronRightIcon,
} from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { iconForTool } from "@/lib/toolIcon";
import { formatToolTitle } from "@/lib/toolTitle";
import { formatToolDuration } from "@/components/blocks/ToolCard";
import { useToolActivity, type ToolActivityEntry } from "@/hooks/useToolActivity";

const MIN_HEIGHT = 120;
const DEFAULT_HEIGHT = 240;
const MAX_HEIGHT_VH = 50;
const AUTO_HIDE_DELAY_MS = 5_000;

export function ToolActivityPanel() {
  const { entries, runningCount, completedCount, isActive } = useToolActivity();
  const [expanded, setExpanded] = useState(false);
  const [userExpanded, setUserExpanded] = useState(false);
  const [visible, setVisible] = useState(false);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);

  useEffect(() => {
    if (isActive) {
      setVisible(true);
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    } else if (entries.length > 0 && !userExpanded) {
      hideTimerRef.current = setTimeout(() => setVisible(false), AUTO_HIDE_DELAY_MS);
    }
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, [isActive, entries.length, userExpanded]);

  useEffect(() => {
    if (expanded && listEndRef.current) {
      listEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [entries.length, expanded]);

  const toggleExpand = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      setUserExpanded(next);
      if (next) setVisible(true);
      return next;
    });
  }, []);

  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = { startY: e.clientY, startH: height };
      const onMove = (ev: MouseEvent) => {
        if (!dragRef.current) return;
        const maxH = window.innerHeight * (MAX_HEIGHT_VH / 100);
        const delta = dragRef.current.startY - ev.clientY;
        setHeight(Math.max(MIN_HEIGHT, Math.min(maxH, dragRef.current.startH + delta)));
      };
      const onUp = () => {
        dragRef.current = null;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [height],
  );

  if (!visible || entries.length === 0) return null;

  const firstRunning = entries.find((e) => e.running);
  const firstRunningTitle = firstRunning
    ? formatToolTitle(firstRunning.execution.name, firstRunning.execution.arguments, firstRunning.execution.argsSummary)
    : null;

  return (
    <div className="shrink-0 border-t border-border bg-background">
      {expanded && (
        <div
          className="h-1 cursor-row-resize hover:bg-accent transition-colors"
          onMouseDown={handleDragStart}
        />
      )}

      <button
        type="button"
        onClick={toggleExpand}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-accent/50"
      >
        {expanded ? (
          <ChevronDownIcon className="size-3.5 shrink-0" />
        ) : (
          <ChevronUpIcon className="size-3.5 shrink-0" />
        )}
        <TerminalIcon className="size-3.5 shrink-0" />
        <span className="font-medium">Terminal</span>

        {runningCount > 0 && firstRunningTitle && (
          <span className="flex items-center gap-1.5 min-w-0 truncate">
            <Loader2Icon className="size-3 shrink-0 animate-spin text-info" />
            <span className="truncate">
              {firstRunningTitle.verb && (
                <span className="font-semibold text-foreground">{firstRunningTitle.verb}</span>
              )}{" "}
              {firstRunningTitle.body}
            </span>
            {runningCount > 1 && (
              <span className="shrink-0 text-muted-foreground">+{runningCount - 1}</span>
            )}
          </span>
        )}

        <span className="ml-auto shrink-0 tabular-nums">
          {completedCount > 0 && (
            <span className="text-muted-foreground">
              {completedCount} completed
            </span>
          )}
        </span>
      </button>

      {expanded && (
        <div
          className="overflow-y-auto border-t border-border/50"
          style={{ height: `${height}px`, maxHeight: `${MAX_HEIGHT_VH}vh` }}
        >
          <div className="flex flex-col divide-y divide-border/30">
            {entries.map((entry) => (
              <ActivityEntry key={entry.execution.callId} entry={entry} />
            ))}
            <div ref={listEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

function ActivityEntry({ entry }: { entry: ToolActivityEntry }) {
  const { execution, output, running, duration } = entry;
  const title = formatToolTitle(execution.name, execution.arguments, execution.argsSummary);
  const Icon = iconForTool(execution.name);
  const hasOutput = output !== null && output.length > 0;

  return (
    <Collapsible className="group/activity-entry" defaultOpen={running}>
      <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors hover:bg-accent/30">
        {running ? (
          <Loader2Icon className="size-3.5 shrink-0 animate-spin text-info" />
        ) : output !== null ? (
          <CheckCircle2Icon className="size-3.5 shrink-0 text-emerald-500" />
        ) : (
          <XCircleIcon className="size-3.5 shrink-0 text-destructive" />
        )}
        <Icon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">
          {title.verb && <span className="font-semibold text-foreground">{title.verb}</span>}
          {title.verb && title.body.length > 0 && " "}
          <span className="text-muted-foreground">{title.body}</span>
        </span>
        {duration !== undefined && (
          <span className="shrink-0 tabular-nums text-muted-foreground">
            {formatToolDuration(duration)}
          </span>
        )}
        {running && (
          <span className="shrink-0 text-info text-[10px] font-medium uppercase tracking-wide">
            running
          </span>
        )}
        {hasOutput && (
          <ChevronRightIcon className="size-3 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/activity-entry:rotate-90" />
        )}
      </CollapsibleTrigger>

      {hasOutput && (
        <CollapsibleContent>
          <div className="mx-3 mb-2 max-h-48 overflow-auto rounded-md bg-muted/50 px-3 py-2">
            <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-muted-foreground">
              {truncateOutput(output!)}
            </pre>
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

function truncateOutput(text: string): string {
  const MAX_LINES = 30;
  const MAX_CHARS = 4_000;
  const lines = text.split("\n");
  if (lines.length <= MAX_LINES && text.length <= MAX_CHARS) return text;
  const sliced = lines.slice(-MAX_LINES).join("\n");
  if (sliced.length > MAX_CHARS) return `…${sliced.slice(-MAX_CHARS)}`;
  return lines.length > MAX_LINES ? `… (${lines.length - MAX_LINES} lines hidden)\n${sliced}` : sliced;
}
