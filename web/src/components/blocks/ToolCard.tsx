// Tool-call renderer. Renders each call as a single muted-text trigger
// line (status icon + truncated `name(argsSummary)`); clicking expands an
// indented panel with the parameters JSON and output preview. The big
// border-stripe / badge / pill card shell was removed deliberately — tool
// calls used to dominate the transcript, and the goal is for the
// assistant's prose to read first.

import {
  CheckIcon,
  ChevronRightIcon,
  CircleSlashIcon,
  CopyIcon,
  Loader2Icon,
  Maximize2Icon,
  Minimize2Icon,
  XCircleIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CodeBlock,
  CodeBlockActions,
  CodeBlockHeader,
  CodeBlockTitle,
} from "@/components/ai-elements/code-block";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { RenderItem, ToolState } from "@/lib/renderItems";
import { iconForTool } from "@/lib/toolIcon";
import {
  type ToolRunCall,
  type ToolTitle,
  formatToolRunLabel,
  formatToolTitle,
} from "@/lib/toolTitle";
import { useFileViewer } from "@/shell/FileViewerContext";
import { detectLang } from "@/shell/codeViewerHelpers";

const OUTPUT_PREVIEW_LINE_LIMIT = 80;
const OUTPUT_PREVIEW_CHAR_LIMIT = 12_000;

const EDIT_TOOL_NAMES = new Set([
  "Edit",
  "MultiEdit",
  "NotebookEdit",
  "sys_os_edit",
  "edit",
]);

interface EditEntry {
  oldStr: string;
  newStr: string;
}

function extractEdits(
  name: string,
  args: Record<string, unknown>,
): { filePath: string; edits: EditEntry[] } | null {
  const path =
    (typeof args.file_path === "string" && args.file_path) ||
    (typeof args.notebook_path === "string" && args.notebook_path) ||
    (typeof args.path === "string" && args.path) ||
    (typeof args.filePath === "string" && args.filePath) ||
    null;
  if (!path) return null;

  if (name === "MultiEdit" && Array.isArray(args.edits)) {
    const edits: EditEntry[] = [];
    for (const e of args.edits) {
      if (e && typeof e === "object" && "old_string" in e && "new_string" in e) {
        edits.push({
          oldStr: String((e as Record<string, unknown>).old_string ?? ""),
          newStr: String((e as Record<string, unknown>).new_string ?? ""),
        });
      }
    }
    return edits.length > 0 ? { filePath: path, edits } : null;
  }

  const oldStr =
    typeof args.old_string === "string"
      ? args.old_string
      : typeof args.old_str === "string"
        ? args.old_str
        : null;
  const newStr =
    typeof args.new_string === "string"
      ? args.new_string
      : typeof args.new_str === "string"
        ? args.new_str
        : null;
  if (oldStr === null || newStr === null) return null;

  return { filePath: path, edits: [{ oldStr, newStr }] };
}

