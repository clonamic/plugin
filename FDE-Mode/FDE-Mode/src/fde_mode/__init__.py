"""FDE-Mode: a Forward-Deployed-Engineer organization for Claude Code.

The package is the deterministic half of the plugin. The LLM half lives in
`skills/` (how the main session directs the work) and `agents/` (the
specialists). Everything here is Python 3.12 standard library only.
"""

__version__ = "1.2.2"
SCHEMA = "fde.out.v1"
