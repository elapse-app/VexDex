"""Issue, list, and revoke inbound API tokens for the VexDex API.

Runs against the database in `DATABASE_URL`. To manage production tokens, point
that at the production DB — e.g. `fly ssh console -C "python manage_tokens.py list"`.

    python manage_tokens.py create --label frontend
    python manage_tokens.py list
    python manage_tokens.py revoke --label frontend
    python manage_tokens.py revoke --id 3
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from db import (
    create_api_token,
    ensure_schema,
    get_engine,
    list_api_tokens,
    revoke_api_token,
)

load_dotenv()


def _cmd_create(engine, args: argparse.Namespace) -> None:
    raw = create_api_token(engine, args.label)
    print(f"Created token for {args.label!r}. Store it now — it is not recoverable:\n")
    print(f"  {raw}\n")


def _cmd_list(engine, _args: argparse.Namespace) -> None:
    tokens = list_api_tokens(engine)
    if not tokens:
        print("No API tokens.")
        return
    print(f"{'id':>4}  {'label':<24}  {'created':<20}  {'last used':<20}  status")
    for t in tokens:
        created = t.created_at.strftime("%Y-%m-%d %H:%M:%S")
        last_used = t.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if t.last_used_at else "-"
        status = f"revoked {t.revoked_at:%Y-%m-%d}" if t.revoked_at else "active"
        print(f"{t.token_id:>4}  {t.label:<24}  {created:<20}  {last_used:<20}  {status}")


def _cmd_revoke(engine, args: argparse.Namespace) -> None:
    count = revoke_api_token(engine, token_id=args.id, label=args.label)
    target = f"id {args.id}" if args.id is not None else f"label {args.label!r}"
    print(f"Revoked {count} token(s) matching {target}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Mint a new token and print it once.")
    p_create.add_argument("--label", required=True, help="Human name for the client.")
    p_create.set_defaults(func=_cmd_create)

    p_list = sub.add_parser("list", help="List all tokens and their status.")
    p_list.set_defaults(func=_cmd_list)

    p_revoke = sub.add_parser("revoke", help="Revoke tokens by id or label.")
    group = p_revoke.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=int, help="Token id to revoke.")
    group.add_argument("--label", help="Revoke every active token with this label.")
    p_revoke.set_defaults(func=_cmd_revoke)

    args = parser.parse_args()

    engine = get_engine()
    ensure_schema(engine)
    args.func(engine, args)


if __name__ == "__main__":
    main()
