---
name: voice-dna
description: Use ONLY on content the user asked to have written for publication (post, caption, script, newsletter, long-form) — never on my own work reports to the user, commit messages, code comments, or config docs. Load when the piece must sound like the OWNER rather than like a competent stranger, or when the user asks to build/update their voice profile from their own past writing. Runs LAST in the writing chain, after structure, hook, dumbify and anti-ai.
license: MIT
metadata:
  category: writing
  source: community
  source_repo: artemnovitckii/content-skills
  source_type: community
  date_added: "2026-08-02"
  author: artemnovitckii
  license_source: "https://github.com/artemnovitckii/content-skills/blob/master/LICENSE"
  local_changes: "upstream ships a build README with no SKILL.md; this wraps it as a portable skill, requires an explicit private profile target, and adds the never-publish rule"
---

# Voice-DNA

Upstream ships this as a build guide, not a skill — the profile is the part you make yourself.
This wrapper does two things: it tells you how to build the profile, and it fixes where the
profile lives.

## Scope (harness rule — read before applying anything below)

**Applies ONLY to** content the user asked to have written or polished for publication.

**Never applies to** the assistant's own work reports (core rule 8 owns those), commit messages
and PR bodies (rule 4), code, code comments, config and meta/doc files. Voice matching does not
override a mandated format.

## The profile is private — this is not negotiable

The profile is a fingerprint of how one specific person writes. It belongs with owner context,
not with shareable config:

- **Lives only at** an explicit private profile path supplied by the caller, or in a measured host
  personal-profile interface the user already configured.
- **Never** goes into a global skill/plugin install directory, the public distribution, or a project repo
  the owner does not control. The public package ships this skill and the build prompt only.
- Do not paste the profile, or writing samples used to build it, into an external service.

Read it only through the supplied path or interface when a piece needs the owner's voice. Treat the
profile as unavailable when no target was supplied, the target is missing, or its first nonblank
line starts with `TEMPLATE-UNFILLED`; skip voice
matching and do not invent a voice. Offer to build the profile only when the user explicitly asks
to establish or capture their personal voice. For a one-off voice pass, the user may provide the
profile in the current conversation; do not persist it automatically.

## Build it (once, ~2 minutes of the user's time)

The user supplies 10–20 pieces of their own writing (20 is better; spoken transcripts of their own
videos beat captions, because they show how the person actually talks). Then run this analysis.
Persist the result only when the user explicitly supplied or approved a private target; otherwise
return it in the current conversation without creating a file:

1. **Analyze — how, not what.** Do not summarize the topics. Extract:
   - **톤** — the overall stance (e.g. blunt but warm).
   - **말버릇** — recurring phrases, how sentences start.
   - **문장 리듬** — length pattern, where paragraphs break (e.g. short. then a long one. then short).
   - **시그니처 훅** — the person's own way of opening a piece.
   - **안티보이스 (금지어)** — what this person would never write.
2. **Write the profile** as *instructions*, not description — a block that can be dropped in front
   of any draft and immediately produce that voice. Quote 3–5 real lines as anchors.
3. **Verify** — write one fresh sample paragraph from the profile alone and put it beside a real
   piece by the owner. If they do not read as the same person, the profile is wrong: name which
   dimension missed and fix that dimension, not the sample.

## Applying it

Load the profile, then rewrite for voice only — do not re-litigate structure, hook, or reading
level, which the earlier skills already settled. Voice is the last pass because it is the one that
must survive; if a voice change would break an accurate claim, accuracy wins (see
`anti-ai-writing`: Accurate > Clear > Specific > Voiced > Stylish).

Keep the profile current: when the owner's writing drifts, rebuild from recent pieces rather than
patching the old profile.
