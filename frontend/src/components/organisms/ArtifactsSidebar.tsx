/**
 * ArtifactsSidebar — right-side panel listing spec artifacts.
 *
 * Fixed 240px column beside the main content stream. Shows a section
 * label, a list of ArtifactCard molecules, or an empty-state message
 * when no artifacts exist.
 *
 * Used in: workspace layout, right column.
 */

import { SectionLabel } from '../atoms/SectionLabel'
import { ArtifactCard } from '../molecules/ArtifactCard'
import './ArtifactsSidebar.css'

interface ArtifactEntry {
  filename: string
  modifiedAgo: string
  variant?: 'recent' | 'stable'
}

interface ArtifactsSidebarProps {
  artifacts: ArtifactEntry[]
}

export function ArtifactsSidebar({ artifacts }: ArtifactsSidebarProps) {
  return (
    <aside className="asb">
      <div className="asb-header">
        <SectionLabel>Artifacts</SectionLabel>
      </div>
      {artifacts.length === 0 ? (
        <div className="asb-empty">No artifacts yet</div>
      ) : (
        <div className="asb-list">
          {artifacts.map((a, i) => (
            <ArtifactCard
              key={i}
              filename={a.filename}
              modifiedAgo={a.modifiedAgo}
              variant={a.variant}
            />
          ))}
        </div>
      )}
    </aside>
  )
}

export default ArtifactsSidebar
