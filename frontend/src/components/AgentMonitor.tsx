import { useScoutList } from '../store/selectors'
import { useElapsed } from '../hooks/useElapsed'
import { formatTokens } from '../utils'
import { AgentInfo } from '../store/index'

function AgentRow({ agent }: { agent: AgentInfo }) {
  const elapsed = useElapsed(agent.startedAt)

  return (
    <tr>
      <td className="col-status agent-status-running">{'>>'}</td>
      <td className="col-agent agent-name-running">{agent.role}</td>
      <td className="col-model agent-model-cell">{agent.model ?? '--'}</td>
      <td className="col-tokens agent-tokens-cell">
        {formatTokens(agent.tokensSent, agent.tokensReceived)}
      </td>
      <td className="col-time agent-time-cell agent-timer">{elapsed}</td>
      <td className="col-doing agent-doing-dim">{agent.stepName || `step ${agent.step}`}</td>
    </tr>
  )
}

export function AgentMonitor() {
  const scouts = useScoutList()

  if (scouts.length === 0) return null

  return (
    <div id="monitor" className="monitor">
      <div className="monitor-inner">
        <div className="agent-table-header">
          <span className="monitor-label">Agents</span>
        </div>
        <table className="agent-table">
          <thead>
            <tr>
              <th className="col-status" />
              <th className="col-agent">Agent</th>
              <th className="col-model">Model</th>
              <th className="col-tokens">Tokens</th>
              <th className="col-time">Time</th>
              <th className="col-doing">Doing</th>
            </tr>
          </thead>
          <tbody>
            {scouts.map(a => (
              <AgentRow key={a.agentId} agent={a} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
