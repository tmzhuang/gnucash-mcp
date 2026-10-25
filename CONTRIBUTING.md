# Contributing to gnucash-mcp

Thank you for your interest in contributing! This project welcomes contributions from the community.

## How to Contribute

### 1. Report Bugs

If you find a bug, please open an issue with:
- A clear description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- Your environment (Python version, MariaDB version, GnuCash version)

### 2. Submit Pull Requests

We welcome pull requests! Here's how to contribute:

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes** following the coding standards in [AGENT.md](AGENT.md)
4. **Test** your changes locally
5. **Submit a pull request**

### 3. Good First Issues

Look for issues labeled "good first issue" to get started.

## Development Setup

### Prerequisites
- Python 3.10+
- pip, setuptools
- MariaDB (for testing)

### Setup

```bash
# Clone and setup
git clone https://github.com/yourusername/gnucash-mcp.git
cd gnucash-mcp
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Setup database (requires GnuCash export)
# See docs/database-setup.md
```

## Coding Standards

See [AGENT.md](AGENT.md) for detailed coding standards.

### Code Style

- Line length: 88 characters
- Indentation: 4 spaces
- Type hints: Required for all functions
- Docstrings: Required for all public functions and classes

### Testing

Before submitting:
- Run `ruff check .`
- Run `pytest tests/`
- Run `ruff format .` (auto-format)

## Pull Request Process

1. **Describe your changes** in the PR title and description
2. **Reference any related issues**
3. **Include screenshots** if UI changes (not applicable here)
4. **Update documentation** if needed
5. **Add tests** for new features
6. **Self-review** your changes

## Code Review

All contributions go through review:
- Maintainer reviews code
- Tests run automatically
- Feedback provided within 48 hours
- Merge after approval

## Style Guide

- [Python PEP 8](https://pep8.org/)
- [flake8](https://flake8.pycqa.org/)
- [ruff](https://astral.sh/ruff/) for linting

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new spending analysis tool
fix: resolve account ambiguity handling
docs: update README with setup instructions
test: add tests for date parsing
chore: update dependencies
```

## Questions?

- Open an issue for questions
- Check existing issues
- Review [AGENT.md](AGENT.md) for guidelines

## Code of Conduct

Be respectful and constructive. We value:
- Diverse perspectives
- Welcoming newcomers
- Constructive feedback
- Clear communication

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license.

---

Thank you for contributing to gnucash-mcp!
