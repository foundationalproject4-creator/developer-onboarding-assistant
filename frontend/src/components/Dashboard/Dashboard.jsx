import { useState } from 'react'
import ProjectOverview from '../sections/ProjectOverview'
import TechStack from '../sections/TechStack'
import ImportantFiles from '../sections/ImportantFiles'
import Architecture from '../sections/Architecture'
import SetupGuide from '../sections/SetupGuide'
import DevWorkflow from '../sections/DevWorkflow'
import StarterTasks from '../sections/StarterTasks'
import Dependencies from '../sections/Dependencies'
import './Dashboard.css'

const TABS = [
  { id: 'overview',      label: 'Overview',        icon: '◉', Component: ProjectOverview, dataKey: 'project_overview' },
  { id: 'techstack',     label: 'Tech Stack',       icon: '⬡', Component: TechStack,       dataKey: 'tech_stack' },
  { id: 'files',         label: 'Important Files',  icon: '⊞', Component: ImportantFiles,  dataKey: 'important_files' },
  { id: 'architecture',  label: 'Architecture',     icon: '⬟', Component: Architecture,    dataKey: null },
  { id: 'setup',         label: 'Setup Guide',      icon: '▶', Component: SetupGuide,      dataKey: 'setup_guide' },
  { id: 'workflow',      label: 'Dev Workflow',     icon: '⇄', Component: DevWorkflow,     dataKey: 'development_workflow' },
  { id: 'tasks',         label: 'Starter Tasks',    icon: '✓', Component: StarterTasks,    dataKey: 'starter_tasks' },
  { id: 'dependencies',  label: 'Dependencies',     icon: '⬡', Component: Dependencies,    dataKey: 'dependencies' },
]

export default function Dashboard({ data }) {
  const [activeTab, setActiveTab] = useState('overview')

  const tab = TABS.find(t => t.id === activeTab)
  const ActiveComponent = tab.Component
  // Architecture tab needs both `architecture` string and `architecture_diagram`
  const sectionData = tab.dataKey === null ? data : data[tab.dataKey]

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
              <div className="dashboard-repo-name">Repository Analysis</div>
              <div className="dashboard-repo-desc">
                {data.used_llm ? 'AI-enhanced analysis' : 'Rule-based analysis'}
              </div>
            </div>
          </div>

          <div className="dashboard-repo-stats">
            {data.used_llm && (
              <span className="dashboard-stat dashboard-stat--lang">
                <span className="dashboard-stat-dot" aria-hidden="true" />
                AI-enhanced
              </span>
            )}
            {data.tech_stack?.length > 0 && (
              <span className="dashboard-stat">
                {data.tech_stack.length} technologies
              </span>
            )}
            {data.important_files?.length > 0 && (
              <span className="dashboard-stat">
                {data.important_files.length} key files
              </span>
            )}
            {data.dependencies?.length > 0 && (
              <span className="dashboard-stat dashboard-stat--issues">
                {data.dependencies.length} dependencies
              </span>
            )}
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
          {/* `analysis` is the full OnboardingKnowledge response. It carries
              the provenance fields (used_llm, data_completeness_notes,
              important_files) that trust signals need; `data` stays the
              unchanged per-section payload. */}
          <ActiveComponent data={sectionData} analysis={data} />
        </div>
      </main>
    </div>
  )
}
