import { useMemo, useState } from "react";
import { useNavigate } from "@/lib/routing";
import { useQueryClient } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AgentCard } from "@/components/AgentCard";
import { useAvailableAgents } from "@/hooks/useAvailableAgents";
import { childSessionsQueryKey } from "@/hooks/useChildSessions";
import { createSession } from "@/lib/sessionsApi";

const UI_ADDED_TITLE_PREFIX = "ui";

export function AddAgentDialog({
  parentSessionId,
  open,
  onOpenChange,
}: {
  parentSessionId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: agents } = useAvailableAgents();

  const agentList = agents ?? [];
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedAgent = agentList.find((a) => a.id === selectedAgentId) ?? null;

  const filtered = useMemo(() => {
    if (!search.trim()) return agentList;
    const q = search.toLowerCase();
    return agentList.filter(
      (a) =>
        a.display_name.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q) ||
        (a.description?.toLowerCase().includes(q) ?? false) ||
        a.skills.some((s) => s.name.toLowerCase().includes(q)),
    );
  }, [agentList, search]);

  function selectAgent(agentId: string): void {
    setSelectedAgentId(agentId);
    setError(null);
  }

  function handleOpenChange(next: boolean): void {
    if (!next) {
      setSelectedAgentId(null);
      setName("");
      setSearch("");
      setError(null);
      setSubmitting(false);
    }
    onOpenChange(next);
  }

  async function handleAdd(): Promise<void> {
    if (selectedAgent === null) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Enter a name for the agent.");
      return;
    }
    const title = `${UI_ADDED_TITLE_PREFIX}:${selectedAgent.name}:${trimmed}`;
    setSubmitting(true);
    setError(null);
    try {
      const session = await createSession(selectedAgent.id, [], {
        parentSessionId,
        subAgentName: null,
        title,
      });
      await queryClient.invalidateQueries({
        queryKey: childSessionsQueryKey(parentSessionId),
      });
      handleOpenChange(false);
      navigate(`/c/${session.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add the agent. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        data-testid="add-agent-dialog"
        className="flex max-h-[85vh] flex-col gap-4 sm:max-w-lg"
      >
        <DialogHeader>
          <DialogTitle>Add agent</DialogTitle>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
          {agentList.length > 4 && (
            <div className="relative">
              <SearchIcon className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <input
                data-testid="add-agent-search"
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search agents…"
                className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring"
              />
            </div>
          )}

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              {search.trim()
                ? `${filtered.length} result${filtered.length !== 1 ? "s" : ""}`
                : "Pick an agent"}
            </span>
            {filtered.length === 0 ? (
              <p data-testid="add-agent-empty" className="text-sm text-muted-foreground">
                {agentList.length === 0
                  ? <>No agents available on this server. Register one with{" "}
                      <code className="font-mono">omnigent server --agent</code>.</>
                  : "No agents match your search."}
              </p>
            ) : (
              filtered.map((agent) => (
                <div key={agent.id} className="flex flex-col gap-1">
                  <AgentCard
                    agent={agent}
                    selected={agent.id === selectedAgentId}
                    onSelect={() => selectAgent(agent.id)}
                    hover
                  />
                  {agent.skills.length > 0 && (
                    <div className="flex flex-wrap gap-1 pl-10">
                      {agent.skills.slice(0, 4).map((skill) => (
                        <span
                          key={skill.name}
                          title={skill.description}
                          className="inline-flex rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                        >
                          {skill.name}
                        </span>
                      ))}
                      {agent.skills.length > 4 && (
                        <span className="inline-flex rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          +{agent.skills.length - 4}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {selectedAgent !== null && (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="add-agent-name" className="text-sm font-medium text-muted-foreground">
                Name
              </label>
              <input
                id="add-agent-name"
                data-testid="add-agent-name-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name this agent"
                className="rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none transition-colors focus-visible:border-ring"
              />
            </div>
          )}

          {error !== null && (
            <p data-testid="add-agent-error" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button
            data-testid="add-agent-submit"
            onClick={handleAdd}
            loading={submitting}
            disabled={selectedAgent === null || !name.trim()}
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
