"""Setup Rezolve Labs Knowledge Base and verify semantic search.

Reads the API key from REZOLVE_KEY environment variable (or .env),
creates the 'PS1 catalogue' Knowledge Base, uploads catalogue.csv,
polls until ready, saves the KB ID to .env, and performs a test search.
"""
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.rezolvelabs.com/api/v1"
CATALOGUE_PATH = Path(__file__).resolve().parent / "catalogue.csv"
ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_env_key() -> Optional[str]:
    """Retrieve REZOLVE_KEY from environment or local .env file."""
    key = os.environ.get("REZOLVE_KEY")
    if key:
        return key.strip()

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("REZOLVE_KEY="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
    return None


def save_kb_id_to_env(kb_id: str):
    """Save or update REZOLVE_KB_ID in .env without overwriting other variables."""
    lines: List[str] = []
    found = False

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("REZOLVE_KB_ID="):
                    lines.append(f"REZOLVE_KB_ID={kb_id}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"REZOLVE_KB_ID={kb_id}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    api_key = load_env_key()
    if not api_key:
        print("Error: REZOLVE_KEY environment variable is not set.", file=sys.stderr)
        print("Please set it in your environment or .env file before running.", file=sys.stderr)
        sys.exit(1)

    if not CATALOGUE_PATH.exists():
        print(f"Error: catalogue file not found at {CATALOGUE_PATH}", file=sys.stderr)
        sys.exit(1)

    headers = {
        "X-API-KEY": api_key,
    }

    # 1. Create Knowledge Base
    print("Creating Knowledge Base 'PS1 catalogue'...")
    kb_url = f"{BASE_URL}/developer-platform/knowledge-bases"
    try:
        resp = requests.post(
            kb_url,
            headers={**headers, "Content-Type": "application/json"},
            json={"name": "PS1 catalogue"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", "unknown")
        detail = e.response.text if getattr(e, "response", None) is not None else str(e)
        print(f"Failed to create Knowledge Base (status {status}): {detail}", file=sys.stderr)
        sys.exit(1)

    kb_json: Dict[str, Any] = resp.json()
    kb_id = kb_json.get("data", {}).get("id") or kb_json.get("id")
    if not kb_id:
        print(f"Error: Could not extract Knowledge Base ID from response: {kb_json}", file=sys.stderr)
        sys.exit(1)

    print(f"Knowledge Base created successfully. ID: {kb_id}")

    # 2. Upload catalogue.csv
    print(f"Uploading {CATALOGUE_PATH.name}...")
    upload_url = f"{BASE_URL}/developer-platform/knowledge-bases/{kb_id}/documents"
    try:
        with open(CATALOGUE_PATH, "rb") as f:
            files = {"file": (CATALOGUE_PATH.name, f, "text/csv")}
            resp = requests.post(upload_url, headers=headers, files=files, timeout=60)
            resp.raise_for_status()
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", "unknown")
        detail = e.response.text if getattr(e, "response", None) is not None else str(e)
        print(f"Failed to upload catalogue document (status {status}): {detail}", file=sys.stderr)
        sys.exit(1)

    doc_json: Dict[str, Any] = resp.json()
    doc_id = doc_json.get("data", {}).get("id") or doc_json.get("id")
    if not doc_id:
        print(f"Error: Could not extract document ID from response: {doc_json}", file=sys.stderr)
        sys.exit(1)

    print(f"Document uploaded. ID: {doc_id}. Polling status until 'ready'...")

    # 3. Poll document status
    doc_status_url = f"{BASE_URL}/developer-platform/knowledge-bases/{kb_id}/documents/{doc_id}"
    available_filters = None
    start_time = time.time()
    timeout_seconds = 180

    while True:
        try:
            resp = requests.get(doc_status_url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            doc_data = data.get("data") if isinstance(data.get("data"), dict) else data
            status = doc_data.get("status")

            if status == "ready":
                available_filters = doc_data.get("availableFilters") or data.get("availableFilters")
                break
            elif status in ("failed", "error"):
                error_msg = doc_data.get("error") or "Unknown error"
                print(f"Document processing failed: {error_msg}", file=sys.stderr)
                sys.exit(1)
            else:
                elapsed = int(time.time() - start_time)
                print(f"  Current status: {status} ({elapsed}s elapsed)...")
                time.sleep(3)

            if time.time() - start_time > timeout_seconds:
                print(f"Error: Timed out after {timeout_seconds}s waiting for document to be ready.", file=sys.stderr)
                sys.exit(1)

        except requests.RequestException as e:
            print(f"Polling warning: {e}. Retrying in 3 seconds...")
            time.sleep(3)

    print("\n" + "=" * 50)
    print(f"Knowledge Base ID: {kb_id}")
    print(f"Available Filters: {available_filters}")
    print("=" * 50)

    # 4. Save Knowledge Base ID to .env
    save_kb_id_to_env(kb_id)
    print("Saved Knowledge Base ID to .env")

    # 5. Run test search
    print("\nRunning test search for 'black running shoes'...")
    search_url = f"{BASE_URL}/product-discovery/search"
    search_payload = {
        "knowledgeBaseId": kb_id,
        "query": "black running shoes",
        "limit": 5,
    }

    try:
        resp = requests.post(
            search_url,
            headers={**headers, "Content-Type": "application/json"},
            json=search_payload,
            timeout=30,
        )
        resp.raise_for_status()
        search_res = resp.json()
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", "unknown")
        detail = e.response.text if getattr(e, "response", None) is not None else str(e)
        print(f"Test search failed (status {status}): {detail}", file=sys.stderr)
        sys.exit(1)

    # Extract returned items/product ids
    # Search response can be list in results, items, or data
    raw_results = (
        search_res.get("data", {}).get("results")
        if isinstance(search_res.get("data"), dict)
        else None
    )
    if raw_results is None:
        raw_results = (
            search_res.get("results")
            or search_res.get("data")
            or search_res.get("items")
            or []
        )

    product_ids = []
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, dict):
                pid = item.get("id") or item.get("product_id")
                if pid:
                    product_ids.append(pid)
            elif isinstance(item, str):
                product_ids.append(item)

    print("Test search completed successfully.")
    print(f"Returned product IDs ({len(product_ids)}): {product_ids}")


if __name__ == "__main__":
    main()
