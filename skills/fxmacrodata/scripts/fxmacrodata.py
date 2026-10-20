"""FXMacroData operation discovery and sourced macro research briefs."""
from __future__ import annotations

import argparse
import json
import sys

from fxmacrodata_skill import build_context, read_requests
from fxmacrodata_skill._fxmacrodata_client import FXMacroDataError, list_operations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List every operation and its input schema without network access")
    schema = sub.add_parser("schema", help="Show the exact schema for one operation")
    schema.add_argument("operation")
    call = sub.add_parser("call", help="Call one operation and retain its original response")
    call.add_argument("operation")
    call.add_argument("--arguments", default="{}", help="JSON object; never include credentials")
    call.add_argument("--history", action="store_true", help="Collect paginated history explicitly")
    call.add_argument("--max-pages", type=int, default=20)
    brief = sub.add_parser("brief", help="Build a sourced macro brief from explicit requests or public USD defaults")
    brief.add_argument("--request", action="append", default=None, metavar="JSON_FILE")
    brief.add_argument("--currency", default="usd")
    brief.add_argument("--indicator", default=None, help="Catalogue indicator slug, not a guessed alias")
    for command in (call, brief):
        command.add_argument("--output", default=None, help="Save original responses and context as JSON")
        command.add_argument("--max-records", type=int, default=12)
        command.add_argument("--max-chars", type=int, default=12000)
    args = parser.parse_args(argv)
    try:
        if args.command in {"list", "schema"}:
            operations = list_operations()
            if args.command == "schema":
                operations = tuple(op for op in operations if op.name == args.operation)
                if not operations:
                    parser.error("Unknown operation; use list to discover available names")
            data = [{"name": op.name, "description": op.description, "method": op.method,
                     "path": op.path, "input_schema": op.input_schema} for op in operations]
            print(json.dumps(data if args.command == "list" else data[0], ensure_ascii=False, indent=2))
            return 0
        if args.command == "call":
            request = {"operation": args.operation, "arguments": json.loads(args.arguments)}
            if args.history:
                request.update(history=True, max_pages=args.max_pages)
            elif args.max_pages != 20:
                parser.error("--max-pages requires --history")
            requests = [request]
        elif args.request:
            requests = read_requests(args.request)
        else:
            requests = [
                {"operation": "data_catalogue", "arguments": {"currency": args.currency}},
                {"operation": "release_calendar", "arguments": {"currency": args.currency}},
            ]
            if args.indicator:
                requests.append({"operation": "indicator_history", "arguments": {
                    "currency": args.currency, "indicator": args.indicator, "limit": 12,
                }})
        context = build_context(requests, max_records=args.max_records, max_chars=args.max_chars)
        if args.output:
            context.write(args.output)
        print(context.text)
        return 0
    except (ValueError, OSError, FXMacroDataError):
        print("FXMacroData request failed. Check operation schemas, credentials, network access and output permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
