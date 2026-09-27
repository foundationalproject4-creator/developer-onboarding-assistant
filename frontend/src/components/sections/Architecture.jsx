import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import AnalysisSource from '../common/AnalysisSource'
import './sections.css'

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  fontFamily: 'inherit',
  securityLevel: 'loose',
  // Compact sizing — shrinks node padding, font, and inter-node spacing
  themeVariables: {
    fontSize: '13px',

    // Colours only. The 'neutral' theme fills the canvas and every node box
    // with #ffffff / #eee, which reads as a light block on the dark
    // dashboard. Transparent fills let the panel show --bg through instead;
    // the white stroke and light text keep the shape and labels readable.
    background: 'transparent',
    mainBkg: 'transparent',
    primaryColor: 'transparent',
    secondaryColor: 'transparent',
    tertiaryColor: 'transparent',
    edgeLabelBackground: 'transparent',

    primaryBorderColor: '#ffffff',
    secondaryBorderColor: '#ffffff',
    tertiaryBorderColor: '#ffffff',
    // Node strokes are derived as nodeBorder = border1 in the 'neutral'
    // theme, not from primaryBorderColor, so border1 has to be set too.
    border1: '#ffffff',
    lineColor: '#ffffff',

    primaryTextColor: '#e6edf3',
    secondaryTextColor: '#e6edf3',
    tertiaryTextColor: '#e6edf3',
    textColor: '#e6edf3',
    text: '#e6edf3',
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

export default function Architecture({ data, analysis }) {
  // `data` is the full response object — we need both `architecture` (string)
  // and `architecture_diagram` (Mermaid string)
  const summary = data?.architecture
  const diagram = data?.architecture_diagram

  return (
    <div className="section-root arch-section">
      <div className="section-header">
        <div className="section-title-row">
          <h2>Architecture</h2>
          <AnalysisSource analysis={analysis} field="architecture" />
        </div>
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
          {/* The diagram itself is never LLM-written (ai/diagram.py runs
              deterministically on both paths), so it is labelled separately
              from the summary above. */}
          <AnalysisSource analysis={analysis} field="architecture_diagram" />
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
