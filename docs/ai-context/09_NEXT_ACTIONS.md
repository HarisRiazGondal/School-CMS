# Next Actions — local PC QA handoff

Latest full suite: **227 run,218 passed,9 PostgreSQL-only skips,no failures**. Two connected in-process request/service journeys pass. All72 cloud-browser matrix rows remain unverified due to an explicit URL-policy block.

1. Give docs/LOCAL_PC_QA_AGENT_PROMPT.md to the PC agent and execute the isolated multi-agent QA handoff. Review docs/SCHOOL_SCENARIO_RESULTS.md and 72-row SCHOOL_SCENARIO_MATRIX.md; distinguish request/service evidence from blocked browser scenarios.
2. For actual cloud-browser UI acceptance, supply a permitted browser-accessible test deployment URL. Do not use proxies, alternate browser surfaces or workarounds for the local URL-policy block.
3. Run the matrix in the permitted UI target with synthetic accounts, record screenshots/results and fix reproducible defects. No browser row is currently passed.
4. Prioritize product gaps separately: automatic invoice generation, regular-portal withdrawal/re-admission/account linking, revision-history viewer and any marks/fee-driven promotion rules.
5. Run PostgreSQL concurrency and configured scanner/email/recovery checks when those services are available; CI/VPS rollout remains deferred unless requested.

Current reports: SCHOOL_SCENARIO_RESULTS.md, SCHOOL_SCENARIO_MATRIX.md, SCHOOL_EDGE_RESULTS.md and school_scenario_evidence.json under docs. New graduation-target service guard is verified. Earlier LOCAL_TEST_REPORT.md remains historical and links the prior reviews. Record source/target/test evidence and update affected AI-context Markdown/JSON/HTML together. Do not count test methods, matrix rows and prior focused runs as disjoint totals.
