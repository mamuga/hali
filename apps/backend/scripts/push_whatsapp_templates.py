"""Push HALI WhatsApp message templates to the Meta Cloud API.

Reads credentials from settings, submits every template JSON in
whatsapp_templates/, and reports the approval status Meta returns.

Idempotent: a template that already exists under the same name+language is
deleted and recreated, so re-running after editing the copy converges rather
than erroring on a duplicate.

Usage:
    poetry run python scripts/push_whatsapp_templates.py
    poetry run python scripts/push_whatsapp_templates.py --status-only
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

from hali.config import settings

TEMPLATES_DIR = Path(__file__).parent.parent / "whatsapp_templates"
GRAPH_BASE = f"https://graph.facebook.com/{settings.whatsapp_api_version}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }


def _templates_url() -> str:
    return f"{GRAPH_BASE}/{settings.whatsapp_business_account_id}/message_templates"


def list_existing_templates() -> dict[tuple[str, str], dict]:
    """Fetch templates currently on the WABA, keyed by (name, language).

    Keyed by both because one name legitimately exists once per language, and
    deleting by name alone would drop every localisation.
    """
    resp = httpx.get(_templates_url(), headers=_headers(), params={"limit": 100}, timeout=30)
    resp.raise_for_status()
    return {(t["name"], t["language"]): t for t in resp.json().get("data", [])}


def push_template(template: dict, existing: dict[tuple[str, str], dict]) -> dict:
    name, lang = template["name"], template["language"]

    if (name, lang) in existing:
        current = existing[(name, lang)]
        print(f"  '{name}' [{lang}] exists (status: {current.get('status')}) - deleting to recreate")
        del_resp = httpx.delete(
            _templates_url(),
            headers=_headers(),
            # hsm_id targets one localisation; name alone deletes all languages.
            params={"hsm_id": current["id"], "name": name},
            timeout=30,
        )
        if del_resp.status_code not in (200, 404):
            print(f"  WARNING: delete returned {del_resp.status_code}: {del_resp.text}")
        time.sleep(1)

    resp = httpx.post(_templates_url(), headers=_headers(), json=template, timeout=30)
    if resp.status_code >= 400:
        print(f"  FAILED ({resp.status_code}): {resp.text}")
        return {"name": name, "language": lang, "status": "failed", "error": resp.text}

    result = resp.json()
    print(f"  submitted: id={result.get('id')} status={result.get('status')}")
    return {
        "name": name,
        "language": lang,
        "id": result.get("id"),
        "status": result.get("status", "PENDING"),
    }


def poll_status(template_id: str, max_wait_s: int = 60) -> str:
    """Poll one template until it leaves PENDING or the wait budget runs out."""
    url = f"{GRAPH_BASE}/{template_id}"
    waited = 0
    while waited < max_wait_s:
        resp = httpx.get(
            url, headers=_headers(), params={"fields": "status,rejected_reason"}, timeout=30
        )
        data = resp.json()
        status = data.get("status", "UNKNOWN")
        if status != "PENDING":
            if status == "REJECTED":
                print(f"  REJECTED: {data.get('rejected_reason', 'no reason given')}")
            return status
        time.sleep(5)
        waited += 5
    return "PENDING (still queued - check WhatsApp Manager)"


def main() -> None:
    missing = [
        name
        for name, value in (
            ("WHATSAPP_TOKEN", settings.whatsapp_token),
            ("WHATSAPP_BUSINESS_ACCOUNT_ID", settings.whatsapp_business_account_id),
        )
        if not value
    ]
    if missing:
        print(f"Missing {', '.join(missing)} - aborting.")
        sys.exit(1)

    status_only = "--status-only" in sys.argv

    existing = list_existing_templates()
    print(f"Existing templates on WABA: {sorted(existing)}\n")

    if status_only:
        for (name, lang), template in sorted(existing.items()):
            print(f"{name} [{lang}]: {template.get('status')}")
        return

    results = []
    for path in sorted(TEMPLATES_DIR.glob("*.json")):
        template = json.loads(path.read_text())
        print(f"Pushing {path.name}...")
        result = push_template(template, existing)
        if result.get("id"):
            print("  polling approval status (up to 60s)...")
            result["final_status"] = poll_status(result["id"])
            print(f"  final status: {result['final_status']}\n")
        results.append(result)

    print("-- Summary ------------------------------")
    for r in results:
        print(f"  {r['name']} [{r['language']}]: {r.get('final_status', r.get('status'))}")

    if any(r.get("final_status", r.get("status")) in ("failed", "REJECTED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
