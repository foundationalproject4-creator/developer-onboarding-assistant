import './sections.css'

export default function DevWorkflow({ data }) {
  // `data` is List[str] — each string is one workflow step or convention
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Development Workflow</h2>
        <p>How the team works together — branching, commits, and reviews.</p>
      </div>

      <ol className="step-list">
        {(data ?? []).map((item, i) => (
          <li key={i} className="step-item">
            <span className="step-number" aria-hidden="true">{i + 1}</span>
            <div className="step-body">
              <p style={{ margin: 0, fontSize: 14, color: 'var(--text)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {item}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
