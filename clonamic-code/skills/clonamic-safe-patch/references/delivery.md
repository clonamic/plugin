# Delivery

Before a completion or release claim:

1. compare the final diff with the approved result and exclusions;
2. run checks after the last mutation;
3. inspect failures, unrun checks, external state, and rollback;
4. review security, data loss, process cleanup, and cross-platform boundaries;
5. deploy through the project's existing path and verify the remote postcondition.

An approved fix/retest/deploy loop continues without another conversational stop. Credentials and device prompts return a resumable platform-action state. A failed required check blocks completion.
