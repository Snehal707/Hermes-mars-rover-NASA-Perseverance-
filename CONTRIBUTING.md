# Contributing

## Development Setup

1. Create and activate virtualenv:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install dashboard dependencies:
   ```bash
   cd dashboard && npm install && cd ..
   ```

## Branching

- Create feature branches from `main`
- Keep commits focused and small
- Use descriptive commit messages

## Validation Before PR

Run:

```bash
python3 -m pytest tests/ -q
```

If you touched dashboard code, also run:

```bash
cd dashboard
npm run lint
```

## Pull Requests

- Explain what changed and why
- Include test evidence
- Call out breaking changes clearly
- Include screenshots/GIFs for dashboard UI changes

