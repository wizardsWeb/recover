"""Create a sign-in-ready user without going through email confirmation.

The project has ``mailer_autoconfirm`` off, so a normal sign-up issues no
session — it sends a confirmation link and waits. Supabase's built-in mailer
also allows only a couple of messages an hour per project, which is fewer than a
day of development spends, and once it is exhausted sign-up looks broken rather
than rate limited: the form says "check your email" and no email ever comes.

This creates the user through the Admin API with ``email_confirm`` already true,
so the account is live immediately and ``signInWithPassword`` works on the first
try. That is a real bypass of email verification, which is why it refuses to run
against a production environment — see ``_guard_environment``.

The ``merchants`` row is not created here. ``on_auth_user_created`` in the
initial migration does it, keyed off ``raw_user_meta_data->>'name'``, and going
through the Admin API means that trigger fires exactly as it would for a genuine
sign-up. Seeding the row by hand would be a second implementation of a thing the
database already does.

Usage::

    cd backend
    .venv/bin/python scripts/create_dev_user.py                      # defaults
    .venv/bin/python scripts/create_dev_user.py --email me@test.dev --password hunter22
    .venv/bin/python scripts/create_dev_user.py --onboarded          # skip /onboarding

Re-running with the same email resets that user's password rather than failing,
so it doubles as "I forgot what I set it to".
"""

import argparse
import base64
import json
import sys
from typing import Any

import httpx

from app.config import get_settings

#: Matches the vertical check constraint in the initial migration.
VERTICALS = ("d2c_beauty", "edtech_subscription", "b2b_distribution", "other")

DEFAULT_EMAIL = "dev@localhost.test"
DEFAULT_PASSWORD = "devpassword123"
DEFAULT_NAME = "Dev Merchant"


def _guard_environment() -> None:
    """Refuse to mint a pre-confirmed account against a real deployment.

    Everything below authenticates with the service-role key, which bypasses RLS
    and email verification both. That is fine on a laptop and is not fine
    anywhere a real merchant's data lives, and the difference between the two is
    one environment variable — so it is worth checking rather than trusting.
    """
    environment = get_settings().ENVIRONMENT.lower()
    if environment in {"production", "staging"}:
        sys.exit(
            f"Refusing to run: ENVIRONMENT is {environment!r}. This script creates an "
            "account with email verification already satisfied, which is a development "
            "affordance only."
        )


class Admin:
    """Thin wrapper over the GoTrue admin endpoints.

    The service key goes in both ``apikey`` and ``Authorization``: Supabase's
    gateway reads the first and GoTrue reads the second, and a call missing
    either one fails in a way that looks like a permissions problem.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
        self._rest = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1"
        key = settings.SUPABASE_SERVICE_KEY
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._anon_key = settings.SUPABASE_ANON_KEY
        self._client = httpx.Client(timeout=20.0)

    def find_user(self, email: str) -> dict[str, Any] | None:
        """Return the user with this email, or None.

        Pages rather than filters. GoTrue's admin list has gained a ``filter``
        parameter at some point in its history, and which builds honour it is not
        something a dev script should depend on.
        """
        page = 1
        while page <= 20:
            response = self._client.get(
                f"{self._base}/admin/users",
                headers=self._headers,
                params={"page": page, "per_page": 200},
            )
            response.raise_for_status()
            users = response.json().get("users", [])
            if not users:
                return None
            for user in users:
                if (user.get("email") or "").lower() == email.lower():
                    return dict(user)
            page += 1
        return None

    def create_user(self, email: str, password: str, name: str) -> dict[str, Any]:
        response = self._client.post(
            f"{self._base}/admin/users",
            headers=self._headers,
            json={
                "email": email,
                "password": password,
                # The whole point: the account is usable without a round trip
                # through an inbox that may never receive anything.
                "email_confirm": True,
                # Read by handle_new_user() to name the merchant row, so
                # onboarding can pre-fill instead of asking twice.
                "user_metadata": {"name": name},
            },
        )
        response.raise_for_status()
        return dict(response.json())

    def reset_user(self, user_id: str, password: str, name: str) -> dict[str, Any]:
        """Set a known password on an existing user and make sure it is confirmed."""
        response = self._client.put(
            f"{self._base}/admin/users/{user_id}",
            headers=self._headers,
            json={
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            },
        )
        response.raise_for_status()
        return dict(response.json())

    def mark_onboarded(self, user_id: str, name: str, vertical: str) -> None:
        """Fill in what /onboarding would have written, so it can be skipped."""
        response = self._client.patch(
            f"{self._rest}/merchants",
            headers={**self._headers, "Prefer": "return=minimal"},
            params={"id": f"eq.{user_id}"},
            json={"name": name, "vertical": vertical, "onboarded": True},
        )
        response.raise_for_status()

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        """Sign in exactly as the browser does — anon key, password grant.

        This is the part worth having in the script. It proves the account is
        genuinely usable rather than merely created, and the token it returns is
        the only way to see which algorithm the project actually signs with.
        """
        response = self._client.post(
            f"{self._base}/token",
            headers={"apikey": self._anon_key, "Content-Type": "application/json"},
            params={"grant_type": "password"},
            json={"email": email, "password": password},
        )
        response.raise_for_status()
        return dict(response.json())


def _jwt_header(token: str) -> dict[str, Any]:
    segment = token.split(".")[0]
    padded = segment + "=" * (-len(segment) % 4)
    return dict(json.loads(base64.urlsafe_b64decode(padded)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument(
        "--onboarded",
        action="store_true",
        help="Mark the merchant onboarded so sign-in lands on /app instead of /onboarding.",
    )
    parser.add_argument("--vertical", choices=VERTICALS, default="d2c_beauty")
    args = parser.parse_args()

    _guard_environment()
    admin = Admin()

    existing = admin.find_user(args.email)
    if existing:
        user = admin.reset_user(str(existing["id"]), args.password, args.name)
        print(f"user already existed — password reset: {args.email}")
    else:
        user = admin.create_user(args.email, args.password, args.name)
        print(f"user created: {args.email}")

    user_id = str(user["id"])
    print(f"  merchant id: {user_id}")

    if args.onboarded:
        admin.mark_onboarded(user_id, args.name, args.vertical)
        print(f"  marked onboarded, vertical={args.vertical}")

    session = admin.sign_in(args.email, args.password)
    header = _jwt_header(session["access_token"])
    print("\nsign-in check: OK")
    print(f"  token alg: {header.get('alg')}   kid: {header.get('kid')}")
    print("\nSign in at http://localhost:3000/login")
    print(f"  email:    {args.email}")
    print(f"  password: {args.password}")


if __name__ == "__main__":
    main()
