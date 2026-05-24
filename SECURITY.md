# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | ✅ Yes     |
| 1.x     | ⚠️ Upgrade recommended |

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Please email: **yashkanzariya50@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 48 hours. If confirmed, a patch will be released within 7 days.

## Security Design

### What this tool IS designed for
- Local development on a trusted machine
- Internal team tools on a private network
- Trusted single-user analytics environments

### What this tool is NOT designed for
- Public internet exposure without additional hardening
- Multi-tenant SaaS environments
- Untrusted user SQL execution

### Hardening for Production Use

If you expose this tool to a network, apply all of the following:

```bash
# 1. Enable basic auth
export DUCK_USER=admin
export DUCK_PASS="$(openssl rand -base64 24)"

# 2. Restrict to localhost and use a reverse proxy with TLS
export HOST=127.0.0.1

# 3. Example nginx reverse proxy with TLS
# location /duckdb/ {
#     proxy_pass http://127.0.0.1:5000/;
#     auth_basic "DuckDB GUI";
#     auth_basic_user_file /etc/nginx/.htpasswd;
# }
```

### Implemented Protections

| Protection | Status |
|-----------|--------|
| SQL parameterization (filter/sort/where) | ✅ |
| Table name validation against schema | ✅ |
| Column name validation against schema | ✅ |
| Extension name regex whitelist | ✅ |
| Setting name validation against known settings | ✅ |
| Blocked dangerous DDL patterns | ✅ |
| Row count hard cap (10,000) | ✅ |
| Upload size cap (200 MB) | ✅ |
| Upload extension whitelist | ✅ |
| No stack traces to client in production | ✅ |
| Atomic JSON writes (no corruption) | ✅ |
| Full-table DELETE blocked without WHERE | ✅ |
| Optional HTTP Basic Auth | ✅ |

### Known Limitations

- **No CSRF protection** — this is a stateless JSON API consumed by a SPA; add a token if you adapt it to a cookie-auth model
- **No rate limiting** — add `flask-limiter` for public deployments
- **SQL execution is unrestricted** — any SQL can be run via the editor (intentional for a dev tool; add read-only mode if needed)
