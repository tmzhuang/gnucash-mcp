# Security Policy

This document outlines the security practices, responsibilities, and procedures for the gnucash-mcp project.

## Overview

This project provides LLMs access to personal financial data via a read-only database interface. Security is critical because:
- Users may expose sensitive financial information
- LLMs could potentially generate malicious queries
- Database credentials must be protected

## Security Model

### Defense-in-Depth Approach

The project implements multiple layers of security:

1. **Database Level**
   - MariaDB user granted only `SELECT` privileges
   - No `INSERT`, `UPDATE`, `DELETE`, `DROP`, or `CREATE` permissions
   - Schema-level restrictions

2. **Session Level**
   - `SET SESSION TRANSACTION READ ONLY` before each query
   - Query timeout limits to prevent slow queries
   - Connection validation

3. **Application Level**
   - `guard.py` validates all SQL queries
   - Blocks non-SELECT statements
   - Strips comments to prevent hidden injection
   - Blocks file operations (`INTO OUTFILE`)
   - Blocks locking clauses (`FOR UPDATE`)

## Security Best Practices

### For Users

- ✅ **Never commit `.env` files** - Contains database credentials
- ✅ **Use read-only database users** - Grant minimal privileges
- ✅ **Use strong passwords** - For database authentication
- ✅ **Run locally** - Avoid exposing the server publicly
- ✅ **Monitor queries** - Review executed queries regularly
- ✅ **Regular backups** - Protect your financial data

### For Developers

- ✅ **Always use `guard.check()`** - Before any query execution
- ✅ **Use parameterized queries** - Never string concatenate user input
- ✅ **Validate account names** - Prevent path traversal attacks
- ✅ **Sanitize all inputs** - Escape special characters
- ✅ **Log security events** - Monitor for suspicious activity

## Vulnerability Disclosure

### Responsible Disclosure

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. **DO NOT** post on social media
3. **DO** send an email to [security email or issue]
4. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (optional)

### Response Time

We aim to respond within **48 hours** of receiving a vulnerability report.

### Disclosure Process

1. Confirm the issue exists
2. Assess severity
3. Develop a fix
4. Notify the reporter
5. Release a patch
6. Public disclosure (with permission)

## Known Vulnerabilities

No public vulnerabilities are currently known.

### CVE Tracking

Security vulnerabilities will be tracked with CVE identifiers when published.

## Security Updates

Security updates are prioritized:
- **Critical:** Released within 7 days
- **High:** Released within 14 days
- **Medium:** Released with next release
- **Low:** Included in regular updates

## Secure Deployment

### Environment Variables

Never expose these in code or logs:
- `DB_PASSWORD` - Database credentials
- `DB_HOST` - Database server address
- `DB_NAME` - Database name

### Recommended .env Configuration

```env
# Use strong passwords
DB_PASSWORD=your-very-secure-random-password-here

# Use specific database user with minimal privileges
DB_USER=gnucash_ro

# Use localhost for local development
DB_HOST=127.0.0.1

# Set reasonable query timeout (seconds)
QUERY_TIMEOUT_S=10
```

### Production Considerations

- Use a VPC or private network
- Enable firewall rules
- Use SSL/TLS for database connections
- Implement rate limiting
- Monitor query patterns
- Regular security audits

## Security Audit

### Automated Security Checks

- ✅ Static analysis with `ruff`
- ✅ Dependency scanning (when available)
- ✅ SQL injection checks

### Manual Review

All code changes are manually reviewed for security implications.

## Incident Response

In case of a security incident:

1. **Contain:** Stop the affected service
2. **Assess:** Determine the scope of impact
3. **Notify:** Inform affected users
4. **Fix:** Deploy a security patch
5. **Review:** Conduct post-incident analysis
6. **Document:** Update security policies

## Security Contacts

For security issues:
- Email: [security@gnucash-mcp.example.com]
- GitHub: [Create a private security advisory]

## Third-Party Dependencies

This project uses:
- `mcp` - Official MCP SDK
- `mariadb` - Database driver
- `python-dotenv` - Environment management

All dependencies are checked for known vulnerabilities via Dependabot/renovate.

## Version History

| Version | Date | Security Changes |
|---------|------|------------------|
| 0.1.0 | 2024 | Initial release with read-only enforcement |

## Acknowledgments

Security improvements are possible thanks to:
- Security researchers
- Community feedback
- Automated scanning tools

---

**Remember:** Security is everyone's responsibility. Follow best practices, stay vigilant, and report issues responsibly.
