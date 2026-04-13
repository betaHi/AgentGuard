# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue.
2. Email: [security contact TBD] or use GitHub's private vulnerability reporting.
3. Include: description, reproduction steps, potential impact.

We will acknowledge within 48 hours and provide a fix timeline within 7 days.

## Scope

AgentGuard is a diagnostics library — it reads trace data but does not execute agent code. Security concerns are primarily around:
- Trace data serialization/deserialization (pickle, JSON)
- File system access (trace storage, HTML report generation)
- CLI command injection (user-provided paths)
