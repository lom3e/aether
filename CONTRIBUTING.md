# Contributing to Aether

Thank you for your interest in contributing to Aether! We welcome contributions of all forms, including bug reports, feature requests, documentation improvements, and code changes.

## Development Setup

Aether is built using Python 3.11+ and relies exclusively on the standard library for its core engine.

To set up a local development environment:

1. **Clone the repository**
   ```bash
   git clone https://github.com/aether-ai/aether.git
   cd aether
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install the package in editable mode with development dependencies**
   ```bash
   pip install -e .
   pip install pytest pytest-asyncio pytest-mock build
   ```

## Running Tests

All code changes should be verified by running the test suite. We use `pytest` for testing.

To run the complete test suite:
```bash
pytest tests/ -q -W error
```

Some tests require external services (e.g., a local Ollama server). To run the suite excluding integration tests:
```bash
pytest tests/ -m "not integration" -q -W error
```

## Pull Request Guidelines

When submitting a pull request, please ensure the following:

- **Backward Compatibility**: New features should not break existing functionality or public APIs.
- **Tests**: Include tests for any new features or bug fixes.
- **Documentation**: Update docstrings and relevant documentation files (e.g., in `docs/` or `README.md`).
- **Clean Code**: Adhere to the existing code style. The codebase relies heavily on Python type hints, so ensure types are properly annotated.
- **Commit Messages**: Write clear, descriptive commit messages.

## Architectural Constraints

Before proposing major architectural changes, please review the [Architecture Documentation](docs/architecture.md). Aether strictly adheres to the following principles:

1. **Zero External Dependencies** for the core engine (only standard library). Optional provider SDKs (like `openai`, `anthropic`) should be loaded lazily and must not break the core if missing.
2. **Safe Loop execution**: Always ensure cognitive loops are bounded by `RuntimeSafetyPolicy`.
3. **Structured Observation**: Never flatten JSON or metadata arbitrarily; use the built-in Observation factory.
