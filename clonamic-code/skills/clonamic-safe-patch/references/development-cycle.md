# Development cycle

Use this only for a non-trivial feature or behavior change.

1. Lock the observable result, exclusions, and acceptance checks. Design in chat unless an artifact was requested.
2. Write the smallest failing behavior test and confirm its failure is caused by the missing behavior.
3. Implement only enough to pass that test.
4. Refactor after green; keep the same checks green.
5. Repeat for the next independent behavior.

Parallel execution is allowed only for isolated file ownership. A reviewer starts after the worker result and fresh evidence exist. A failed review returns one bounded rework packet; it never creates another user approval inside the accepted scope.
