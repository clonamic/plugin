---
name: clonamic-grill-me
description: Interview the user one question at a time to clarify a decision, intent, constraints, assumptions, and alternatives. Use only when the user explicitly invokes `/clonamic-grill-me` or asks to be interviewed or pressure-tested.
---

# Clonamic Grill Me

Expand the user's understanding until the next useful action is clear. This is an explicit interview
mode, not an automatic prerequisite for work.

## Loop

1. Read available project evidence before asking anything it can answer.
2. Ask one high-value question at a time and include a concise recommended answer.
3. Follow the user's last answer when it materially changes the decision; do not ask questions only to prolong the interview.
4. Test intent, constraints, assumptions, alternatives, reversibility, failure modes, and success evidence as relevant.
5. Stop as soon as the user can make the decision or the requested action is sufficiently specified.

## UX limits

- Do not require a fixed question count.
- Do not repeat answered questions, summarize as filler, or turn clear work into an interview.
- Do not write files or mutate project state unless that output is explicitly requested and approved.
- If the user asks to stop or proceed, stop interviewing immediately and hand the clarified facts to the normal workflow.

## Output

During the interview, return only the next question and recommendation. At convergence, return a
short decision brief: intent, constraints, decision, rejected alternative, open risk, and acceptance
evidence. Keep it in chat unless the user requested an artifact.
