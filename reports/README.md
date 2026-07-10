# reports/

Generated buy-review artifacts from the Agents lane (`scripts/agents_review.py` →
`scripts/agents_report.py`). Each run produces a `.json` snapshot, a `.md` report, and a
self-contained `.html` dashboard.

**`*-STUB-SAMPLE.*`** are produced by the deterministic stub engine (`DEBUG_STUB=1`) to
demonstrate the pipeline shape. **They are NOT real analysis** — the numbers are placeholders
and the files are bannered as such. Real verdicts require the lane enabled on the laptop
(`AGENTS_ENABLED=true` + `requirements-agents.txt` + `ANTHROPIC_API_KEY`); see
`.claude/modules/agents.md`.
