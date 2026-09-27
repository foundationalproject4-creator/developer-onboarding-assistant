/**
 * Mock onboarding data — shaped to match the future FastAPI response schema.
 *
 * API base URL is read from the VITE_API_URL environment variable.
 * Set it in frontend/.env.local for local dev, and in the Vercel dashboard
 * for production — never hardcode a URL here.
 *
 *   # frontend/.env.local
 *   VITE_API_URL=http://localhost:8000
 *
 *   # Vercel dashboard → Environment Variables
 *   VITE_API_URL=https://your-app.onrender.com
 */

// Vite exposes env vars prefixed with VITE_ via import.meta.env.
// Falls back to empty string when not set — triggers mock path below.
const API_BASE = import.meta.env.VITE_API_URL ?? ''
export const MOCK_ONBOARDING_DATA = {
  overview: {
    name: 'developer-onboarding-assistant',
    description:
      'An AI-powered tool that analyzes unfamiliar repositories and generates structured onboarding guides for developers — covering architecture, setup, workflows, and starter tasks.',
    language: 'Python',
    license: 'MIT',
    stars: 42,
    forks: 7,
    openIssues: 3,
    lastUpdated: '2025-07-10',
    topics: ['ai', 'developer-tools', 'onboarding', 'fastapi', 'react'],
  },

  techStack: [
    { name: 'React 19', category: 'Frontend', version: '19.2.8', description: 'UI component library for building the onboarding dashboard.' },
    { name: 'Vite', category: 'Build Tool', version: '8.3.0', description: 'Fast development server and bundler for the React frontend.' },
    { name: 'FastAPI', category: 'Backend', version: '0.115', description: 'High-performance Python web framework powering the REST API.' },
    { name: 'Python', category: 'Language', version: '3.11+', description: 'Primary language for the backend, analyzer, and AI integration.' },
    { name: 'Uvicorn', category: 'Server', version: '0.32', description: 'ASGI server running the FastAPI application.' },
    { name: 'GitPython', category: 'Analyzer', version: '3.1', description: 'Python library used to clone and traverse repository structure.' },
    { name: 'Anthropic Claude', category: 'AI', version: 'claude-sonnet-4-6', description: 'LLM API used to generate onboarding content from repository analysis.' },
    { name: 'CSS Custom Properties', category: 'Styling', version: 'native', description: 'Token-based design system with dark mode support.' },
  ],

  structure: {
    name: 'developer-onboarding-assistant',
    type: 'directory',
    children: [
      {
        name: 'frontend/', type: 'directory', children: [
          { name: 'src/', type: 'directory', children: [
            { name: 'components/', type: 'directory' },
            { name: 'data/', type: 'directory' },
            { name: 'App.jsx', type: 'file' },
            { name: 'main.jsx', type: 'file' },
            { name: 'index.css', type: 'file' },
          ]},
          { name: 'index.html', type: 'file' },
          { name: 'vite.config.js', type: 'file' },
          { name: 'package.json', type: 'file' },
        ],
      },
      {
        name: 'backend/', type: 'directory', children: [
          { name: 'main.py', type: 'file' },
          { name: 'routes/', type: 'directory' },
          { name: 'models/', type: 'directory' },
          { name: 'requirements.txt', type: 'file' },
        ],
      },
      {
        name: 'analyzer/', type: 'directory', children: [
          { name: 'repo_analyzer.py', type: 'file' },
          { name: 'structure_parser.py', type: 'file' },
        ],
      },
      { name: 'docs/', type: 'directory' },
      { name: 'README.md', type: 'file' },
      { name: '.gitignore', type: 'file' },
    ],
  },

  importantFiles: [
    { path: 'backend/main.py', role: 'API Entry Point', description: 'FastAPI application instance and router registration. Start here to understand all available endpoints.' },
    { path: 'analyzer/repo_analyzer.py', role: 'Core Analyzer', description: 'Orchestrates repository cloning, file traversal, and data extraction passed to the AI layer.' },
    { path: 'frontend/src/App.jsx', role: 'Frontend Root', description: 'Main React component managing app state: idle → loading → dashboard. Start here for frontend flow.' },
    { path: 'frontend/src/data/mockData.js', role: 'Mock API Contract', description: 'Defines the exact shape of the API response. Use this as the contract when building the real backend response.' },
    { path: 'frontend/vite.config.js', role: 'Build Config', description: 'Vite configuration. Add proxy rules here to forward /api calls to the FastAPI backend during development.' },
    { path: 'backend/requirements.txt', role: 'Python Dependencies', description: 'All Python package requirements. Run pip install -r requirements.txt to set up the backend environment.' },
    { path: 'README.md', role: 'Project Root', description: 'Top-level project documentation. Contains team structure, setup instructions, and development workflow.' },
  ],

  architecture: {
    summary:
      'Three-tier architecture: a React frontend, a FastAPI backend, and a Python analyzer layer. The frontend submits a repository URL; the backend orchestrates analysis and AI generation; the analyzer clones and parses the repository; Anthropic Claude produces the natural-language content.',
    diagram: `
┌─────────────────────────────────────────────────────┐
│                    Browser (React)                   │
│  RepoInput ──▶ Dashboard ──▶ 8 Section Components   │
└───────────────────────┬─────────────────────────────┘
                        │ POST /api/analyze
                        ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                     │
│  /analyze endpoint ──▶ Analyzer ──▶ AI Generator    │
└────────────┬──────────────────────┬─────────────────┘
             │                      │
             ▼                      ▼
    Git Repository           Anthropic Claude
    (clone + parse)        (content generation)
`,
    components: [
      { name: 'React Frontend', responsibility: 'User interface, state management, section rendering' },
      { name: 'FastAPI Backend', responsibility: 'REST API, request validation, orchestration' },
      { name: 'Repository Analyzer', responsibility: 'Git clone, file tree traversal, dependency extraction' },
      { name: 'Anthropic Claude', responsibility: 'LLM-based generation of all onboarding text content' },
    ],
  },

  setupGuide: [
    {
      step: 1, title: 'Clone the repository',
      commands: ['git clone https://github.com/your-org/developer-onboarding-assistant.git', 'cd developer-onboarding-assistant'],
    },
    {
      step: 2, title: 'Set up the Python backend',
      commands: ['cd backend', 'python -m venv venv', 'venv\\Scripts\\activate  # Windows', 'pip install -r requirements.txt'],
    },
    {
      step: 3, title: 'Configure environment variables',
      commands: ['cp .env.example .env', '# Edit .env and set ANTHROPIC_API_KEY to enable the LLM path'],
    },
    {
      step: 4, title: 'Start the FastAPI backend',
      commands: ['uvicorn main:app --reload --port 8000'],
    },
    {
      step: 5, title: 'Set up and start the frontend',
      commands: ['cd ../frontend', 'npm install', 'npm run dev'],
    },
    {
      step: 6, title: 'Open the app',
      commands: ['# Visit http://localhost:5173 in your browser'],
    },
  ],

  devWorkflow: {
    summary: 'Git-flow branching model. Feature branches off main, PRs required before merging. Each team member owns a vertical slice.',
    steps: [
      { step: 1, title: 'Create a feature branch', detail: 'Branch from main using the pattern feature/<your-name>/<feature-name>' },
      { step: 2, title: 'Develop your feature', detail: 'Make atomic commits with clear messages. Prefix: feat:, fix:, docs:, chore:' },
      { step: 3, title: 'Test locally', detail: 'Run the frontend (npm run dev) and backend (uvicorn) together. Test your endpoint or component end-to-end.' },
      { step: 4, title: 'Open a Pull Request', detail: 'PRs must include a description of changes and must not break existing endpoints or components.' },
      { step: 5, title: 'Code review', detail: 'At least one other team member reviews before merging. Use GitHub review comments.' },
      { step: 6, title: 'Merge to main', detail: 'Squash-merge into main after approval. Delete the feature branch.' },
    ],
    conventions: [
      'Frontend lives in frontend/, backend in backend/, analyzer in analyzer/.',
      'Do not commit .env files or API keys.',
      'Use npm run lint before pushing frontend changes.',
      'Keep mock data in sync with real API schema changes.',
    ],
  },

  starterTasks: [
    { id: 1, title: 'Connect frontend to real API', difficulty: 'Intermediate', description: 'Replace the mock fetch in App.jsx with a real POST to /api/analyze. Handle loading and error states from the live response.', owner: 'Frontend' },
    { id: 2, title: 'Add copy-to-clipboard for code blocks', difficulty: 'Beginner', description: 'In SetupGuide, add a small copy button on each command block. Show a "Copied!" confirmation for 2 seconds.', owner: 'Frontend' },
    { id: 3, title: 'Implement /api/analyze endpoint', difficulty: 'Intermediate', description: 'Wire up the FastAPI route to accept a repo URL, call the analyzer, and return the onboarding JSON matching mockData.js schema.', owner: 'Backend' },
    { id: 4, title: 'Add error handling UI', difficulty: 'Beginner', description: 'Show a clear error message when the API returns a non-200 response. Allow the user to retry from the same input.', owner: 'Frontend' },
    { id: 5, title: 'Persist last result to localStorage', difficulty: 'Beginner', description: 'Save the last successful onboarding result to localStorage so it survives a page refresh.', owner: 'Frontend' },
    { id: 6, title: 'Write analyzer unit tests', difficulty: 'Intermediate', description: 'Add pytest tests for repo_analyzer.py covering file tree traversal and dependency extraction edge cases.', owner: 'Analyzer' },
    { id: 7, title: 'Add repo URL validation on backend', difficulty: 'Beginner', description: 'Validate that the submitted URL is a valid GitHub or GitLab URL before attempting to clone.', owner: 'Backend' },
    { id: 8, title: 'Add dark/light mode toggle', difficulty: 'Beginner', description: 'Add a toggle button to the header that switches between dark and light mode. The CSS custom properties are already set up in index.css.', owner: 'Frontend' },
  ],
}

