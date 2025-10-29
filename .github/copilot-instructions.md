# GitHub Copilot Instructions for chia-blockchain

## Project Overview

This is the Chia blockchain repository - a modern cryptocurrency implementation built from scratch. Key characteristics:
- **Language**: Python 3.10+ (supports 3.10, 3.11, 3.12, 3.13)
- **Core Technology**: Proof of space and time consensus mechanism
- **Architecture**: Full node, farmer, timelord, wallet, and harvester components
- **Key Dependencies**: chiavdf (VDF implementation), chiapos (proof of space), clvm (Chialisp VM), chia_rs (Rust components)

## Code Style and Formatting

### Ruff (Linter and Formatter)
- **REQUIRED**: All code must pass Ruff checks before committing
- Run: `ruff format && ruff check --fix`
- Line length: 120 characters maximum
- Imports must include `from __future__ import annotations` (enforced by isort)
- All relative imports are banned - use absolute imports only
- Follow PEP 8 naming conventions and code style

### Type Hints (MyPy)
- **REQUIRED**: All code must have complete type annotations
- Run: `mypy .`
- Always specify return types for functions
- Always specify types for local variables when not obvious from context
- Use strict mypy configuration (see `mypy.ini.template`)
- Type annotations are required for all function parameters and return values

### Pre-commit Hooks
- Pre-commit hooks are configured and should be installed: `pre-commit install`
- Hooks run automatically before each commit (Ruff, MyPy, and other checks)
- Run manually: `pre-commit run --all-files`

## Testing Requirements

### Test Framework
- **Framework**: pytest with pytest-xdist for parallel execution
- **Location**: All tests in `chia/_tests/` directory
- Run tests: `pytest . -v --durations 0`
- Tests run in parallel by default (`-n auto`)

### Test Coverage
- Maintain high test coverage for all new code
- Use `pytest-cov` for coverage reporting
- Critical paths (consensus, wallet, blockchain) require comprehensive testing

### Test Best Practices
- Write focused, independent tests
- Use existing test fixtures and utilities from `chia/_tests/`
- Mock external dependencies appropriately
- Test edge cases and error conditions
- Follow existing test patterns in the codebase

## Security

### Security Requirements
- **NEVER** commit secrets, passwords, or private keys
- Validate all external inputs
- Use cryptographically secure random generators from `secrets` module
- Follow secure coding practices for cryptographic operations
- BLS signatures and cryptographic primitives are critical - handle with care

### Code Review
- All changes require review and signed commits
- Security-sensitive code requires extra scrutiny
- Run security scanners (CodeQL is configured in workflows)

## Development Workflow

### Branching Strategy
- Feature branches from `main` for all development work
- Branch naming: descriptive names (e.g., `feature/add-new-rpc`, `fix/wallet-sync-issue`)
- All commits must be signed (GPG, SSH, or X.509)
- Squash merge all pull requests

### Build and Test Cycle
1. Install dependencies: `sh install.sh -d` (development mode)
2. Activate virtual environment: `. ./activate`
3. Format code: `ruff format`
4. Lint code: `ruff check --fix`
5. Type check: `mypy .`
6. Run tests: `pytest . -v`

### Continuous Integration
- Pre-commit checks (linting, formatting, type checking) run on all PRs
- Full test suite runs on multiple platforms (Linux, macOS, Windows)
- Multiple Python versions tested (3.10, 3.11, 3.12, 3.13)
- CodeQL security scanning enabled
- All checks must pass before merge

## Pull Request Guidelines

### When Copilot Opens a PR

After opening a pull request, **ALWAYS investigate the PR checks status**:

1. **Wait for CI checks to start**: GitHub Actions workflows will begin automatically
2. **Monitor check status**: Use GitHub's PR checks UI or API to verify:
   - Pre-commit checks (formatting, linting, type checking)
   - Test suite across all platforms
   - CodeQL security analysis
   - Build verification
3. **If checks fail**:
   - Review the failed job logs
   - Identify the root cause (test failures, linting issues, type errors)
   - Fix the issues and push updates to the PR
   - Verify fixes by checking that CI passes on subsequent runs
4. **Don't merge until all checks pass**: This is critical for code quality

### PR Best Practices
- Write clear, descriptive PR titles and descriptions
- Reference related issues with `#issue-number`
- Keep PRs focused and reasonably sized
- Respond to review feedback promptly
- Update documentation if behavior changes
- Ensure backward compatibility unless explicitly breaking

## Documentation

### Code Documentation
- Document all public APIs with clear docstrings
- Include parameter types and descriptions
- Document return values and exceptions
- Keep documentation up-to-date with code changes

### Project Documentation
- Update relevant markdown files for user-facing changes
- Key docs: `README.md`, `CONTRIBUTING.md`, `INSTALL.md`
- Update `CHANGELOG.md` for version changes

## Common Pitfalls to Avoid

1. **Async/Await**: Be careful with async functions - avoid blocking calls
2. **Resource Leaks**: Always close files, sockets, and database connections
3. **Cryptographic Operations**: Don't roll your own crypto - use established libraries
4. **Database Operations**: Use proper transaction handling with aiosqlite
5. **Configuration**: Respect the configuration system in `chia/util/config.py`
6. **Logging**: Use the structured logging system, not `print()` statements

## Internal Libraries and Patterns

### Key Internal Modules
- `chia.util`: Utility functions, configuration, logging
- `chia.consensus`: Consensus rules and validation
- `chia.protocols`: Network protocol definitions
- `chia.types`: Core blockchain types and data structures
- `chia.rpc`: RPC server and client implementations

### Common Patterns
- Use `create_referenced_task()` from `chia.util.task_referencer` instead of `asyncio.create_task()`
- Use structured logging with `logging.getLogger(__name__)`
- Follow existing patterns for RPC endpoints and protocol messages
- Use `chia.util.ints` for fixed-size integer types (uint8, uint32, uint64, etc.)

## Additional Resources

- [Contributing Guidelines](CONTRIBUTING.md)
- [Installation Instructions](INSTALL.md)
- [Chia Documentation](https://docs.chia.net/)
- [Chialisp Documentation](https://chialisp.com/)
- [Chia Green Paper](https://www.chia.net/assets/ChiaGreenPaper.pdf)

## Repository Maintenance

- Dependencies managed via Poetry (see `pyproject.toml`)
- Use `poetry install` or `pip install -e .` for development setup
- Keep dependencies up-to-date but verify compatibility
- Check for security advisories on dependencies

---

**Remember**: The goal is to maintain high code quality, security, and test coverage while following established patterns and best practices in the Chia blockchain codebase.
