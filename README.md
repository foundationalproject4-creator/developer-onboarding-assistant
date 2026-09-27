# Developer Onboarding Assistant

> **AI-powered repository analysis that turns an unfamiliar codebase into an interactive developer onboarding guide.**

## 🚀 Overview

Joining an unfamiliar software project can be difficult. Developers often spend hours exploring folders, understanding the architecture, identifying important files, finding dependencies, and figuring out how to run the project.

**Developer Onboarding Assistant** analyzes a GitHub repository and automatically generates an interactive onboarding guide.

Instead of manually exploring a repository, a developer can provide a repository URL and receive a structured view of the project.

## ✨ Features

* 🔍 **Repository Analysis** — analyzes the structure and contents of a repository
* 🧠 **AI-Powered Analysis** — generates meaningful project insights when an LLM is available
* 🛡️ **Rule-Based Fallback** — continues working even when an LLM is unavailable
* 💻 **Technology Detection** — identifies languages, frameworks, and technologies
* 📁 **Important Files** — highlights files that are useful for understanding the project
* 🏗️ **Architecture Visualization** — generates a visual architecture diagram
* ⚙️ **Setup Guide** — provides repository setup information
* 🔄 **Development Workflow** — derives steps for installing and running the project
* 📦 **Dependency Analysis** — identifies project dependencies
* 🎯 **Starter Tasks** — helps new developers get started with the codebase

## 🏗️ Architecture

```text
GitHub Repository
       │
       ▼
Repository Analyzer
       │
       ▼
Structured Repository Data
       │
       ▼
AI Analysis / Rule-Based Fallback
       │
       ▼
FastAPI Backend
       │
       ▼
React Frontend
       │
       ▼
Interactive Onboarding Dashboard
```

## 🛠️ Tech Stack

### Frontend

* React
* Vite
* JavaScript
* CSS
* Mermaid

### Backend

* Python
* FastAPI
* Uvicorn

### AI Layer

* Anthropic API
* Rule-based fallback analysis

### Repository Analysis

* Repository structure analysis
* Language and dependency detection
* Important-file detection

## 📂 Project Structure

```text
developer-onboarding-assistant/
│
├── ai/
│   ├── generator.py
│   ├── schemas.py
│   ├── prompts.py
│   ├── llm_client.py
│   └── diagram.py
│
├── analyzer/
│   └── Repository analysis components
│
├── backend/
│   ├── main.py
│   └── analyzer_adapter.py
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── bob_sessions/
│   └── Development evidence
│
└── README.md
```

## ⚙️ Getting Started

### Prerequisites

Make sure you have:

* Python 3.12+
* Node.js
* npm
* Git

### 1. Clone the repository

```bash
git clone https://github.com/foundationalproject4-creator/developer-onboarding-assistant.git
cd developer-onboarding-assistant
```

### 2. Set up the backend

Create and activate a Python virtual environment:

```bash
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the backend dependencies according to the project's requirements file.

### 3. Start the backend

From the project root:

```bash
uvicorn backend.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### 4. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local Vite URL shown in the terminal.

## 🔑 AI Configuration

The project supports an AI-powered analysis path using the Anthropic API.

Create a `.env` file and add:

```env
ANTHROPIC_API_KEY=your_api_key_here
```

**Never commit your `.env` file or API keys to GitHub.**

If an LLM is unavailable, the application uses its **rule-based fallback analysis** so that repository analysis can still be demonstrated.

## 🔄 How It Works

1. User enters a GitHub repository URL.
2. Backend validates the repository URL.
3. The repository is cloned temporarily for analysis.
4. The Repository Analyzer detects project information.
5. Analyzer output is converted into a structured analysis model.
6. The AI layer generates onboarding information when available.
7. If the LLM is unavailable, the rule-based fallback generates grounded results.
8. FastAPI returns the structured onboarding data.
9. React displays the results as an interactive dashboard.

## 🧩 Generated Onboarding Sections

The dashboard provides:

| Section         | Purpose                                    |
| --------------- | ------------------------------------------ |
| Overview        | High-level project summary                 |
| Tech Stack      | Detected technologies                      |
| Important Files | Files useful for understanding the project |
| Architecture    | Visual project architecture                |
| Setup Guide     | Setup and installation information         |
| Dev Workflow    | Development/run workflow                   |
| Starter Tasks   | Suggested tasks for new developers         |
| Dependencies    | Project dependencies                       |

## 🛡️ Grounded Analysis

A key design principle is **not inventing repository information**.

The analysis is based on information detected from the repository, such as:

* Project structure
* Languages
* Frameworks
* Dependencies
* Important files
* Entry points
* Configuration files

When the AI/LLM is unavailable, the deterministic fallback provides repository-grounded information instead of fabricating project functionality.

## 🎯 Problem We Solve

New developers joining an existing project commonly face questions such as:

* What does this project do?
* Where should I start?
* Which files are important?
* What technologies are being used?
* How are the components connected?
* How do I run the project?
* What could I work on first?

The Developer Onboarding Assistant brings these answers together in one place.

## 👥 Team

**Developer Onboarding Assistant — IBM Bob 2.0 Hackathon**

Team members:

* Mayank — Frontend
* Kushal — Backend & Integration
* Radhika — AI & Architecture
* Siri — Integration & Testing
* Meith — Repository Analyzer

## 🚧 Current Status

The project currently supports:

* Repository URL analysis
* Repository structure detection
* Technology detection
* Important-file detection
* Dependency analysis
* AI/fallback onboarding generation
* Architecture visualization
* Interactive React dashboard
* FastAPI backend
* Automated backend tests

## 🔮 Future Improvements

* More accurate semantic repository understanding
* Improved onboarding task recommendations
* Code-level dependency graphs
* Interactive architecture exploration
* Pull-request and issue-based onboarding
* Support for additional repository platforms
* Persistent analysis history
* More detailed AI-generated developer guidance

## 📜 License

This project was created as a hackathon project.
