#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI/UX Pro Max Search - BM25 search engine for UI/UX style guides
Usage: python search.py "<query>" [--domain <domain>] [--stack <stack>] [--max-results 3]
       python search.py "<query>" --design-system [-p "Project Name"]
       python search.py "<query>" --design-system --variance 8 --motion 9 --density 7

Domains: style, prompt, color, chart, landing, product, ux, typography, google-fonts, gsap
Stacks: react, nextjs, vue, svelte, astro, swiftui, react-native, flutter, nuxtjs, nuxt-ui, html-tailwind, shadcn, jetpack-compose, threejs, angular, laravel, javafx, wpf, winui, avalonia, uno, uwp

Design dials (1-10, only with --design-system):
  --variance   DESIGN_VARIANCE: 1=centered/minimal, 10=bold/asymmetric
  --motion     MOTION_INTENSITY: 1=minimal feedback, 10=advanced motion guidance
  --density    VISUAL_DENSITY: 1=spacious, 10=compact grouping guidance

This Clonamic copy is stdout/JSON only and never writes project files.
"""

import argparse
import sys
import io
from core import CSV_CONFIG, AVAILABLE_STACKS, MAX_RESULTS, search, search_stack
from design_system import generate_design_system

# Force UTF-8 for stdout/stderr to handle emojis on Windows (cp1252 default)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def format_output(result):
    """Format results for Claude consumption (token-optimized)"""
    if "error" in result:
        return f"Error: {result['error']}"

    output = []
    if result.get("stack"):
        output.append(f"## UI Pro Max Stack Guidelines")
        output.append(f"**Stack:** {result['stack']} | **Query:** {result['query']}")
    else:
        output.append(f"## UI Pro Max Search Results")
        output.append(f"**Domain:** {result['domain']} | **Query:** {result['query']}")
    output.append(f"**Source:** {result['file']} | **Found:** {result['count']} results\n")

    for i, row in enumerate(result['results'], 1):
        output.append(f"### Result {i}")
        for key, value in row.items():
            value_str = str(value)
            if len(value_str) > 300:
                value_str = value_str[:300] + "..."
            output.append(f"- **{key}:** {value_str}")
        output.append("")

    return "\n".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UI Pro Max Search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--domain", "-d", choices=list(CSV_CONFIG.keys()), help="Search domain")
    parser.add_argument("--stack", "-s", choices=AVAILABLE_STACKS, help=f"Stack-specific search. Available: {', '.join(AVAILABLE_STACKS)}")
    parser.add_argument("--max-results", "-n", type=int, default=MAX_RESULTS, help="Max results (default: 3)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    # Design system generation
    parser.add_argument("--design-system", "-ds", action="store_true", help="Generate complete design system recommendation")
    parser.add_argument("--project-name", "-p", type=str, default=None, help="Project name for design system output")
    parser.add_argument("--format", "-f", choices=["ascii", "markdown"], default="ascii", help="Output format for design system")
    # Design dials (1-10), only applied with --design-system
    parser.add_argument("--variance", type=int, choices=range(1, 11), metavar="1-10", help="DESIGN_VARIANCE dial: 1=centered/minimal, 10=bold/asymmetric (only with --design-system)")
    parser.add_argument("--motion", type=int, choices=range(1, 11), metavar="1-10", help="MOTION_INTENSITY dial: 1=minimal feedback, 10=advanced motion guidance (only with --design-system)")
    parser.add_argument("--density", type=int, choices=range(1, 11), metavar="1-10", help="VISUAL_DENSITY dial: 1=spacious, 10=compact grouping guidance (only with --design-system)")

    args = parser.parse_args()

    format_requested = any(option in sys.argv[1:] for option in ("--format", "-f"))
    max_results_requested = any(option in sys.argv[1:] for option in ("--max-results", "-n"))
    if args.design_system:
        if args.json:
            parser.error("--json is available only for search results, not --design-system")
        if args.domain or args.stack:
            parser.error("--domain/--stack cannot be combined with --design-system")
        if max_results_requested:
            parser.error("--max-results cannot be combined with --design-system")
    else:
        if args.project_name or args.variance is not None or args.motion is not None or args.density is not None:
            parser.error("--project-name and design dials require --design-system")
        if format_requested:
            parser.error("--format requires --design-system")
        if args.domain and args.stack:
            parser.error("choose one of --domain or --stack")

    # Design system takes priority
    if args.design_system:
        result = generate_design_system(
            args.query,
            args.project_name,
            args.format,
            persist=False,
            page=None,
            output_dir=None,
            variance=args.variance,
            motion=args.motion,
            density=args.density
        )
        print(result)
    # Stack search
    elif args.stack:
        result = search_stack(args.query, args.stack, args.max_results)
        if args.json:
            import json
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_output(result))
    # Domain search
    else:
        result = search(args.query, args.domain, args.max_results)
        if args.json:
            import json
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_output(result))
