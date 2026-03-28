import { KoanStore, AgentInfo, ArtifactFile, ActivityEntry, Interaction, CompletionInfo } from '../store/index'

// connectSSE opens an EventSource and wires every SSE event type to a store action.
// Returns the EventSource so the caller can close it on unmount or reconnect.
// Does NOT schedule its own reconnect — App.tsx owns that lifecycle.
export function connectSSE(store: KoanStore): EventSource {
  const es = new EventSource('/events')

  store.getState().setConnected(true)

  // ── Structural events ──────────────────────────────────────────────────────

  es.addEventListener('phase', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { phase: string }
    store.getState().setPhase(d.phase)
  })

  es.addEventListener('subagent', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as Record<string, unknown>
    // _build_subagent_json returns {"agent_id": None} when no primary agent is active.
    // Guard against this to avoid setting primaryAgent to an object with undefined fields.
    if (d['agent_id'] === null || d['agent_id'] === undefined) {
      store.getState().setPrimaryAgent(null)
      return
    }
    store.getState().setPrimaryAgent({
      agentId:        d['agent_id'] as string,
      role:           d['role'] as string,
      model:          d['model'] as string | null,
      step:           d['step'] as number,
      stepName:       d['step_name'] as string,
      startedAt:      d['started_at_ms'] as number,
      tokensSent:     d['tokens_sent'] as number,
      tokensReceived: d['tokens_received'] as number,
    } satisfies AgentInfo)
  })

  es.addEventListener('subagent-idle', () => {
    store.getState().setPrimaryAgent(null)
  })

  es.addEventListener('agents', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { agents: Record<string, unknown>[] }
    // d.agents is an array from _build_agents_json(). Python emits snake_case;
    // map to camelCase here at the bridge boundary.
    // Without this mapping, Object.fromEntries would key everything under "undefined"
    // because a.agentId doesn't exist on the raw JSON (it's a.agent_id).
    const scouts = Object.fromEntries(
      d.agents.map((a) => [a['agent_id'] as string, {
        agentId:        a['agent_id'] as string,
        role:           a['role'] as string,
        model:          a['model'] as string | null,
        step:           a['step'] as number,
        stepName:       a['step_name'] as string,
        startedAt:      a['started_at_ms'] as number,
        tokensSent:     a['tokens_sent'] as number,
        tokensReceived: a['tokens_received'] as number,
      } satisfies AgentInfo])
    )
    store.getState().setScouts(scouts)
  })

  es.addEventListener('artifacts', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { artifacts: ArtifactFile[] }
    store.getState().setArtifacts(d.artifacts)
  })

  es.addEventListener('intake-progress', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as Record<string, unknown>
    store.getState().setIntakeProgress({
      subPhase:   (d['subPhase'] as string) ?? '',
      confidence: (d['confidence'] as string | null) ?? null,
      summary:    (d['summary'] as string) ?? '',
    })
  })

  // ── High-frequency events ──────────────────────────────────────────────────

  es.addEventListener('token-delta', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { delta: string }
    store.getState().appendStreamDelta(d.delta)
  })

  es.addEventListener('token-clear', () => {
    store.getState().clearStream()
  })

  es.addEventListener('logs', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { line: ActivityEntry }
    store.getState().appendLog(d.line)
  })

  // ── Notifications ──────────────────────────────────────────────────────────

  es.addEventListener('notification', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as Record<string, unknown>
    // Backend notification types are categorical event names (e.g. 'runner_error'),
    // NOT severity levels. Map to severity here at the bridge boundary.
    const SEVERITY_MAP: Record<string, 'error' | 'warning' | 'info'> = {
      runner_error: 'error',
      bootstrap_failure: 'error',
      spawn_failure: 'error',
      interaction_cancelled: 'info',
      config_warning: 'warning',
    }
    const type = d['type'] as string
    store.getState().addNotification({
      id: crypto.randomUUID(),
      type,
      severity: SEVERITY_MAP[type] ?? 'info',
      message: d['message'] as string,
      detail: d['details'] as string | undefined,
    })
  })

  // ── Interactions ───────────────────────────────────────────────────────────

  es.addEventListener('interaction', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { type: string } & Record<string, unknown>
    // 'cleared' means the interaction was resolved; restore the activity feed.
    store.getState().setInteraction(d.type === 'cleared' ? null : d as Interaction)
  })

  es.addEventListener('pipeline-end', (e) => {
    const d = JSON.parse((e as MessageEvent).data) as CompletionInfo
    store.getState().setCompletion(d)
  })

  // onerror will be overridden by App.tsx to schedule reconnects.
  es.onerror = () => {
    store.getState().setConnected(false)
    es.close()
  }

  return es
}
