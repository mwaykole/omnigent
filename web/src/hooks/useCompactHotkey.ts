// ⌘⇧K (Ctrl+Shift+K on Win/Linux) triggers context compaction. The Shift
// modifier avoids collision with ⌘K (command palette), which explicitly
// guards `e.shiftKey === false`.

import { useEffect } from "react";

import { useChatStore } from "@/store/chatStore";

const HOTKEY_OWNING_SURFACES = ".xterm, .monaco-editor";

function focusOwnsHotkey(): boolean {
  const el = document.activeElement;
  return el instanceof Element && el.closest(HOTKEY_OWNING_SURFACES) !== null;
}

export function useCompactHotkey(): void {
  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent): void => {
      if (e.repeat) return;
      if (!(e.metaKey || e.ctrlKey) || !e.shiftKey || e.altKey) return;
      if (e.key !== "k" && e.key !== "K") return;
      if (e.getModifierState("AltGraph")) return;
      if (focusOwnsHotkey()) return;

      e.preventDefault();
      e.stopPropagation();
      useChatStore.getState().compact();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}
