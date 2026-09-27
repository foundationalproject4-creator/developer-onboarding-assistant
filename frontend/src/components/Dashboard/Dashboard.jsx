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
  { id: 'overview',     label: 'Overview',        icon: '◉', Component: ProjectOverview,  dataKey: 'overview' },
  { id: 'techstack',    label: 'Tech Stack',       icon: '⬡', Component: TechStack,        dataKey: 'techStack' },
  { id: 'structure',    label: 'Structure',        icon: '❐', Component: ProjectStructure, dataKey: 'structure' },
  { id: 'files',        label: 'Important Files',  icon: '⊞', Component: ImportantFiles,   dataKey: 'importantFiles' },
  { id: 'architecture', label: 'Architecture',     icon: '⬟', Component: Architecture,     dataKey: 'architecture' },
  { id: 'setup',        label: 'Setup Guide',      icon: '▶', Component: SetupGuide,       dataKey: 'setupGuide' },
  { id: 'workflow',     label: 'Dev Workflow',     icon: '⇄', Component: DevWorkflow,      dataKey: 'devWorkflow' },
  { id: 'tasks',        label: 'Starter Tasks',    icon: '✓', Component: StarterTasks,     dataKey: 'starterTasks' },
]

export default function Dashboard({ data }) {
  const [activeTab, setActiveTab] = useState('overview')

  const tab = TABS.find(t => t.id === activeTab)
  const ActiveComponent = tab.Component
  const sectionData = data[tab.dataKey]

  return (
    <div className="dashboard-root">
      {/* ── Repo summary bar ─────────────────────────────────────────────── */}
      <div className="dashboard-repo-bar">
        <div className="dashboard-repo-bar-inner">
          <div className="dashboard-repo-bar-left">
            <div className="dashboard-repo-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="1" width="12" height="14" rx="2" />
                <path d="M5 5h6M5 8h6M5 11h4" />
              </svg>
            </div>
            <div>
              <div className="dashboard-repo-name">{data.overview.name}</div>
              <div className="dashboard-repo-desc">{data.overview.description}</div>
            </div>
          </div>

          <div className="dashboard-repo-stats">
            <span className="dashboard-stat" aria-label={`${data.overview.stars} stars`}>
              <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 11.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/></svg>
              {data.overview.stars}
            </span>
            <span className="dashboard-stat" aria-label={`${data.overview.forks} forks`}>
              <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"/></svg>
              {data.overview.forks}
            </span>
            <span className="dashboard-stat dashboard-stat--issues" aria-label={`${data.overview.openIssues} open issues`}>
              <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z"/><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z"/></svg>
              {data.overview.openIssues} issues
            </span>
            <span className="dashboard-stat dashboard-stat--lang">
              <span className="dashboard-stat-dot" aria-hidden="true" />
              {data.overview.language}
            </span>
            <span className="dashboard-stat dashboard-stat--license">
              {data.overview.license}
            </span>
          </div>
        </div>
      </div>

      {/* ── Tab navigation ──────────────────────────────────────────────── */}
      <nav
        className="dashboard-tabs"
        aria-label="Dashboard sections"
        role="tablist"
      >
        <div className="dashboard-tabs-inner">
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
        </div>
      </nav>

      {/* ── Section content ──────────────────────────────────────────────── */}
      <main
        id={`panel-${tab.id}`}
        role="tabpanel"
        aria-labelledby={`tab-${tab.id}`}
        className="dashboard-content"
      >
        <div className="dashboard-content-inner">
          <ActiveComponent data={sectionData} />
        </div>
      </main>
    </div>
  )
}
