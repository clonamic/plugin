# Debugging

No fix precedes a root-cause trace.

1. Capture the exact failure and reproduce it.
2. Trace the bad state backward to its first incorrect boundary.
3. Compare with a working sibling path.
4. State one falsifiable hypothesis.
5. Add the smallest regression test, confirm red, apply one fix, and confirm green.

Three failed correction strategies indicate an architectural problem. Stop patch stacking, preserve evidence, and return the broken assumption and smallest redesign boundary.
