# Makefile for gnucash-mcp
# Simplified development tasks

.PHONY: help install lint test smoke clean docs serve

# Default target
help:
	@echo "Available targets:"
	@echo "  pip install -e .     - Install package in editable mode"
	@echo "  pip install -e .[dev] - Install package with dev dependencies"
	@echo "  lint                 - Run linter (ruff)"
	@echo "  test                 - Run unit tests (pytest)"
	@echo "  smoke                - Run smoke test"
	@echo "  clean                - Remove generated files"
	@echo "  docs                 - Build documentation"
	@echo "  serve                - Run the MCP server"
	@echo "  eval                 - Run full evaluation suite (promptfoo)"

# Install package
install:
	pip install -e ".[dev]"

# Install without dev dependencies
install-base:
	pip install -e .

# Lint code
lint:
	ruff check .

# Run unit tests
test:
	pytest tests/ -v

# Run smoke test
smoke:
	python smoke_test.py "EQ Bank"

# Clean generated files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache

# Build documentation
docs:
	@echo "Documentation is available in docs/ directory."
	@echo "To add docs, see CONTRIBUTING.md"

# Run the MCP server
serve:
	python server.py

# Run full evaluation suite
eval:
	promptfoo eval

# Format code
format:
	ruff format .

# Check formatting
format-check:
	ruff format --check .

# Install pre-commit hooks
pre-commit-install:
	pre-commit install

# Run pre-commit hooks
pre-commit-run:
	pre-commit run --all-files

# Create virtual environment
venv-create:
	python -m venv .venv

# Activate virtual environment
venv-activate:
	@echo "Activate virtual environment with:"
	@echo "  source .venv/bin/activate  # Linux/macOS"
	@echo "  .venv\\Scripts\\activate    # Windows"
