# Contributing to DuckDB Advanced GUI

Thank you for taking the time to contribute! 🎉

This project is maintained by **Yash Kanzariya**. All contributions — bug reports, feature requests, documentation improvements, and code — are welcome.

---

## 🐛 Bug Reports

Please open a GitHub Issue and include:

1. **DuckDB version** (`SELECT version()`)
2. **Python version** (`python --version`)
3. **OS / browser**
4. **Steps to reproduce** the bug
5. **Expected vs actual** behaviour
6. Any **error messages** from the browser console or server terminal

---

## 💡 Feature Requests

Open a GitHub Issue with the label `enhancement`. Describe:

- What you want to do (the goal, not the implementation)
- Why it would be useful
- Any mockups or examples

---

## 🔧 Pull Requests

### Setup

```bash
git clone https://github.com/yashkanzariya/duckdb-advanced-gui
cd duckdb-advanced-gui
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Workflow

1. **Fork** the repo and create a branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Test manually:
   ```bash
   DUCKDB_PATH=test.duckdb python app.py
   # Open http://localhost:5000 and test your change
   ```
4. Run the quick smoke test:
   ```bash
   DUCKDB_PATH=test.duckdb python -c "
   import app, json
   app._register_env_db()
   client = app.app.test_client()
   for ep in ['/api/info', '/api/schema', '/api/dashboard']:
       r = client.get(ep)
       assert r.status_code == 200, f'{ep} failed: {r.status_code}'
       print(f'OK  {ep}')
   "
   ```
5. Commit: `git commit -m "feat: describe your change"`
6. Push and open a PR against `main`

### Code Style

- Python: follow PEP 8, use type hints where practical
- JavaScript: vanilla ES2020+, no build step, no frameworks
- Keep the frontend a single self-contained `templates/index.html`
- Every new API route must: validate inputs, use parameterised queries, return consistent `{"ok": true}` or `{"error": "..."}` JSON

### Security Guidelines

- **Never** interpolate user input into SQL strings — always use `?` parameters
- **Always** validate table/column names against `SHOW TABLES` / `duckdb_columns()` before use
- **Never** expose `traceback.format_exc()` to the HTTP response (use `err_resp()`)
- File uploads: validate extension, use temp files, clean up in `finally`

---

## 📄 License

By contributing you agree that your work will be licensed under the [MIT License](LICENSE).
