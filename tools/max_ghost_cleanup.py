#!/usr/bin/env python3
"""Audit or deactivate unused MAX bridge ghost users in Synapse.

Dry-run is the default. Deactivation requires a Synapse server-admin access token
and explicit --deactivate --yes. The script never edits Synapse's SQL database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import aiohttp
from ruamel.yaml import YAML


@dataclass(frozen=True)
class Candidate:
    max_user_id: str
    mxid: str
    name: str | None
    phone: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find MAX ghost accounts that have no direct MAX portal. "
            "By default only prints a report."
        )
    )
    parser.add_argument(
        "--config",
        default="/opt/mautrix-max/data/config.yaml",
        help="Bridge config.yaml path",
    )
    parser.add_argument(
        "--db",
        default="/opt/mautrix-max/data/pymatrix-max.db",
        help="Bridge SQLite database path",
    )
    parser.add_argument(
        "--max-id",
        action="append",
        default=[],
        help="Limit to one MAX user ID; may be repeated",
    )
    parser.add_argument(
        "--deactivate",
        action="store_true",
        help="Deactivate verified candidates through Synapse Admin API",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required with --deactivate",
    )
    parser.add_argument(
        "--admin-token-env",
        default="SYNAPSE_ADMIN_TOKEN",
        help="Environment variable containing a Synapse server-admin token",
    )
    return parser.parse_args()


def load_bridge_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        config = YAML(typ="safe").load(handle)
    if not isinstance(config, dict):
        raise RuntimeError(f"Invalid bridge config: {path}")
    return config


def load_candidates(db_path: str, selected_ids: set[str]) -> tuple[list[Candidate], set[str]]:
    if not Path(db_path).exists():
        raise RuntimeError(f"Bridge database not found: {db_path}")

    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        direct_rooms = {
            str(row["mxid"])
            for row in db.execute(
                "SELECT mxid FROM portal WHERE is_direct=1 AND mxid IS NOT NULL"
            )
        }
        rows = db.execute(
            """
            SELECT p.max_user_id, p.mxid, p.name, p.phone
            FROM puppet AS p
            WHERE NOT EXISTS (
                SELECT 1
                FROM portal AS d
                WHERE d.is_direct=1
                  AND d.remote_user_id=p.max_user_id
            )
            ORDER BY COALESCE(p.name, ''), p.max_user_id
            """
        ).fetchall()

    candidates = [
        Candidate(
            max_user_id=str(row["max_user_id"]),
            mxid=str(row["mxid"]),
            name=row["name"],
            phone=row["phone"],
        )
        for row in rows
        if not selected_ids or str(row["max_user_id"]) in selected_ids
    ]
    return candidates, direct_rooms


async def get_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    **kwargs,
) -> tuple[int, object]:
    async with session.request(method, url, **kwargs) as response:
        text = await response.text()
        try:
            payload: object = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = text
        return response.status, payload


async def audit_synapse(
    candidates: list[Candidate],
    direct_rooms: set[str],
    homeserver: str,
    appservice_id: str,
    admin_token: str,
    deactivate: bool,
) -> int:
    headers = {"Authorization": f"Bearer {admin_token}"}
    changed = 0

    async with aiohttp.ClientSession(headers=headers) as session:
        for candidate in candidates:
            encoded_mxid = quote(candidate.mxid, safe="")
            user_url = f"{homeserver}/_synapse/admin/v2/users/{encoded_mxid}"
            status, user = await get_json(session, "GET", user_url)
            if status == 404:
                print(f"SKIP {candidate.mxid}: Synapse account not found")
                continue
            if status != 200 or not isinstance(user, dict):
                print(f"SKIP {candidate.mxid}: user query HTTP {status}: {user!r}")
                continue

            actual_as_id = user.get("appservice_id")
            if actual_as_id != appservice_id:
                print(
                    f"SKIP {candidate.mxid}: appservice_id={actual_as_id!r}, "
                    f"expected {appservice_id!r}"
                )
                continue
            if bool(user.get("deactivated")):
                print(f"OK   {candidate.mxid}: already deactivated")
                continue

            memberships_url = (
                f"{homeserver}/_synapse/admin/v1/users/{encoded_mxid}/memberships"
            )
            m_status, memberships_payload = await get_json(
                session, "GET", memberships_url
            )
            if m_status != 200 or not isinstance(memberships_payload, dict):
                print(
                    f"SKIP {candidate.mxid}: memberships HTTP {m_status}: "
                    f"{memberships_payload!r}"
                )
                continue

            memberships = memberships_payload.get("memberships") or {}
            joined_direct = sorted(
                room_id
                for room_id, membership in memberships.items()
                if room_id in direct_rooms and membership in {"join", "invite", "knock"}
            )
            if joined_direct:
                print(
                    f"KEEP {candidate.mxid}: still linked to direct room(s): "
                    + ", ".join(joined_direct)
                )
                continue

            active_rooms = sorted(
                room_id
                for room_id, membership in memberships.items()
                if membership in {"join", "invite", "knock"}
            )
            details = candidate.name or "без имени"
            if candidate.phone:
                details += f", {candidate.phone}"
            print(
                f"CANDIDATE {candidate.mxid} (MAX {candidate.max_user_id}; {details}); "
                f"active_rooms={len(active_rooms)}"
            )

            if not deactivate:
                continue

            deactivate_url = (
                f"{homeserver}/_synapse/admin/v1/deactivate/{encoded_mxid}"
            )
            d_status, d_payload = await get_json(
                session,
                "POST",
                deactivate_url,
                json={"erase": False},
            )
            if d_status == 200:
                changed += 1
                print(f"DEACTIVATED {candidate.mxid}")
            else:
                print(
                    f"FAILED {candidate.mxid}: deactivate HTTP {d_status}: "
                    f"{d_payload!r}"
                )

    return changed


async def async_main() -> int:
    args = parse_args()
    if args.deactivate and not args.yes:
        print("Refusing destructive action: add --yes with --deactivate", file=sys.stderr)
        return 2

    config = load_bridge_config(args.config)
    selected_ids = {str(value).strip() for value in args.max_id if str(value).strip()}
    candidates, direct_rooms = load_candidates(args.db, selected_ids)

    print(f"Bridge-local candidates without direct portal: {len(candidates)}")
    if not candidates:
        return 0

    admin_token = os.environ.get(args.admin_token_env, "").strip()
    if not admin_token:
        for candidate in candidates:
            details = candidate.name or "без имени"
            if candidate.phone:
                details += f", {candidate.phone}"
            print(
                f"LOCAL-CANDIDATE {candidate.mxid} "
                f"(MAX {candidate.max_user_id}; {details})"
            )
        print(
            f"Set {args.admin_token_env} to verify appservice ownership and room "
            "memberships through Synapse Admin API. No changes made."
        )
        return 0 if not args.deactivate else 2

    homeserver = str(config["homeserver"]["address"]).rstrip("/")
    appservice_id = str(config["appservice"]["id"])
    changed = await audit_synapse(
        candidates=candidates,
        direct_rooms=direct_rooms,
        homeserver=homeserver,
        appservice_id=appservice_id,
        admin_token=admin_token,
        deactivate=args.deactivate,
    )
    print(f"Deactivated: {changed}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
