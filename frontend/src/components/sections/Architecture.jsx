import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import './sections.css'

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  fontFamily: 'inherit',
  securityLevel: 'loose',
  // Compact sizing — shrinks node padding, font, and inter-node spacing
  themeVariables: {
    fontSize: '13px',
  },
  flowchart: {
    nodeSpacing: 30,
    rankSpacing: 40,
    padding: 10,
    useMaxWidth: true,
  },
  graph: {
    nodeSpacing: 30,
    rankSpacing: 40,
    padding: 10,
  },
})

let diagramCounter = 0

function MermaidDiagram({ definition }) {
  const containerRef = useRef(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!definition || !containerRef.current) return

    let cancelled = false
    const id = `mermaid-diag-${++diagramCounter}`

    console.log('MERMAID DATA:', definition)
    mermaid.render(id, definition)
      .then(({ svg }) => {
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg
          const svgEl = containerRef.current.querySelector('svg')
          if (svgEl) {
            // Let the SVG scale down to fit but never stretch beyond its
            // natural rendered width — avoids the bloated full-width look.
            svgEl.removeAttribute('width')
            svgEl.removeAttribute('height')
            svgEl.style.maxWidth = '100%'
            svgEl.style.height = 'auto'
            svgEl.style.display = 'block'
            svgEl.style.margin = '0 auto'
          }
        }
      })
      .catch(err => {
        if (!cancelled) setError(err?.message ?? 'Failed to render diagram.')
      })

    return () => { cancelled = true }
  }, [definition])

  if (error) {
    return (
      <div className="code-block" style={{ margin: 0 }}>
        <code>{definition}</code>
      </div>
    )
  }

  return <div ref={containerRef} className="arch-mermaid-canvas" />
}

export default function Architecture({ data }) {
  // `data` is the full response object — we need both `architecture` (string)
  // and `architecture_diagram` (Mermaid string)
  const summary = data?.architecture
  const diagram = data?.architecture_diagram

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Architecture</h2>
        <p>High-level system design and component responsibilities.</p>
      </div>

      {/* Summary */}
      {summary && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.75, margin: 0, whiteSpace: 'pre-wrap' }}>
            {summary}
          </p>
        </div>
      )}

      {/* Mermaid diagram */}
      {diagram && (
        <div className="arch-diagram-wrap">
          <MermaidDiagram definition={diagram} />
        </div>
      )}

      {!summary && !diagram && (
        <div className="card">
          <p style={{ color: 'var(--text-muted)', margin: 0 }}>No architecture information available.</p>
        </div>
      )}
    </div>
  )
}
