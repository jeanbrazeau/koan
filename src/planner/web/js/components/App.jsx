// Root layout component. Everything lives inside a single centred max-width
// container (.app). The header is a normal flex child (not position:fixed);
// it stays at the top because .app is a flex column with overflow:hidden and
// child areas scroll internally.
//
// Two mutually exclusive content modes below the header:
//
//   Interactive — PhaseContent fills a centred scrollable column. Used for
//                 forms, settings overlay, loading screen, and completion.
//   Live        — StatusSidebar on the left, ActivityFeed on the right.
//
// isInteractive = !phase || pendingInput || showSettings || phase === 'completed'
//
// AgentMonitor and Notifications are always mounted; they manage their own
// visibility via internal selectors.

import { Header } from './Header.jsx'
import { PhaseContent } from './PhaseContent.jsx'
import { ActivityFeed } from './ActivityFeed.jsx'
import { AgentMonitor } from './AgentMonitor.jsx'
import { StatusSidebar } from './StatusSidebar.jsx'
import { Notifications } from './Notifications.jsx'
import { useStore } from '../store.js'

export function App({ token, topic }) {
  const phase = useStore(s => s.phase)
  const pending = useStore(s => s.pendingInput)
  const showSettings = useStore(s => s.showSettings)

  // Interactive mode: forms, settings overlay, loading screen, completion.
  // Live mode: active subagent activity feed with status sidebar.
  const isInteractive = !phase || pending || showSettings || phase === 'completed'

  return (
    <div class="app">
      <Header />
      {isInteractive ? (
        <main class="main-panel">
          <div class="phase-content">
            <PhaseContent token={token} topic={topic} />
          </div>
        </main>
      ) : (
        // Live layout: status sidebar on the left, activity feed on the right.
        <div class="live-layout">
          <StatusSidebar />
          <div class="live-main">
            <main class="main-panel">
              <ActivityFeed />
            </main>
          </div>
        </div>
      )}
      <AgentMonitor />
      <Notifications />
    </div>
  )
}
