import { useState } from 'react'
import { useArtifactTree } from '../store/selectors'
import { ArtifactFile } from '../store/index'
import { formatSize } from '../utils'
import * as api from '../api/client'

function ArtifactOverlay({
  displayPath,
  content,
  onClose,
}: {
  displayPath: string
  content: string
  onClose: () => void
}) {
  const filename = displayPath.split('/').pop() ?? displayPath

  return (
    <div className="artifact-overlay" onClick={onClose}>
      <div className="artifact-overlay-panel" onClick={e => e.stopPropagation()}>
        <div className="artifact-overlay-header">
          <div>
            <div className="artifact-overlay-title">
              {filename}
              <span className="artifact-overlay-readonly-badge">read-only</span>
            </div>
            <div className="artifact-overlay-path">{displayPath}</div>
          </div>
          <button className="settings-btn" onClick={onClose} aria-label="Close">
            &#10005;
          </button>
        </div>
        <div className="artifact-overlay-body">
          <pre>{content}</pre>
        </div>
      </div>
    </div>
  )
}

function FolderNode({
  dir,
  files,
  onFileClick,
}: {
  dir: string
  files: ArtifactFile[]
  onFileClick: (path: string) => void
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className="tree-folder">
      <div className="tree-folder-label" onClick={() => setOpen(v => !v)}>
        {open ? '▾' : '▸'} {dir}/
      </div>
      {open && (
        <div className="tree-children">
          {files.map(f => {
            const filename = f.path.split('/').pop() ?? f.path
            const modTime = new Date(f.modifiedAt).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            })
            return (
              <div
                key={f.path}
                className="tree-file"
                onClick={() => onFileClick(f.path)}
              >
                <span className="tree-file-name">{filename}</span>
                <span className="tree-file-meta">
                  {formatSize(f.size)} — {modTime}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function ArtifactsSidebar() {
  const tree = useArtifactTree()
  const [overlay, setOverlay] = useState<{ displayPath: string; content: string } | null>(null)

  const handleFileClick = async (path: string) => {
    try {
      const data = await api.getArtifactContent(path)
      setOverlay({ displayPath: data.displayPath, content: data.content })
    } catch {
      // ignore fetch errors
    }
  }

  const dirs = Object.keys(tree)

  return (
    <>
      <aside id="artifacts-sidebar" className="artifacts-sidebar">
        <div className="sidebar-heading">Artifacts</div>
        {dirs.length === 0 ? (
          <div className="artifacts-empty">No artifacts yet</div>
        ) : (
          dirs.map(dir => (
            <FolderNode
              key={dir}
              dir={dir}
              files={tree[dir]}
              onFileClick={handleFileClick}
            />
          ))
        )}
      </aside>

      {overlay && (
        <ArtifactOverlay
          displayPath={overlay.displayPath}
          content={overlay.content}
          onClose={() => setOverlay(null)}
        />
      )}
    </>
  )
}
