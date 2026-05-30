# Authoring a new integration

This guide walks through adding a new medium (Discord, email, MS Teams,
a queue) as an iris adapter.

## 1. Copy the reference

```bash
cp -r integrations/slack integrations/<your-name>
cd integrations/<your-name>
```

## 2. Retarget the medium pieces

| File | What changes |
|---|---|
| `config.py` | Replace `SLACK_*` env vars with `<YOUR>_*` |
| `app.py` | Replace Slack Bolt with your medium's library |
| `parser.py` | If your medium has its own message shape, parse it here |
| `handlers/*.py` | Adjust the response formatting to the medium |
| `README.md` | Update env-var docs and smoke-test |

## 3. Leave `client.py` alone

`client.py` is the pure-Python adapter for the iris primitives. It
shells out to `scripts/memory.py`, `scripts/parse-tasks.py`, etc. via
`subprocess`. Every adapter uses the same `client.py` shape; only the
medium-specific code on top differs.

If you find yourself reaching into iris's Python modules directly,
stop. Add a CLI flag to `scripts/<thing>.py` instead, then call it from
`client.py`. That keeps the boundary clean.

## 4. Register in `.env.example`

Append your env vars under a labelled section. Use a unique prefix.

## 5. Smoke test (CI-ready)

Add a `tests/test_<your-name>_adapter.py` that:

1. Confirms `<your-name>/config.healthcheck()` returns sensible flags
   when its env vars are missing (does not raise).
2. Confirms `<your-name>/client.py`'s public functions round-trip
   against a fixture iris state.
3. Mocks the medium's outbound calls (do not hit Slack/Discord in CI).

See `tests/test_adapter_contract.py` for the pattern.

## 6. Open a PR

In the PR description:
- Link to the medium's docs.
- Confirm `python3 scripts/doctor.py` passes.
- Confirm the new test passes.
- Confirm the existing Slack tests still pass (no regression in
  `client.py`).