function EditDiffPanel({
  filePath,
  edits,
}: {
  filePath: string;
  edits: EditEntry[];
}) {
  return (
    <div className="rounded-md border bg-muted/20 overflow-hidden text-sm font-mono">
      <div className="flex items-center justify-between border-b bg-muted/40 px-3 py-1.5">
        <span className="truncate font-medium text-xs uppercase tracking-wide text-muted-foreground">
          {filePath}
        </span>
      </div>
      <div className="overflow-x-auto">
        {edits.map((edit, i) => (
          <div key={i} className={edits.length > 1 ? "border-b last:border-b-0" : ""}>
            {edit.oldStr.split("\n").map((line, j) => (
              <div
                key={`old-${j}`}
                className="bg-red-500/10 text-red-700 dark:text-red-400 px-3 py-0.5 whitespace-pre-wrap break-all"
              >
                <span className="select-none opacity-50 mr-2">-</span>
                {line}
              </div>
            ))}
            {edit.newStr.split("\n").map((line, j) => (
              <div
                key={`new-${j}`}
                className="bg-green-500/10 text-green-700 dark:text-green-400 px-3 py-0.5 whitespace-pre-wrap break-all"
              >
                <span className="select-none opacity-50 mr-2">+</span>
                {line}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

const READ_TOOL_NAMES = new Set(["Read", "sys_os_read", "read"]);
const WRITE_TOOL_NAMES = new Set(["Write", "sys_os_write", "write"]);
const SHELL_TOOL_NAMES = new Set(["Bash", "sys_os_shell", "shell", "bash"]);

function extractFilePath(args: Record<string, unknown>): string | null {
  return (
    (typeof args.file_path === "string" && args.file_path) ||
    (typeof args.path === "string" && args.path) ||
    (typeof args.filePath === "string" && args.filePath) ||
    null
  );
}

function extractWriteInfo(
  args: Record<string, unknown>,
): { filePath: string; content: string } | null {
  const path = extractFilePath(args);
  if (!path) return null;
  const content =
    typeof args.content === "string"
      ? args.content
      : typeof args.file_text === "string"
        ? args.file_text
        : null;
  return content !== null ? { filePath: path, content } : null;
}

const SHELL_TAIL_LINES = 20;

function getShellOutputPreview(
  output: string,
  expanded: boolean,
): OutputPreview & { skippedLineCount: number } {
  const lines = output.length === 0 ? [] : output.split("\n");
  const lineCount = lines.length;
  const charCount = output.length;

  if (
    expanded ||
    (lineCount <= OUTPUT_PREVIEW_LINE_LIMIT && charCount <= OUTPUT_PREVIEW_CHAR_LIMIT)
  ) {
    return {
      text: output,
      isTruncated: false,
      lineCount,
      charCount,
      shownLineCount: lineCount,
      shownCharCount: charCount,
      hiddenLineCount: 0,
      hiddenCharCount: 0,
      skippedLineCount: 0,
    };
  }

  const tailLines = lines.slice(-SHELL_TAIL_LINES);
  const text = tailLines.join("\n");
  const skippedLineCount = lineCount - SHELL_TAIL_LINES;

  return {
    text,
    isTruncated: true,
    lineCount,
    charCount,
    shownLineCount: tailLines.length,
    shownCharCount: text.length,
    hiddenLineCount: skippedLineCount,
    hiddenCharCount: charCount - text.length,
    skippedLineCount,
  };
}

function HighlightedCodePanel({
  filePath,
  code,
  copyLabel,
}: {
  filePath: string;
  code: string;
  copyLabel: string;
}) {
  const language = detectLang(filePath);
  return (
    <CodeBlock code={code} language={language === "text" ? "json" : language}>
      <CodeBlockHeader>
        <CodeBlockTitle className="min-w-0">
          <span className="truncate font-medium text-xs uppercase tracking-wide text-muted-foreground">
            {filePath}
          </span>
        </CodeBlockTitle>
        <CodeBlockActions>
          <CopyTextButton label={copyLabel} text={code} />
        </CodeBlockActions>
      </CodeBlockHeader>
    </CodeBlock>
  );
}

function ReadOutputPanel({ filePath, output }: { filePath: string; output: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  useEffect(() => setIsExpanded(false), [output]);

  const collapsedPreview = useMemo(() => getOutputPreview(output), [output]);
  const preview = useMemo(() => getOutputPreview(output, isExpanded), [output, isExpanded]);
  const canExpand = collapsedPreview.isTruncated;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "relative rounded-md",
          canExpand && !isExpanded && "max-h-80 overflow-hidden",
          (!canExpand || isExpanded) && "max-h-[36rem] overflow-auto",
        )}
      >
        <HighlightedCodePanel filePath={filePath} code={preview.text} copyLabel="Copy output" />
        {canExpand && !isExpanded && (
          <div className="pointer-events-none absolute inset-x-px bottom-px h-16 rounded-b-md bg-gradient-to-t from-background to-transparent" />
        )}
      </div>
      {canExpand && (
        <div className="flex flex-col gap-2 rounded-md border bg-muted/30 px-3 py-2 text-muted-foreground text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="min-w-0">
            {isExpanded ? "Showing full output" : "Previewing output"} (
            {formatOutputStats(isExpanded ? preview : collapsedPreview)})
          </span>
          <Button
            className="w-fit"
            onClick={() => setIsExpanded((value) => !value)}
            size="xs"
            type="button"
            variant="outline"
          >
            {isExpanded ? <Minimize2Icon className="size-3" /> : <Maximize2Icon className="size-3" />}
            {isExpanded ? "Collapse" : "Expand"}
          </Button>
        </div>
      )}
    </div>
  );
}

function WritePreviewPanel({
  filePath,
  content,
}: {
  filePath: string;
  content: string;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const collapsedPreview = useMemo(() => getOutputPreview(content), [content]);
  const preview = useMemo(() => getOutputPreview(content, isExpanded), [content, isExpanded]);
  const canExpand = collapsedPreview.isTruncated;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "relative rounded-md",
          canExpand && !isExpanded && "max-h-80 overflow-hidden",
          (!canExpand || isExpanded) && "max-h-[36rem] overflow-auto",
        )}
      >
        <HighlightedCodePanel filePath={filePath} code={preview.text} copyLabel="Copy content" />
        {canExpand && !isExpanded && (
          <div className="pointer-events-none absolute inset-x-px bottom-px h-16 rounded-b-md bg-gradient-to-t from-background to-transparent" />
        )}
      </div>
      {canExpand && (
        <div className="flex flex-col gap-2 rounded-md border bg-muted/30 px-3 py-2 text-muted-foreground text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="min-w-0">
            {isExpanded ? "Showing full content" : "Previewing content"} (
            {formatOutputStats(isExpanded ? preview : collapsedPreview)})
          </span>
          <Button
            className="w-fit"
            onClick={() => setIsExpanded((value) => !value)}
            size="xs"
            type="button"
            variant="outline"
          >
            {isExpanded ? <Minimize2Icon className="size-3" /> : <Maximize2Icon className="size-3" />}
            {isExpanded ? "Collapse" : "Expand"}
          </Button>
        </div>
      )}
    </div>
  );
}

function ShellOutputSection({ output }: { output: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  useEffect(() => setIsExpanded(false), [output]);

  const collapsedPreview = useMemo(() => getShellOutputPreview(output, false), [output]);
  const preview = useMemo(
    () => getShellOutputPreview(output, isExpanded),
    [output, isExpanded],
  );
  const canExpand = collapsedPreview.isTruncated;

  return (
    <div className="space-y-2">
      {canExpand && !isExpanded && collapsedPreview.skippedLineCount > 0 && (
        <button
          type="button"
          onClick={() => setIsExpanded(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed bg-muted/30 px-3 py-1.5 text-muted-foreground text-xs transition-colors hover:bg-muted/50 hover:text-foreground"
        >
          <Maximize2Icon className="size-3" />
          Show {collapsedPreview.skippedLineCount.toLocaleString()} earlier lines
        </button>
      )}
      <div
        className={cn(
          "relative rounded-md",
          (!canExpand || isExpanded) && "max-h-[36rem] overflow-auto",
        )}
      >
        <CodePanel
          title="Output"
          text={preview.text}
          copyText={output}
          copyLabel="Copy output"
        />
      </div>
      {canExpand && isExpanded && (
        <div className="flex justify-end">
          <Button
            className="w-fit"
            onClick={() => setIsExpanded(false)}
            size="xs"
            type="button"
            variant="outline"
          >
            <Minimize2Icon className="size-3" />
            Collapse
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * Tools whose `args.path` field is a workspace file path that the user
 * should be able to click to open in the FileViewer.
 */
const FILE_PATH_TOOLS = new Set(["sys_os_read", "sys_os_write", "sys_os_edit"]);

/**
 * If the string is valid JSON, return its 2-space-indented form.
 * Otherwise return the string verbatim. The code block renders inside a
 * `<pre>`, so a compact one-line JSON payload otherwise becomes a single
 * horizontal-scrolling line.
 */
function prettyPrintIfJson(s: string): string {
  try {
    const parsed: unknown = JSON.parse(s);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return s;
  }
}

export function formatToolDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0ms";
  }

  if (seconds < 1) {
    return `${Math.max(1, Math.round(seconds * 1000))}ms`;
  }

  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const totalSeconds = Math.round(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (totalSeconds < 60 * 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

interface OutputPreview {
  text: string;
  isTruncated: boolean;
  lineCount: number;
  charCount: number;
  shownLineCount: number;
  shownCharCount: number;
  hiddenLineCount: number;
  hiddenCharCount: number;
}

export function getOutputPreview(output: string, expanded = false): OutputPreview {
  const lines = output.length === 0 ? [] : output.split("\n");
  const lineCount = lines.length;
  const charCount = output.length;

  if (
    expanded ||
    (lineCount <= OUTPUT_PREVIEW_LINE_LIMIT && charCount <= OUTPUT_PREVIEW_CHAR_LIMIT)
  ) {
    return {
      text: output,
      isTruncated: false,
      lineCount,
      charCount,
      shownLineCount: lineCount,
      shownCharCount: charCount,
      hiddenLineCount: 0,
      hiddenCharCount: 0,
    };
  }

  let text =
    lineCount > OUTPUT_PREVIEW_LINE_LIMIT
      ? lines.slice(0, OUTPUT_PREVIEW_LINE_LIMIT).join("\n")
      : output;

  if (text.length > OUTPUT_PREVIEW_CHAR_LIMIT) {
    text = text.slice(0, OUTPUT_PREVIEW_CHAR_LIMIT).trimEnd();
  }

  const shownLineCount = text.length === 0 ? 0 : text.split("\n").length;
  const shownCharCount = text.length;

  return {
    text,
    isTruncated: shownCharCount < charCount,
    lineCount,
    charCount,
    shownLineCount,
    shownCharCount,
    hiddenLineCount: Math.max(0, lineCount - shownLineCount),
    hiddenCharCount: Math.max(0, charCount - shownCharCount),
  };
}

interface ToolCardProps {
  /** Display name for the tool. For native tools, this is the friendly label. */
  name: string;
  /**
   * Set for native (provider-managed) tools — the underlying type
   * (e.g. "web_search_call"). Used to pick the category icon.
   */
  nativeToolType?: string;
  /** Brief one-line summary of arguments shown next to the name. */
  argsSummary?: string;
  /** Full args dict, rendered as JSON in the expanded panel. */
  arguments: Record<string, unknown>;
  /** Tool output, or null if not yet available / never produced. */
  output: string | null;
  state: ToolState;
  /** Seconds from the page's performance clock when the tool call rendered. */
  startedAt?: number | null;
  /** Completed runtime in seconds. Undefined when historical data lacks timing. */
  duration?: number;
}

export function ToolCard({
  name,
  nativeToolType,
  argsSummary,
  arguments: args,
  output,
  state,
  startedAt,
  duration,
}: ToolCardProps) {
  const title = useMemo(() => formatToolTitle(name, args, argsSummary), [name, args, argsSummary]);
  const inputJson = useMemo(() => JSON.stringify(args, null, 2), [args]);
  const formattedOutput = useMemo(
    () => (output === null ? null : prettyPrintIfJson(output)),
    [output],
  );
  const elapsedDuration = useElapsedDuration(state === "input-available" ? startedAt : null);
  const displayDuration = duration ?? elapsedDuration;

  const editInfo = useMemo(
    () => (EDIT_TOOL_NAMES.has(name) ? extractEdits(name, args) : null),
    [name, args],
  );
  const readPath = useMemo(
    () => (READ_TOOL_NAMES.has(name) ? extractFilePath(args) : null),
    [name, args],
  );
  const writeInfo = useMemo(
    () => (WRITE_TOOL_NAMES.has(name) ? extractWriteInfo(args) : null),
    [name, args],
  );
  const isShellTool = SHELL_TOOL_NAMES.has(name);

  // When this is a file-path tool and we're inside AppShell, make the path
  // in the trigger row a clickable link that opens the FileViewer.
  const openFile = useFileViewer();
  const rawPath =
    FILE_PATH_TOOLS.has(name) &&
    typeof args.path === "string" &&
    args.path.length > 0 &&
    !args.path.startsWith("/") // FileViewer rejects absolute paths
      ? args.path
      : null;
  const onBodyClick = openFile && rawPath ? () => openFile(rawPath) : undefined;

  return (
    <Collapsible
      defaultOpen={editInfo !== null || writeInfo !== null}
      className="group not-prose w-full"
    >
      <ToolTriggerRow
        title={title}
        name={name}
        nativeToolType={nativeToolType}
        state={state}
        duration={displayDuration}
        onBodyClick={onBodyClick}
      />
      <CollapsibleContent className="mt-1 ml-2 space-y-2 border-l pl-3 py-1 data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=open]:animate-in">
        {editInfo !== null ? (
          <EditDiffPanel filePath={editInfo.filePath} edits={editInfo.edits} />
        ) : writeInfo !== null ? (
          <WritePreviewPanel filePath={writeInfo.filePath} content={writeInfo.content} />
        ) : (
          <CodePanel
            title="Parameters"
            text={inputJson}
            copyText={inputJson}
            copyLabel="Copy parameters"
          />
        )}
        {formattedOutput !== null && readPath !== null ? (
          <ReadOutputPanel filePath={readPath} output={formattedOutput} />
        ) : formattedOutput !== null && isShellTool ? (
          <ShellOutputSection output={formattedOutput} />
        ) : formattedOutput !== null ? (
          <OutputSection output={formattedOutput} />
        ) : null}
        {formattedOutput === null && state === "input-available" && (
          <ToolPendingOutput duration={displayDuration} />
        )}
        {formattedOutput === null &&
          (state === "output-error" || state === "cancelled" || state === "no-output") && (
            <EmptyOutputState state={state} />
          )}
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * Render the folded (older) part of a contiguous tool run as one muted
 * summary line ("Read 2 files"). Clicking expands to show each tool as
 * its own (also-collapsible) trigger. `BlockRenderer` decides which
 * tools fold here: older tools once the visible tail of the most
 * recent ones has been peeled off.
 */
export function ToolGroupSummary({ tools }: { tools: RenderItem[] }) {
  const label = formatToolRunLabel(tools.map(toolRunCall));
  return (
    // Named `group/tool-summary` so this collapsible only rotates its
    // OWN chevron (line 296 in `ToolTriggerRow` uses an unnamed
    // `group-data-[state=open]:rotate-90` that would otherwise match
    // any ancestor `.group[data-state=open]` and incorrectly rotate
    // chevrons of inner tool cards when this outer group is open).
    <Collapsible defaultOpen={false} className="group/tool-summary not-prose w-full">
      <CollapsibleTrigger className="flex cursor-pointer items-center gap-1.5 py-0.5 text-left text-muted-foreground text-sm transition-colors hover:text-foreground">
        <ChevronRightIcon className="size-3.5 shrink-0 transition-transform group-data-[state=open]/tool-summary:rotate-90" />
        <span>{label}</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1 ml-2 space-y-1 border-l pl-3 pt-1 pb-0 data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=open]:animate-in">
        {tools.map((item) => {
          if (item.kind === "tool") {
            return (
              <ToolCard
                key={`tool:${item.execution.callId}`}
                name={item.execution.name}
                argsSummary={item.execution.argsSummary}
                arguments={item.execution.arguments}
                output={item.output}
                state={item.state}
                startedAt={item.startedAt}
                duration={item.duration}
              />
            );
          }
          if (item.kind === "native_tool") {
            return (
              <ToolCard
                key={`native:${item.itemId ?? item.label}`}
                name={item.label}
                nativeToolType={item.toolType}
                arguments={item.data}
                output={null}
                state="output-available"
              />
            );
          }
          return null;
        })}
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Tool name + args used to categorize a run item for the summary label. */
function toolRunCall(item: RenderItem): ToolRunCall {
  if (item.kind === "tool") {
    return { name: item.execution.name, args: item.execution.arguments };
  }
  if (item.kind === "native_tool") return { name: item.toolType, args: item.data };
  return { name: "" };
}

/**
 * Single muted-text trigger line for a tool call. Status/category icon
 * at left, title (verb bold + dynamic body) in the middle truncated to
 * one line, optional duration on the right, chevron at the far right.
 */
function ToolTriggerRow({
  title,
  name,
  nativeToolType,
  state,
  duration,
  onBodyClick,
}: {
  title: ToolTitle;
  name: string;
  nativeToolType: string | undefined;
  state: ToolState;
  duration: number | undefined;
  /** When set, the body text (e.g. file path) is rendered as a clickable link. */
  onBodyClick?: () => void;
}) {
  const tooltip =
    title.verb && title.body ? `${title.verb} ${title.body}` : (title.verb ?? title.body);
  return (
    <CollapsibleTrigger
      title={tooltip}
      className="flex w-full cursor-pointer items-center gap-1.5 py-0.5 text-left text-muted-foreground text-sm transition-colors hover:text-foreground"
    >
      <StatusIcon name={name} nativeToolType={nativeToolType} state={state} />
      <span className="min-w-0 flex-1 truncate">
        {title.verb !== null && <span className="font-semibold text-foreground">{title.verb}</span>}
        {title.verb !== null && title.body.length > 0 && " "}
        {onBodyClick ? (
          // Use <span role="link"> instead of <button> to avoid nesting
          // interactive elements — CollapsibleTrigger already renders as
          // a <button>, and nested buttons are invalid HTML.
          <span
            role="link"
            tabIndex={0}
            className="underline decoration-dotted underline-offset-2 hover:text-foreground transition-colors cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              onBodyClick();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault(); // prevent Space from triggering parent button's click via keyup
                e.stopPropagation();
                onBodyClick();
              }
            }}
          >
            {title.body}
          </span>
        ) : (
          title.body
        )}
      </span>
      {duration !== undefined && (
        <span className="shrink-0 tabular-nums opacity-70">{formatToolDuration(duration)}</span>
      )}
      <ChevronRightIcon className="size-3.5 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
    </CollapsibleTrigger>
  );
}

/**
 * Icon shown at the start of a tool-call row. The transient states
 * (running / errored / cancelled) take priority so the user sees an
 * unambiguous progress signal; once the tool has completed cleanly we
 * fall back to a category icon picked from the tool name.
 */
function StatusIcon({
  name,
  nativeToolType,
  state,
}: {
  name: string;
  nativeToolType: string | undefined;
  state: ToolState;
}): ReactNode {
  if (state === "input-available") {
    // Slightly larger and tinted so the running indicator is the one
    // thing in the row that actively draws the eye.
    return <Loader2Icon className="size-3.5 shrink-0 animate-spin text-info" />;
  }
  if (state === "output-error") {
    return <XCircleIcon className="size-3.5 shrink-0 text-destructive" />;
  }
  if (state === "cancelled" || state === "no-output") {
    // Turn over, no output recorded — muted slash, not the error icon.
    return <CircleSlashIcon className="size-3.5 shrink-0" />;
  }
  const Icon = iconForTool(name, nativeToolType);
  return <Icon className="size-3.5 shrink-0" />;
}

function CodePanel({
  title,
  text,
  copyText,
  copyLabel,
}: {
  title: string;
  text: string;
  copyText: string;
  copyLabel: string;
}) {
  return (
    <CodeBlock code={text} language="json">
      <CodeBlockHeader>
        <CodeBlockTitle className="min-w-0">
          <span className="truncate font-medium uppercase tracking-wide">{title}</span>
        </CodeBlockTitle>
        <CodeBlockActions>
          <CopyTextButton label={copyLabel} text={copyText} />
        </CodeBlockActions>
      </CodeBlockHeader>
    </CodeBlock>
  );
}

function OutputSection({ output }: { output: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  useEffect(() => setIsExpanded(false), [output]);

  const collapsedPreview = useMemo(() => getOutputPreview(output), [output]);
  const preview = useMemo(() => getOutputPreview(output, isExpanded), [output, isExpanded]);
  const canExpand = collapsedPreview.isTruncated;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "relative rounded-md",
          canExpand && !isExpanded && "max-h-80 overflow-hidden",
          // overflow-auto (vs overflow-y-auto) keeps long single-line output from blowing out the bubble width.
          (!canExpand || isExpanded) && "max-h-[36rem] overflow-auto",
        )}
      >
        <CodePanel title="Output" text={preview.text} copyText={output} copyLabel="Copy output" />
        {canExpand && !isExpanded && (
          <div className="pointer-events-none absolute inset-x-px bottom-px h-16 rounded-b-md bg-gradient-to-t from-background to-transparent" />
        )}
      </div>
      {canExpand && (
        <div className="flex flex-col gap-2 rounded-md border bg-muted/30 px-3 py-2 text-muted-foreground text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="min-w-0">
            {isExpanded ? "Showing full output" : "Previewing output"} (
            {formatOutputStats(isExpanded ? preview : collapsedPreview)})
          </span>
          <Button
            className="w-fit"
            onClick={() => setIsExpanded((value) => !value)}
            size="xs"
            type="button"
            variant="outline"
          >
            {isExpanded ? (
              <Minimize2Icon className="size-3" />
            ) : (
              <Maximize2Icon className="size-3" />
            )}
            {isExpanded ? "Collapse" : "Expand"}
          </Button>
        </div>
      )}
    </div>
  );
}

function ToolPendingOutput({ duration }: { duration: number | undefined }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/30 p-3">
      <div className="flex items-center gap-2 text-muted-foreground text-ui">
        <Loader2Icon className="size-4 animate-spin text-info" />
        <span>
          Waiting for output
          {duration !== undefined ? ` for ${formatToolDuration(duration)}` : ""}
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-info/70" />
      </div>
    </div>
  );
}

function EmptyOutputState({ state }: { state: "output-error" | "cancelled" | "no-output" }) {
  let message: string;
  if (state === "cancelled") {
    message = "Tool was cancelled before output arrived.";
  } else if (state === "no-output") {
    message = "No output was recorded for this tool call.";
  } else {
    message = "Tool did not return output before the response failed.";
  }
  return (
    <div className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-muted-foreground text-ui">
      {message}
    </div>
  );
}

interface CopyTextButtonProps {
  text: string;
  label: string;
}

function CopyTextButton({ text, label }: CopyTextButtonProps) {
  const [isCopied, setIsCopied] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  const copyToClipboard = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }

    setIsCopied(true);
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = window.setTimeout(() => setIsCopied(false), 2000);
  }, [text]);

  useEffect(
    () => () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    },
    [],
  );

  const Icon = isCopied ? CheckIcon : CopyIcon;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          aria-label={isCopied ? "Copied" : label}
          className="size-6 text-muted-foreground"
          onClick={copyToClipboard}
          size="icon-xs"
          type="button"
          variant="ghost"
        >
          <Icon className="size-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{isCopied ? "Copied" : label}</TooltipContent>
    </Tooltip>
  );
}

function useElapsedDuration(startedAt: number | null | undefined): number | undefined {
  const [now, setNow] = useState(() => getNowSeconds());

  useEffect(() => {
    if (startedAt === null || startedAt === undefined) {
      return;
    }

    setNow(getNowSeconds());
    const interval = window.setInterval(() => setNow(getNowSeconds()), 500);
    return () => window.clearInterval(interval);
  }, [startedAt]);

  if (startedAt === null || startedAt === undefined) {
    return undefined;
  }

  return Math.max(0, now - startedAt);
}

function getNowSeconds(): number {
  if (typeof performance !== "undefined") {
    return performance.now() / 1000;
  }
  return Date.now() / 1000;
}

function formatOutputStats(preview: OutputPreview): string {
  if (!preview.isTruncated) {
    return `${formatCount(preview.lineCount, "line")} / ${formatCount(preview.charCount, "char")}`;
  }

  const hidden: string[] = [];
  if (preview.hiddenLineCount > 0) {
    hidden.push(`${formatCount(preview.hiddenLineCount, "line")} hidden`);
  }
  if (preview.hiddenCharCount > 0) {
    hidden.push(`${formatCount(preview.hiddenCharCount, "char")} hidden`);
  }

  return `${formatCount(preview.shownLineCount, "line")} / ${formatCount(
    preview.shownCharCount,
    "char",
  )} shown; ${hidden.join(", ")}`;
}

function formatCount(count: number, unit: string): string {
  return `${count.toLocaleString()} ${unit}${count === 1 ? "" : "s"}`;
}
