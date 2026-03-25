// SSE dispatch layer. Connects to the event stream and routes each event
// type to a named handler from store.js. This file does not import useStore
// or know the store's internal shape -- all state mapping lives in store.js.

import {
  handleInitEvent,
  handlePhaseEvent,
  handleIntakeProgressEvent,
  handleStoriesEvent,
  handleScoutsEvent,
  handleAgentsEvent,
  handleLogsEvent,
  handleSubagentEvent,
  handleSubagentIdleEvent,
  handlePipelineEndEvent,
  handleAskEvent,
  handleModelConfigEvent,
  handleModelConfigConfirmedEvent,
  handleAskCancelledEvent,
  handleArtifactReviewEvent,
  handleArtifactReviewCancelledEvent,
  handleFrozenLogsEvent,
  handleWorkflowDecisionEvent,
  handleWorkflowDecisionCancelledEvent,
  handleArtifactsEvent,
  handleNotificationEvent,
  handleConnectionError,
  handleTokenDeltaEvent,
  handleTokenClearEvent,
} from './store.js'

export function connectSSE(token) {
  const es = new EventSource(`/events?session=${encodeURIComponent(token)}`)

  const handlers = {
    'init':                        handleInitEvent,
    'phase':                       handlePhaseEvent,
    'intake-progress':             handleIntakeProgressEvent,
    'stories':                     handleStoriesEvent,
    'scouts':                      handleScoutsEvent,
    'agents':                      handleAgentsEvent,
    'logs':                        handleLogsEvent,
    'subagent':                    handleSubagentEvent,
    'subagent-idle':               handleSubagentIdleEvent,
    'pipeline-end':                handlePipelineEndEvent,
    'ask':                         handleAskEvent,
    'model-config':                handleModelConfigEvent,
    'model-config-confirmed':      handleModelConfigConfirmedEvent,
    'ask-cancelled':               handleAskCancelledEvent,
    'artifact-review':             handleArtifactReviewEvent,
    'artifact-review-cancelled':   handleArtifactReviewCancelledEvent,
    'frozen-logs':                 handleFrozenLogsEvent,
    'workflow-decision':           handleWorkflowDecisionEvent,
    'workflow-decision-cancelled': handleWorkflowDecisionCancelledEvent,
    'artifacts':                   handleArtifactsEvent,
    'notification':                handleNotificationEvent,
    'token-delta':                 handleTokenDeltaEvent,
    'token-clear':                 handleTokenClearEvent,
  }

  for (const [event, handler] of Object.entries(handlers)) {
    es.addEventListener(event, (e) => {
      try { handler(JSON.parse(e.data)) }
      catch (err) { console.error(`[koan] SSE "${event}":`, err) }
    })
  }

  es.onerror = () => handleConnectionError()

  return es
}
