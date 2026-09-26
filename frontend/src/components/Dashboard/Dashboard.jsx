import { useState } from 'react'
import ProjectOverview from '../sections/ProjectOverview'
import TechStack from '../sections/TechStack'
import ProjectStructure from '../sections/ProjectStructure'
import ImportantFiles from '../sections/ImportantFiles'
import Architecture from '../sections/Architecture'
import SetupGuide from '../sections/SetupGuide'
import DevWorkflow from '../sections/DevWorkflow'
import StarterTasks from '../sections/StarterTasks'
import './Dashboard.css'

const TABS = [
  { id: 'overview',      label: 'Overview',       Component: ProjectOverview,  dataKey: 'overview' },
  { id: 'techstack',     label: 'Tech Stack',      Component: TechStack,        dataKey: 'techStack' },
  { id: 'structure',     label: 'Structure',       Component: ProjectStructure, dataKey: 'structure' },
  { id: 'files',         label: 'Important Files', Component: ImportantFiles,   dataKey: 'importantFiles' },
  { id: 'architecture',  label: 'Architecture',    Component: Architecture,     dataKey: 'architecture' },
  { id: 'setup',         label: 'Setup Guide',     Component: SetupGuide,       dataKey: 'setupGuide' },
  { id: 'workflow',      label: 'Dev Workflow',    Component: DevWorkflow,      dataKey: 'devWorkflow' },
  { id: 'tasks',         label: 'Starter Tasks',   Component: StarterTasks,     dataKey: 'starterTasks' },
]

export default function Dashboard({ data }) {
  const [activeTab, setActiveTab] = useState('overview')

  const tab = TABS.find(t => t.id === activeTab)
  const ActiveComponent = tab.Component
  const sectionData = data[tab.dataKey]

  return (
    <div className="dashboard-root">
      {/* Repo meta bar */}
      <div className="dashboard-meta">
        <div>
          <div className="dashboard-meta-title">{data.overview.name}</div>
          <div className="dashboard-meta-desc">{data.overview.description}</div>
        </div>
        <div className="dashboard-meta-stats">
          <span className="meta-stat"><span className="meta-stat-icon">★</span>{data.overview.stars}</span>
          <span className="meta-stat"><span className="meta-stat-icon">⑂</span>{data.overview.forks}</span>
          <span className="meta-stat"><span className="meta-stat-icon">◎</span>{data.overview.openIssues}</span>
        </div>
      </div>

      {/* Tab navigation */}
      <nav className="dashboard-tabs" aria-label="Dashboard sections" role="tablist">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            aria-controls={`panel-${t.id}`}
            id={`tab-${t.id}`}
            className={`tab-btn${activeTab === t.id ? ' active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Section content */}
      <main
        id={`panel-${tab.id}`}
        role="tabpanel"
        aria-labelledby={`tab-${tab.id}`}
        className="dashboard-content"
      >
        <ActiveComponent data={sectionData} />
      </main>
    </div>
  )
}
