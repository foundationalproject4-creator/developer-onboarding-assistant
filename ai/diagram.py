"""
Deterministic Mermaid diagram generation.

This is intentionally NOT left to the LLM: architecture diagrams are exactly
the kind of thing that's easy for a model to hallucinate connections for.
Instead we detect known signals (frameworks / dependency names) and only draw
nodes and edges we have evidence for. If nothing is detected, we say so
in the diagram itself rather than drawing a generic "example" diagram.

Signal set maintenance
----------------------
Add new entries to the sets below when a stack starts appearing in repos and
is being silently missed (diagram shows "Architecture not determinable…").
Guidelines:
- Use the lowercase pip/npm package name OR the common framework name as it
  would appear in ``frameworks`` or ``dependencies`` of a RepoAnalysis.
- Keep entries short — substring matching is used, so "remix" matches both
  "remix" and "@remix-run/react".
- Do NOT add very generic words that appear in non-framework dep names.
"""

from __future__ import annotations

from typing import List

from .schemas import RepoAnalysis

FRONTEND_SIGNALS = {
    # React ecosystem
    "react", "next.js", "nextjs", "next",
    # Vue ecosystem
    "vue", "nuxt",
    # Svelte / SvelteKit
    "svelte", "sveltekit", "@sveltejs",
    # Remix
    "remix", "@remix-run",
    # Angular
    "angular", "@angular",
    # Other popular frontend frameworks / build tools
    "vite", "gatsby", "astro", "solid", "qwik",
    # Older / still-common
    "ember", "backbone", "knockout",
}

BACKEND_SIGNALS = {
    # Python
    "fastapi", "django", "flask", "starlette", "tornado", "aiohttp", "falcon",
    # Node.js
    "express", "express.js", "koa", "hapi", "@hapi",
    # NestJS (Node + TypeScript)
    "nestjs", "@nestjs",
    # Java / JVM
    "spring", "spring boot", "quarkus", "micronaut", "ktor",
    # Go
    "gin", "echo", "fiber", "gorilla",
    # Ruby
    "rails", "sinatra",
    # .NET
    "asp.net", "aspnetcore",
    # PHP
    "laravel", "symfony",
    # Rust
    "actix", "axum", "rocket",
    # Django REST Framework (often listed as a dep alongside django)
    "djangorestframework", "rest_framework",
}

DATABASE_SIGNALS = {
    # Relational
    "postgres", "postgresql", "mysql", "sqlite", "mariadb", "mssql",
    # NoSQL
    "mongodb", "mongo", "cassandra", "couchdb", "neo4j", "arangodb",
    # Key-value / cache (also appears as a service)
    "redis",
    # Cloud-managed
    "dynamodb", "firestore", "cosmosdb", "bigtable", "spanner",
    # ORMs / query builders (signal a DB is present)
    "sqlalchemy", "alembic", "prisma", "typeorm", "sequelize", "knex",
    "gorm", "hibernate", "jpa", "drizzle",
}

EXTERNAL_SERVICE_SIGNALS = {
    # AI / LLM
    "openai", "anthropic", "cohere", "huggingface", "langchain", "llamaindex",
    # Payment
    "stripe", "braintree", "paypal",
    # Communication
    "twilio", "sendgrid", "mailgun", "postmark", "resend",
    # Auth
    "auth0", "okta", "clerk", "supabase",
    # Cloud providers
    "aws", "boto3", "s3", "gcp", "google-cloud", "azure",
    # Observability
    "sentry", "datadog", "newrelic", "honeycomb",
    # Messaging
    "kafka", "rabbitmq", "celery", "rq", "sidekiq", "bull",
    # Storage / CDN
    "firebase", "cloudinary", "imgix",
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
        node_id = "Ext_" + svc.replace(".", "_").replace(" ", "_").replace("-", "_").replace("@", "").title()
        lines.append(f'    {node_id}["{svc.title()}"]')
        nodes_added = True

    if has_frontend and has_backend:
        lines.append("    Frontend --> Backend")
    if has_backend and has_db:
        lines.append("    Backend --> Database")
    for svc in detected_services:
        node_id = "Ext_" + svc.replace(".", "_").replace(" ", "_").replace("-", "_").replace("@", "").title()
        if has_backend:
            lines.append(f"    Backend --> {node_id}")

    if not nodes_added:
        # No detectable signals — be honest instead of drawing a fake diagram.
        lines.append('    Unknown["Architecture not determinable from available data"]')

    return "\n".join(lines)
