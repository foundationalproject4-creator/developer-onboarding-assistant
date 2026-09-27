import './sections.css'

export default function ProjectOverview({ data }) {
  // `data` is the `project_overview` string from the backend
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Project Overview</h2>
        <p>High-level summary of the repository.</p>
      </div>

      <div className="card po-overview-card">
        <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.75, margin: 0 }}>
          {data || 'No overview available.'}
        </p>
      </div>
    </div>
  )
}
