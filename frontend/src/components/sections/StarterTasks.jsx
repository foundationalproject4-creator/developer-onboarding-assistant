import './sections.css'

const DIFFICULTY_BADGE = {
  Beginner:     'badge-green',
  Intermediate: 'badge-orange',
  Advanced:     'badge-accent',
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
          <div key={task.id} className="card task-card">
            <div className="task-card-header">
              <span className="task-card-title">{task.title}</span>
              <span className={`badge ${DIFFICULTY_BADGE[task.difficulty] ?? 'badge-neutral'}`} style={{ flexShrink: 0 }}>
                {task.difficulty}
              </span>
            </div>
            <p className="task-card-desc">{task.description}</p>
            <div className="task-card-footer">
              <span className="task-owner-badge">
                {task.owner}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
