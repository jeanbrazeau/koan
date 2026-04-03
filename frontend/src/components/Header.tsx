import { useStore } from '../store/index'

export function Header() {
  const setSettingsOpen = useStore(s => s.setSettingsOpen)

  return (
    <header className="header">
      <div className="header-left">
        <span className="logo">koan</span>
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
