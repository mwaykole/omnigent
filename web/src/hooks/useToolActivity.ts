import { useMemo } from "react";
import { useChatStore } from "@/store/chatStore";
import type { ToolExecution, AnyBlock, ToolGroup, ToolResultBlock } from "@/lib/blocks";

export interface ToolActivityEntry {
  execution: ToolExecution;
  output: string | null;
  running: boolean;
  duration: number | undefined;
}

export interface ToolActivity {
  entries: ToolActivityEntry[];
  runningCount: number;
  completedCount: number;
  isActive: boolean;
}

const MAX_RECENT = 15;

export function useToolActivity(): ToolActivity {
  const blocks = useChatStore((s) => s.blocks);
  const activeResponse = useChatStore((s) => s.activeResponse);

  return useMemo(() => {
    const isStreaming = activeResponse?.state === "streaming";

    const resultsByCallId = new Map<string, string>();
    const toolGroups: { group: ToolGroup; index: number }[] = [];

    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (b.type === "tool_group") {
        toolGroups.push({ group: b, index: i });
      } else if (b.type === "tool_result") {
        const tr = b as ToolResultBlock;
        resultsByCallId.set(tr.callId, tr.output);
      }
    }

    const trailingLiveCallIds = new Set<string>();
    if (isStreaming) {
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.type === "tool_result" || b.type === "native_tool") continue;
        if (b.type !== "tool_group") break;
        for (const ex of (b as ToolGroup).executions) {
          if (ex.output === null && !resultsByCallId.has(ex.callId)) {
            trailingLiveCallIds.add(ex.callId);
          }
        }
      }
    }

    const entries: ToolActivityEntry[] = [];
    let runningCount = 0;

    const recentGroups = toolGroups.slice(-MAX_RECENT);
    for (const { group } of recentGroups) {
      for (const ex of group.executions) {
        const isRunning = trailingLiveCallIds.has(ex.callId);
        const output = ex.output ?? resultsByCallId.get(ex.callId) ?? null;

        let duration: number | undefined;
        if (!isRunning && group.ctx.createdAtS !== undefined) {
          const resultBlock = findResultBlock(blocks, ex.callId);
          if (resultBlock?.ctx.createdAtS !== undefined) {
            duration = resultBlock.ctx.createdAtS - group.ctx.createdAtS;
          }
        }

        entries.push({ execution: ex, output, running: isRunning, duration });
        if (isRunning) runningCount++;
      }
    }

    return {
      entries,
      runningCount,
      completedCount: entries.length - runningCount,
      isActive: runningCount > 0,
    };
  }, [blocks, activeResponse]);
}

function findResultBlock(blocks: AnyBlock[], callId: string): ToolResultBlock | null {
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.type === "tool_result" && (b as ToolResultBlock).callId === callId) {
      return b as ToolResultBlock;
    }
  }
  return null;
}
