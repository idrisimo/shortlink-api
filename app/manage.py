"""Management CLI.  Usage: python -m app.manage create-key <name>"""

import argparse

from app.config import get_settings
from app.db import init_db, make_engine, make_session_factory
from app.security import create_api_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-key", help="Issue a new API key")
    create.add_argument("name", help="Label for the key, e.g. 'my-laptop'")
    args = parser.parse_args(argv)

    engine = make_engine(get_settings().database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        raw = create_api_key(db, args.name)
    print(f"API key for '{args.name}' (shown once, store it safely):\n{raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