/**
 * Validates that a URL looks like a real owner/repo path on a supported host.
 * Used by fetchOnboardingData to gate the mock response.
 */
const VALID_REPO_URL = /^https?:\/\/(github\.com|gitlab\.com|bitbucket\.org)\/([^\s/]+)\/([^\s/]+?)\/?$/i

function validateRepoUrl(url) {
  if (!url || !url.trim()) {
    throw new Error('Please enter a repository URL.')
  }
  const match = VALID_REPO_URL.exec(url.trim())
  if (!match) {
    throw new Error(
      'Invalid repository URL. Expected format: https://github.com/owner/repository'
    )
  }
  const [, , owner, repo] = match
  // Reject obviously placeholder-looking values
  if (owner.length < 1 || repo.length < 1) {
    throw new Error('Repository URL must include both an owner and a repository name.')
  }
}

/**
 * Fetch onboarding data for a repository URL.
 *
 * Live path  — used when VITE_API_URL is set (staging / production).
 *   POST {VITE_API_URL}/analyze  → { repo_path: repoUrl }
 *
 * Mock path  — used when VITE_API_URL is not set (local UI development).
 *   Returns MOCK_ONBOARDING_DATA after a simulated delay.
 */
export async function fetchOnboardingData(repoUrl) {
  // Validate first — throws immediately, before any network call
  validateRepoUrl(repoUrl)

  if (API_BASE) {
    // ── Live path ─────────────────────────────────────────────────────────
    const response = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: repoUrl }),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body?.detail ?? `Server error ${response.status}`)
    }
    return response.json()
  }

  // ── Mock path (no VITE_API_URL set) ─────────────────────────────────────
  await new Promise(resolve => setTimeout(resolve, 2800))
  return MOCK_ONBOARDING_DATA
}
