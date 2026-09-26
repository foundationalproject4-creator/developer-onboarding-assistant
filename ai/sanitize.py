"""
Pre-send sanitizer for RepoAnalysis payloads.

Before any RepoAnalysis is forwarded to the LLM, ``sanitize_analysis``
strips strings that match common secret/credential patterns.  This is a
best-effort defence-in-depth measure — it is NOT a substitute for access
controls or repo-level secret scanning (e.g. GitHub Advanced Security,
truffleHog, detect-secrets).

What is scrubbed
----------------
1. String values that match high-confidence secret patterns (API keys, tokens,
   private-key PEM headers, AWS-style keys, connection strings with passwords,
   .env KEY=VALUE lines containing credential-like values).
2. File *paths* that are well-known secret-bearing filenames (.env, .pem,
   id_rsa, credentials.json, service_account.json, .netrc, etc.) — the path
   itself is replaced with a redaction marker so the LLM is never shown it.

What is NOT scrubbed
--------------------
- Dependency *names* (e.g. "cryptography") — these are package names, not secrets.
- Project names, language names, framework names — these carry no secrets.
- Legitimate file paths that happen to contain the word "key" (e.g. "src/keygen.py")
  — only exact filename patterns are matched, not substrings in directory names.

Redaction marker
----------------
All redacted values are replaced with the string ``"[REDACTED]"``.

Logging policy
--------------
When a field value is redacted a WARNING is emitted containing:
  - Which field was redacted (e.g. "important_files[2].description")
  - The pattern category that matched (e.g. "api_key_pattern")
  - The first 4 chars of the original value + "…" so a human can identify
    what was matched without reconstructing the secret.

The original value is NEVER logged in full.

Design note: why not raise an error?
-------------------------------------
Raising a validation error on suspected secrets would break the fallback path
too (which does not call the LLM but would still be blocked).  A warning +
redaction keeps the system functional while making the event visible.  A
stricter policy (hard reject) can be enforced at the infrastructure layer
(e.g. a WAF rule, or by checking ``data_completeness_notes`` for redaction
markers in the response).
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import List, Union

from .schemas import DependencyEntry, ImportantFileEntry, RepoAnalysis

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redaction marker (also stored in data_completeness_notes so callers know)
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"

# ---------------------------------------------------------------------------
# Secret-value patterns
# ---------------------------------------------------------------------------
# Each pattern is tried against individual string values (not the whole JSON).
# Patterns are ordered from most-specific to least-specific.

_SECRET_VALUE_PATTERNS: List[tuple[str, re.Pattern]] = [
    # Anthropic API keys  sk-ant-api03-...
    ("anthropic_api_key", re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{40,}", re.I)),
    # OpenAI API keys  sk-... (20+ chars after sk-)
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9]{20,}", re.I)),
    # Generic bearer / API token header values
    ("bearer_token", re.compile(r"(?:bearer\s+|token[=:\s]+)[A-Za-z0-9+/=_\-]{20,}", re.I)),
    # AWS Access Key ID  AKIA...
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    # AWS Secret Access Key (40 base64 chars after assignment)
    ("aws_secret_key", re.compile(r"(?:aws_secret_access_key|AWS_SECRET)[=:\s]+[A-Za-z0-9+/]{40}", re.I)),
    # GitHub personal access tokens  ghp_... / ghs_... / github_pat_...
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}", re.I)),
    # Generic hex token (32+ hex chars — covers MD5/SHA-style tokens)
    ("hex_token", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
    # Private key PEM header
    ("pem_private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I)),
    # Connection strings with embedded passwords  postgresql://user:pass@host
    ("connection_string_with_password",
     re.compile(r"[a-z][a-z0-9+\-.]+://[^:@/\s]+:[^@/\s]{6,}@", re.I)),
    # .env-style  KEY=VALUE where value looks like a secret (20+ non-space chars)
    ("dotenv_assignment",
     re.compile(r"^[A-Z][A-Z0-9_]{2,}=[^\s]{20,}$", re.MULTILINE)),
]

# ---------------------------------------------------------------------------
# Secret-bearing filename patterns
# ---------------------------------------------------------------------------
# Matched against the *basename* (last path component) only.

_SECRET_FILENAME_PATTERNS: List[tuple[str, re.Pattern]] = [
    ("dotenv_file",           re.compile(r"^\.env(?:\..+)?$", re.I)),
    ("pem_certificate",       re.compile(r"\.pem$", re.I)),
    ("private_key_file",      re.compile(r"(?:^|[\\/])id_(?:rsa|ecdsa|ed25519|dsa)$", re.I)),
    ("pkcs12_keystore",       re.compile(r"\.p12$|\.pfx$", re.I)),
    ("google_credentials",    re.compile(r"(?:credentials|service.?account)\.json$", re.I)),
    ("aws_credentials_file",  re.compile(r"^(?:\.aws[\\/])?credentials$", re.I)),
    ("netrc_file",            re.compile(r"^\.netrc$", re.I)),
    ("htpasswd_file",         re.compile(r"^\.htpasswd$", re.I)),
    ("keystore_file",         re.compile(r"\.jks$|\.keystore$", re.I)),
    ("vault_token_file",      re.compile(r"^\.vault-token$", re.I)),
    ("kubernetes_kubeconfig", re.compile(r"^kubeconfig(?:\..+)?$", re.I)),
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SanitizeResult:
    analysis: RepoAnalysis
    redactions: List[str] = field(default_factory=list)

    @property
    def had_redactions(self) -> bool:
        return bool(self.redactions)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_preview(value: str) -> str:
    """Return first 4 chars + '…' — enough to identify the match, not enough to reconstruct it."""
    return (value[:4] + "…") if len(value) > 4 else "****"


def _is_secret_value(s: str) -> tuple[bool, str]:
    """Return (True, pattern_name) if s matches any secret pattern."""
    for name, pat in _SECRET_VALUE_PATTERNS:
        if pat.search(s):
            return True, name
    return False, ""


def _is_secret_filename(path: str) -> tuple[bool, str]:
    """Return (True, pattern_name) if the basename of path matches a secret-file pattern."""
    # Extract the filename component (handle both / and \)
    basename = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    for name, pat in _SECRET_FILENAME_PATTERNS:
        if pat.search(basename):
            return True, name
    return False, ""


def _redact_string(
    value: str, field_path: str, redactions: List[str]
) -> str:
    """If value matches a secret pattern, redact it and record the event."""
    matched, pattern_name = _is_secret_value(value)
    if matched:
        redactions.append(f"{field_path} matched {pattern_name}")
        log.warning(
            "ai.sanitize: redacted potential secret in %s "
            "(pattern=%s, preview=%r); value replaced with %r",
            field_path,
            pattern_name,
            _safe_preview(value),
            REDACTED,
        )
        return REDACTED
    return value


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def sanitize_analysis(analysis: RepoAnalysis) -> SanitizeResult:
    """
    Return a copy of ``analysis`` with secret-looking strings replaced by
    ``REDACTED`` and a list of human-readable redaction notices.

    The original ``analysis`` object is never mutated.
    """
    # Work on mutable dict so we can selectively replace fields.
    data = analysis.model_dump(exclude_none=False)
    redactions: List[str] = []

    # --- project_name ---
    if data.get("project_name"):
        data["project_name"] = _redact_string(data["project_name"], "project_name", redactions)

    # --- languages (strings) ---
    langs: List[str] = []
    for i, lang in enumerate(data.get("languages") or []):
        langs.append(_redact_string(str(lang), f"languages[{i}]", redactions))
    data["languages"] = langs

    # --- frameworks (strings) ---
    fws: List[str] = []
    for i, fw in enumerate(data.get("frameworks") or []):
        fws.append(_redact_string(str(fw), f"frameworks[{i}]", redactions))
    data["frameworks"] = fws

    # --- important_files ---
    clean_files = []
    for i, entry in enumerate(data.get("important_files") or []):
        if isinstance(entry, str):
            matched_fn, fn_pattern = _is_secret_filename(entry)
            if matched_fn:
                redactions.append(f"important_files[{i}] path matched {fn_pattern}")
                log.warning(
                    "ai.sanitize: redacted secret-bearing filename at important_files[%d] "
                    "(pattern=%s, preview=%r)",
                    i, fn_pattern, _safe_preview(entry),
                )
                clean_files.append(REDACTED)
            else:
                clean_files.append(_redact_string(entry, f"important_files[{i}]", redactions))
        else:
            # Dict representation of ImportantFileEntry
            path = str(entry.get("path", ""))
            matched_fn, fn_pattern = _is_secret_filename(path)
            if matched_fn:
                redactions.append(f"important_files[{i}].path matched {fn_pattern}")
                log.warning(
                    "ai.sanitize: redacted secret-bearing filename at important_files[%d].path "
                    "(pattern=%s, preview=%r)",
                    i, fn_pattern, _safe_preview(path),
                )
                entry = dict(entry)
                entry["path"] = REDACTED
                entry["description"] = REDACTED
            else:
                entry = dict(entry)
                entry["path"] = _redact_string(path, f"important_files[{i}].path", redactions)
                if entry.get("description"):
                    entry["description"] = _redact_string(
                        str(entry["description"]),
                        f"important_files[{i}].description",
                        redactions,
                    )
            clean_files.append(entry)
    data["important_files"] = clean_files

    # --- dependencies ---
    clean_deps = []
    for i, dep in enumerate(data.get("dependencies") or []):
        if isinstance(dep, str):
            clean_deps.append(_redact_string(dep, f"dependencies[{i}]", redactions))
        else:
            dep = dict(dep)
            dep["name"] = _redact_string(str(dep.get("name", "")), f"dependencies[{i}].name", redactions)
            if dep.get("version"):
                dep["version"] = _redact_string(
                    str(dep["version"]), f"dependencies[{i}].version", redactions
                )
            clean_deps.append(dep)
    data["dependencies"] = clean_deps

    # --- project_structure (walk all string leaves) ---
    if data.get("project_structure") is not None:
        data["project_structure"] = _sanitize_structure(data["project_structure"], redactions)

    # Reconstruct a validated RepoAnalysis from the cleaned data.
    clean_analysis = RepoAnalysis.model_validate(data)
    return SanitizeResult(analysis=clean_analysis, redactions=redactions)


def _sanitize_structure(obj: object, redactions: List[str]) -> object:
    """Recursively walk project_structure, redacting secret-looking strings."""
    if isinstance(obj, str):
        matched_val, pattern_name = _is_secret_value(obj)
        if matched_val:
            redactions.append(f"project_structure leaf matched {pattern_name}")
            log.warning(
                "ai.sanitize: redacted potential secret in project_structure "
                "(pattern=%s, preview=%r)",
                pattern_name,
                _safe_preview(obj),
            )
            return REDACTED
        # Also check if it's a secret filename
        matched_fn, fn_pattern = _is_secret_filename(obj)
        if matched_fn:
            redactions.append(f"project_structure filename matched {fn_pattern}")
            log.warning(
                "ai.sanitize: redacted secret-bearing filename in project_structure "
                "(pattern=%s, preview=%r)",
                fn_pattern,
                _safe_preview(obj),
            )
            return REDACTED
        return obj
    if isinstance(obj, list):
        return [_sanitize_structure(item, redactions) for item in obj]
    if isinstance(obj, dict):
        return {k: _sanitize_structure(v, redactions) for k, v in obj.items()}
    return obj
