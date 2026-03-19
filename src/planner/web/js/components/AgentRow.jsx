import { useState, useEffect } from 'preact/hooks'
import { shortenModel, formatTokens } from '../lib/utils.js'

function ThinkingTimer({ since }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = new Date(since).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [since])

  const text = elapsed < 60
    ? `${elapsed}s`
    : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`

  return <span class="thinking-timer">{text}</span>
}

const STATUS = {
  null:        { symbol: '○', statusCls: 'agent-status-queued',   nameCls: 'agent-name-queued' },
  running:     { symbol: '●', statusCls: 'agent-status-running',  nameCls: 'agent-name-running' },
  completed:   { symbol: '✓', statusCls: 'agent-status-done',     nameCls: 'agent-name-done' },
  failed:      { symbol: '✗', statusCls: 'agent-status-failed',   nameCls: 'agent-name-failed' },
}

export function AgentRow({ agent, maxLines = 5 }) {
  const s = STATUS[agent.status] || STATUS.running
  const actions = agent.recentActions || []
  const start = Math.max(0, actions.length - maxLines)

  return (
    <tr>
      <td class={`col-status ${s.statusCls}`}>{s.symbol}</td>
      <td class={s.nameCls}>{agent.name || agent.id}</td>
      <td class="col-model agent-model-cell">{shortenModel(agent.model)}</td>
      <td class="col-tokens agent-tokens-cell">{formatTokens(agent.tokensSent || 0)}</td>
      <td class="col-tokens agent-tokens-cell">{formatTokens(agent.tokensReceived || 0)}</td>
      <td class="col-doing">
        <DoingCell status={agent.status} actions={actions} start={start} />
      </td>
    </tr>
  )
}

function DoingCell({ status, actions, start }) {
  if (status === null) return <span class="agent-doing-dim">queued</span>
  if (status === 'completed') return <span class="agent-doing-dim">done</span>
  if (status === 'failed') return <span class="agent-doing-dim agent-doing-failed">failed</span>

  // running
  if (actions.length === 0) return <span class="agent-doing-line">initializing...</span>

  return (
    <div class="agent-doing-lines">
      {actions.slice(start).map((action, i) => {
        const isThinking = typeof action === 'object' && action.tool === 'thinking'
        const inFlight = typeof action === 'object' && !!action.inFlight

        if (isThinking) {
          return (
            <div key={i} class="agent-doing-line agent-doing-thinking">
              <span class={`agent-doing-prefix ${inFlight ? 'prefix-active thinking-dot' : 'prefix-done'}`}>
                {inFlight ? '●' : '·'}
              </span>
              {inFlight
                ? <>thinking <ThinkingTimer since={action.ts} /></>
                : `thought for ${action.summary}`
              }
            </div>
          )
        }

        const text = typeof action === 'string'
          ? action
          : (action.summary ? `${action.tool}: ${action.summary}` : action.tool)

        return (
          <div key={i} class={`agent-doing-line${inFlight ? ' agent-doing-inflight' : ''}`}>
            <span class={`agent-doing-prefix ${inFlight ? 'prefix-active' : 'prefix-done'}`}>
              {inFlight ? '●' : '·'}
            </span>
            {text}
          </div>
        )
      })}
    </div>
  )
}
