import './sections.css'

const DIFFICULTY_BADGE = {
  Beginner: 'badge-green',
  Intermediate: 'badge-orange',
  Advanced: 'badge-accent',
}

export default function StarterTasks({ data }) {
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Starter Tasks</h2>
        <p>Good first issues to tackle when joining this project.</p>
      </div>

      <div className="card-grid">
        {data.map(task => (
          <div key={task.id} className="card">
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
              <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-h)', lineHeight: 1.4 }}>{task.title}</span>
              <span className={`badge ${DIFFICULTY_BADGE[task.difficulty] ?? 'badge-neutral'}`} style={{ flexShrink: 0 }}>
                {task.difficulty}
              </span>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.65, margin: '0 0 12px' }}>
              {task.description}
            </p>
            <span className="badge badge-neutral">👤 {task.owner}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
