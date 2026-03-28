import { useMemo } from 'react'
import { useStore, ArtifactFile } from './index'

// Subscribe to the raw scouts Record — reference-stable until setScouts is called.
// Derive the array in the component via useMemo to avoid creating a new array
// on every render (which would trigger useSyncExternalStore's infinite loop).
export function useScoutList() {
  const scouts = useStore(s => s.scouts)
  return useMemo(() => Object.values(scouts), [scouts])
}

// Isolated subscription: StatusSidebar re-renders only when primaryAgent changes.
export const usePrimaryAgent = () => useStore(s => s.primaryAgent)

// Boolean subscription: drives conditional rendering of the interaction overlay
// without subscribing to the full interaction payload.
export const useHasInteraction = () => useStore(s => s.activeInteraction !== null)

function groupByDirectory(artifacts: ArtifactFile[]): Record<string, ArtifactFile[]> {
  const tree: Record<string, ArtifactFile[]> = {}
  for (const a of artifacts) {
    const parts = a.path.split('/')
    const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : 'epic-root'
    if (!tree[dir]) tree[dir] = []
    tree[dir].push(a)
  }
  return tree
}

// Subscribe to the raw artifacts array — reference-stable until setArtifacts is called.
// Derive the tree in the component via useMemo.
export function useArtifactTree() {
  const artifacts = useStore(s => s.artifacts)
  return useMemo(() => groupByDirectory(artifacts), [artifacts])
}
