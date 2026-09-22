# CI

A GitHub Actions workflow was not committed because the token used to create
this repo lacks `workflows` permission. To add it, create
`.github/workflows/test.yml` yourself:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements-dev.txt
      - run: pytest -q
```
