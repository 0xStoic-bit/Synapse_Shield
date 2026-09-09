# Contributing to Synapse Shield

First off, thank you for considering contributing to Synapse Shield! We welcome contributions from developers, security researchers, and machine learning enthusiasts.

## Local Development Setup

To get your environment up and running:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/0xStoic-bit/Synapse_Shield.git
   cd Synapse_Shield
   ```

2. **Set up a virtual environment (Python 3.10+ required):**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies in editable mode:**
   ```bash
   pip install -e .
   pip install pytest httpx pytest-cov ruff
   ```

4. **Run the test suite:**
   We strictly enforce that all tests pass before accepting any Pull Request.
   ```bash
   pytest tests -v
   ```

## Development Guidelines

### Coding Standards
- We use **Ruff** for linting and formatting. Run `ruff check .` before committing.
- Follow PEP 8 style guidelines.
- Keep the zero-dependency mindset for the core inference engine (`models.py`). Avoid adding large frameworks like PyTorch or TensorFlow to the main dependencies. NumPy is our sole numerical dependency.

### Pull Request Workflow
1. Create a descriptive branch name from `main` (e.g., `feature/advanced-mouse-heuristics` or `fix/jwt-timeout`).
2. Keep your commits atomic and write clear, concise commit messages.
3. Write unit tests for any new features or bug fixes in the `tests/` directory.
4. Update documentation, `CHANGELOG.md`, or docstrings if your changes impact the API surface.
5. Open a Pull Request. CI checks will run automatically. Wait for maintainers to review.

### Security Vulnerabilities
If you are contributing a patch for a security vulnerability, please refer to our `SECURITY.md` for proper disclosure protocols. Do NOT submit a public PR for an unpatched vulnerability without coordinating with us first.

Thank you for helping us make the internet a safer place!
