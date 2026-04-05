/**
 * ArtifactCard — a file entry in the artifacts sidebar.
 *
 * Shows a colored icon square, filename (truncated), and a
 * last-modified timestamp. "recent" files get a navy icon,
 * "stable" files get a teal icon.
 *
 * Used in: artifacts sidebar.
 */

import './ArtifactCard.css'

interface ArtifactCardProps {
  filename: string
  modifiedAgo: string
  variant?: 'recent' | 'stable'
}

const FileIcon = ({ stroke }: { stroke: string }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke={stroke} strokeWidth="2" />
    <path d="M14 2v6h6" stroke={stroke} strokeWidth="2" />
  </svg>
)

export function ArtifactCard({ filename, modifiedAgo, variant = 'recent' }: ArtifactCardProps) {
  return (
    <div className="ac">
      <span className={`ac-icon ac-icon--${variant}`}>
        <FileIcon stroke={variant === 'recent' ? '#b8b0d0' : '#d0f0e8'} />
      </span>
      <span className="ac-info">
        <span className="ac-filename">{filename}</span>
        <span className="ac-time">{modifiedAgo}</span>
      </span>
    </div>
  )
}

export default ArtifactCard
