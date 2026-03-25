// Lightweight markdown rendering for LLM-generated content.
// Block mode (<Md>) for multi-paragraph text (context, descriptions).
// Inline mode (<MdInline>) for single-line text (labels, options, headings).
//
// Usage:
//   <Md text={question.context} class="question-context" />
//   <MdInline text={optionLabel} />

import { marked } from 'marked'

/** Block markdown — renders <p>, <ul>, <code>, <strong>, etc. */
export function Md({ text, class: className }) {
  if (!text) return null
  return <div class={className} dangerouslySetInnerHTML={{ __html: marked.parse(text) }} />
}

/** Inline markdown — renders **bold**, `code`, *italic*, [links] without wrapping <p>. */
export function MdInline({ text, class: className }) {
  if (!text) return null
  return <span class={className} dangerouslySetInnerHTML={{ __html: marked.parseInline(text) }} />
}
