import AnalysisSource from '../common/AnalysisSource'
import './sections.css'

export default function StarterTasks({ data, analysis }) {
  // `data` is List[str] — each string is a suggested starter task description
  return (
    <div className="section-root starter-tasks">
      <div className="section-header">
        <div className="section-title-row">
          <h2>Starter Tasks</h2>
          <AnalysisSource analysis={analysis} field="starter_tasks" />
        </div>
        <p>Good first issues to tackle when joining this project.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(data ?? []).map((task, i) => (
          <div key={i} className="card task-card">
            <div className="task-card-header">
              <span className="task-card-title">{`Task ${i + 1}`}</span>
              <span className="badge badge-neutral" style={{ flexShrink: 0 }}>
                Suggested
              </span>
            </div>
            <p className="task-card-desc" style={{ whiteSpace: 'pre-wrap' }}>{task}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
