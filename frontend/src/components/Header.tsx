import { useStore } from '../store/index'
import { PillStrip } from './PillStrip'

export function Header() {
  const run = useStore(s => s.run)
  const setSettingsOpen = useStore(s => s.setSettingsOpen)

  return (
    <header className="header">
      <div className="header-left">
        <span className="logo">koan</span>
        {run && <PillStrip />}
      </div>
      <div className="header-right">
        <button
          className="settings-btn"
          aria-label="Settings"
          onClick={() => setSettingsOpen(true)}
        >
          &#9881;
        </button>
      </div>
    </header>
  )
}
