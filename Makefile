# Makefile for gnucash-mcp
# Development tasks — all use `uv` (no pip, no PYTHONPATH hacks)

.PHONY: help install lint test smoke clean serve pre-commit-run format format-check

help:
	@echo "Available targets:"
	@echo "  install        - Install package in editable mode"
	@echo "  lint           - Run linter (ruff check)"
	@echo "  format         - Format code (ruff format)"
	@echo "  format-check   - Check formatting"
	@echo "  test           - Run unit tests (pytest)"
	@echo "  smoke          - Run smoke test"
	@echo "  serve          - Run the MCP server (stdio)"
	@echo "  pre-commit-run - Run all pre-commit hooks"

install:
	uv pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

test:
	uv run pytest tests/ -v

smoke:
	uv run python smoke_test.py "EQ Bank"

serve:
	uv run gnucash-mcp

pre-commit-run:
	pre-commit run --all-files

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache gnucash_mcp.egg-info
