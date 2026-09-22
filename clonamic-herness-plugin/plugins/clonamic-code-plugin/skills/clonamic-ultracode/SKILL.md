---
name: clonamic-ultracode
description: Run bounded native multi-agent review only with viable alternatives, boundary impact, unresolved evidence, and high error cost; requires isolated agents.
---

# Clonamic Ultracode

Activate only after all four gates pass and the host confirms native isolated agents.

## Review contract

Read [references/decision-contract.json](references/decision-contract.json). Give each reviewer the same question, live options, evidence, constraints, exclusions, and budget.

1. Collect positions before sharing them.
2. Require evidence, strongest objection, and falsifying condition.
3. Allow one rebuttal round only for material disagreement.
4. Declare `consensus` only for unanimous compatible reasoning.
5. Preserve all other disagreement as `no_consensus`.

Return one read-only `DecisionReview` with status, unanimous recommendation if any, dissent, evidence, open questions, and budget use.

## Failure

- `unavailable` — no native isolated agents; do not substitute an external executor or simulated voices.
- `aborted` — budget ended; preserve partial positions without recommendation.
- `no_consensus` — preserve dissent and leave the decision unresolved.

No recursion, hidden model choice, retry, authorization, completion verdict, or report formatting.
