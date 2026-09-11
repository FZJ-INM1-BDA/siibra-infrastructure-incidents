"""Manage incidents.json: create, update and resolve incidents.

Examples:
    # create a new (active) incident
    python manage.py new "Service degraded" \\
        -m "We are investigating an issue." \\
        -t baseinfra -t baseinfra/k8s

    # add an update to a current incident
    python manage.py update -m "The issue is being worked on." \\
        --memo "root cause was a network switch"

    # add a final update and move the incident into the 'past' list
    python manage.py resolve -m "Issue resolved."

update/resolve act on a current (active) incident chosen by --index (0-based,
position in the 'incidents' list). If --index is omitted and there is exactly
one active incident, that one is used; otherwise an error is raised.

Datetime accepts the same offset syntax as gen_datetime.py, e.g. -1d, +1h30m.
If omitted, the current time (RFC3339, local timezone) is used.
"""

import argparse
import datetime
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INCIDENTS_FILE = ROOT / "incidents.json"

# Keep in sync with schema/incident.schema.json
VALID_TAGS = (
    "baseinfra",
    "baseinfra/vm",
    "baseinfra/k8s",
    "baseinfra/routing",
    "externsvc",
    "externsvc/ebrains",
    "externsvc/ebrains/k8s",
)

DELTA_PATTERN = re.compile(
    r"^(?P<sign>[-+])(?P<days>\d+d)?(?P<hours>\d+h)?(?P<minutes>\d+m)?$"
)


def resolve_datetime(spec):
    """Return an RFC3339 timestamp. `spec` is None or an offset like -1d/+1h30m."""
    now = datetime.datetime.now(datetime.UTC)
    if spec:
        matched = DELTA_PATTERN.match(spec)
        if matched is None:
            raise ValueError(f"datetime offset does not match {DELTA_PATTERN.pattern}")
        days = matched.group("days")
        hours = matched.group("hours")
        minutes = matched.group("minutes")
        delta = datetime.timedelta(
            days=int(days[:-1]) if days else 0,
            hours=int(hours[:-1]) if hours else 0,
            minutes=int(minutes[:-1]) if minutes else 0,
        )
        now = now + delta if matched.group("sign") == "+" else now - delta
    return now.astimezone().isoformat()


def load():
    with open(INCIDENTS_FILE, encoding="utf-8") as fp:
        return json.load(fp)


def save(data):
    with open(INCIDENTS_FILE, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False)
        fp.write("\n")


def validate_tags(tags):
    invalid = [t for t in tags if t not in VALID_TAGS]
    if invalid:
        raise ValueError(
            f"invalid tag(s): {', '.join(invalid)}. "
            f"Valid tags: {', '.join(VALID_TAGS)}"
        )


def select_active(data, index):
    """Return an active incident chosen by index.

    If index is None: use the only active incident if there is exactly one,
    otherwise raise. If index is given, it must be a valid position.
    """
    incidents = data.get("incidents", [])
    if index is None:
        if len(incidents) == 1:
            return incidents[0]
        raise ValueError(
            f"--index is required: there are {len(incidents)} active incidents"
        )
    if not 0 <= index < len(incidents):
        raise ValueError(
            f"index {index} out of range: {len(incidents)} active incident(s)"
        )
    return incidents[index]


def make_update(message, datetime_spec, memo):
    update = {
        "datetime": resolve_datetime(datetime_spec),
        "message": message,
    }
    if memo:
        update["memo"] = memo
    return update


def cmd_new(args):
    data = load()
    validate_tags(args.tag)
    incident = {
        "id": str(uuid.uuid4()),
        "tags": args.tag,
        "title": args.title,
        "updates": [make_update(args.message, args.datetime, args.memo)],
    }
    data.setdefault("incidents", []).append(incident)
    save(data)
    print(f"created incident {incident['id']}")
    return 0


def cmd_update(args):
    data = load()
    incident = select_active(data, args.index)
    incident["updates"].append(make_update(args.message, args.datetime, args.memo))
    save(data)
    print(f"added update to {incident['id']}")
    return 0


def cmd_resolve(args):
    data = load()
    incident = select_active(data, args.index)
    if args.message:
        incident["updates"].append(make_update(args.message, args.datetime, args.memo))
    data["incidents"].remove(incident)
    data.setdefault("past", []).insert(0, incident)
    save(data)
    print(f"resolved {incident['id']}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Manage siibra infrastructure incidents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_update_args(p, message_required=True):
        p.add_argument(
            "-m", "--message", required=message_required,
            help="the public-facing update message",
        )
        p.add_argument(
            "-d", "--datetime", default=None,
            help="offset for the update time (e.g. -1d, +1h30m). Default: now",
        )
        p.add_argument("--memo", default=None, help="internal note (not public)")

    def add_index_arg(p):
        p.add_argument(
            "-i", "--index", type=int, default=None,
            help="0-based index of the active incident. "
                 "Optional if exactly one active incident exists",
        )

    p_new = sub.add_parser("new", help="create a new active incident")
    p_new.add_argument("title", help="incident title")
    p_new.add_argument(
        "-t", "--tag", action="append", default=[],
        help=f"tag (repeatable). One of: {', '.join(VALID_TAGS)}",
    )
    add_update_args(p_new)
    p_new.set_defaults(func=cmd_new)

    p_update = sub.add_parser("update", help="add an update to a current incident")
    add_index_arg(p_update)
    add_update_args(p_update)
    p_update.set_defaults(func=cmd_update)

    p_resolve = sub.add_parser(
        "resolve", help="add a final update and move a current incident to 'past'"
    )
    add_index_arg(p_resolve)
    add_update_args(p_resolve, message_required=False)
    p_resolve.set_defaults(func=cmd_resolve)

    return parser


def normalize_datetime_args(argv):
    """Glue a datetime offset onto its flag so leading '-' (e.g. -1h) isn't
    mistaken for an option. Turns '-d -1h' into '-d=-1h'."""
    out = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in ("-d", "--datetime") and i + 1 < len(argv):
            out.append(f"{token}={argv[i + 1]}")
            i += 2
            continue
        out.append(token)
        i += 1
    return out


def main(argv):
    parser = build_parser()
    args = parser.parse_args(normalize_datetime_args(argv))
    try:
        return args.func(args)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
