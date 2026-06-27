# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Botte Secrète, please report it privately.

**Contact:** `sylvain.galliez@gmail.com`

**Do not** open a public GitHub issue for security vulnerabilities.

### What to include
- Description of the vulnerability
- Steps to reproduce (proof of concept preferred)
- Potential impact
- Suggested fix (optional)

### Response timeline
- **48h:** Acknowledgment of receipt
- **7 days:** Initial assessment and mitigation plan
- **30 days:** Patch released (depending on severity)

## Scope

This policy covers the `botte-secrete` repository at https://github.com/zedarvates/botte-secrete.

The following are **not** in scope:
- Third-party dependencies (report to their respective maintainers)
- Theoretical attacks requiring physical access or social engineering

## Supported versions

| Version | Supported |
|---------|-----------|
| latest  | ✅ |
| < latest| ❌ |

## Safe by design

Botte Secrète is designed to:
- Run fully locally with **zero cloud dependencies** by default
- Never send data to external servers unless explicitly configured
- Operate with **no system-level privileges** (no sudo, no daemon, no cron)
- Be verifiable: all releases are tagged and the test suite is public
