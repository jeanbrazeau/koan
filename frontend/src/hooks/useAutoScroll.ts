import { useEffect, RefObject } from 'react'

// useAutoScroll scrolls the referenced element to the bottom after every
// render of the calling component, but only if the user is already near the
// bottom. This preserves intentional scroll position when the user scrolls up
// to read earlier entries. Replaces manual scrollTop manipulation in koan.js.
export function useAutoScroll(ref: RefObject<HTMLDivElement | null>): void {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40
    if (atBottom) {
      el.scrollTop = el.scrollHeight
    }
  })
}
