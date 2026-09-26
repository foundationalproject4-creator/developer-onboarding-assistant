"""
Deterministic Mermaid diagram generation.

This is intentionally NOT left to the LLM: architecture diagrams are exactly
the kind of thing that's easy for a model to hallucinate connections for.
Instead we detect known signals (frameworks / dependency names) and only draw
nodes and edges we have evidence for. If nothing is detected, we say so
in the diagram itself rather than drawing a generic "example" diagram.
"""

from __future__ import annotations

from typing import List

from .schemas import RepoAnalysis

FRONTEND_SIGNALS = {
    "react", "vue", "angular", "next.js", "nextjs", "svelte", "nuxt", "vite",
}
BACKEND_SIGNALS = {
    "fastapi", "django", "flask", "express", "express.js", "spring", "spring boot",
    "nestjs", "rails", "gin", "asp.net",
}
DATABASE_SIGNALS = {
    "postgres", "postgresql", "mysql", "sqlite", "mongodb", "mongo", "redis",
    "cassandra", "dynamodb", "mariadb", "sqlalchemy", "prisma",
}
EXTERNAL_SERVICE_SIGNALS = {
    "stripe", "twilio", "aws", "boto3", "s3", "sendgrid", "firebase",
    "auth0", "openai", "anthropic", "kafka", "rabbitmq", "sentry",
}


def _normalize_names(analysis: RepoAnalysis) -> List[str]:
    names: List[str] = []
    names.extend(f.lower() for f in analysis.frameworks)
    for dep in analysis.dependencies:
        name = dep if isinstance(dep, str) else dep.name
        names.append(name.lower())
    return names


def generate_architecture_diagram(analysis: RepoAnalysis) -> str:
    names = _normalize_names(analysis)

    has_frontend = any(any(sig in n for sig in FRONTEND_SIGNALS) for n in names)
    has_backend = any(any(sig in n for sig in BACKEND_SIGNALS) for n in names)
    has_db = any(any(sig in n for sig in DATABASE_SIGNALS) for n in names)
    detected_services = sorted({
        sig for n in names for sig in EXTERNAL_SERVICE_SIGNALS if sig in n
    })

    lines = ["graph TD"]
    nodes_added = False

    if has_frontend:
        lines.append('    Frontend["Frontend"]')
        nodes_added = True
    if has_backend:
        lines.append('    Backend["Backend / API"]')
        nodes_added = True
    if has_db:
        lines.append('    Database[("Database")]')
        nodes_added = True
    for svc in detected_services:
        node_id = "Ext_" + svc.replace(".", "_").replace(" ", "_").title()
        lines.append(f'    {node_id}["{svc.title()}"]')
        nodes_added = True

    if has_frontend and has_backend:
        lines.append("    Frontend --> Backend")
    if has_backend and has_db:
        lines.append("    Backend --> Database")
    for svc in detected_services:
        node_id = "Ext_" + svc.replace(".", "_").replace(" ", "_").title()
        if has_backend:
            lines.append(f"    Backend --> {node_id}")

    if not nodes_added:
        # No detectable signals — be honest instead of drawing a fake diagram.
        lines.append('    Unknown["Architecture not determinable from available data"]')

    return "\n".join(lines)
