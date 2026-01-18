#!/usr/bin/env python3

"""Generate MeiliSearch tasks for testing the Tasks Queue feature.

This script triggers various operations on a MeiliSearch instance to create
tasks in different states, useful for testing the task monitoring UI.

Usage:
    # Generate tasks on default instance
    python scripts/seed_tasks.py --url http://localhost:7700

    # Generate tasks with API key
    python scripts/seed_tasks.py --url http://localhost:7700 --api-key your-key

    # Generate more tasks
    python scripts/seed_tasks.py --url http://localhost:7700 --count 20
"""

import argparse
import random
import sys
import time
from datetime import datetime


def generate_tasks(url: str, api_key: str | None = None, count: int = 10) -> None:
    """Generate various tasks on a MeiliSearch instance."""
    try:
        import httpx
    except ImportError:
        print("Error: httpx is required. Install with: pip install httpx")
        sys.exit(1)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    client = httpx.Client(base_url=url, headers=headers, timeout=60.0)

    # Check connection
    try:
        response = client.get("/health")
        if response.status_code != 200:
            print(f"Error: Cannot connect to MeiliSearch at {url}")
            sys.exit(1)
        print(f"Connected to MeiliSearch at {url}")
    except httpx.HTTPError as e:
        print(f"Error connecting to MeiliSearch: {e}")
        sys.exit(1)

    # Get existing indexes
    try:
        response = client.get("/indexes")
        indexes = response.json().get("results", [])
        index_uids = [idx["uid"] for idx in indexes]
        if not index_uids:
            print(
                "No indexes found. Run 'make seed-instance' first to create test data."
            )
            sys.exit(1)
        print(f"Found indexes: {', '.join(index_uids)}")
    except Exception as e:
        print(f"Error fetching indexes: {e}")
        sys.exit(1)

    print(f"\nGenerating {count} tasks...")

    task_operations = [
        ("settings_update", update_settings),
        ("document_add", add_documents),
        ("document_delete", delete_documents),
    ]

    for i in range(count):
        index_uid = random.choice(index_uids)
        op_name, op_func = random.choice(task_operations)

        print(f"  [{i + 1}/{count}] {op_name} on '{index_uid}'...", end=" ")

        try:
            task_uid = op_func(client, index_uid)
            if task_uid:
                print(f"task #{task_uid}")
            else:
                print("done")
        except Exception as e:
            print(f"error: {e}")

        # Small delay to spread out tasks
        time.sleep(0.2)

    # Generate a few rapid-fire tasks to potentially have some in processing state
    print("\nGenerating rapid-fire tasks to create queue...")
    for i in range(5):
        index_uid = random.choice(index_uids)
        try:
            # Add small batches of documents quickly
            docs = [
                {"id": 100000 + i * 10 + j, "rapid_test": True, "batch": i}
                for j in range(10)
            ]
            response = client.post(f"/indexes/{index_uid}/documents", json=docs)
            task_info = response.json()
            print(f"  Rapid task #{task_info.get('taskUid', 'N/A')} on '{index_uid}'")
        except Exception as e:
            print(f"  Error: {e}")

    print("\nTask generation complete!")
    print("\nView tasks with:")
    print(f"  meiliscan tasks --url {url}")
    print(f"  meiliscan tasks --url {url} --watch")
    print(f"  meiliscan serve --url {url}  # Then visit http://localhost:8080/tasks")


def update_settings(client, index_uid: str) -> int | None:
    """Update settings on an index to create a settingsUpdate task."""
    # Fetch current settings
    response = client.get(f"/indexes/{index_uid}/settings")
    if response.status_code != 200:
        return None

    current_settings = response.json()

    # Make a minor change - toggle a stop word
    stop_words = current_settings.get("stopWords", [])
    test_word = "testword"

    if test_word in stop_words:
        stop_words = [w for w in stop_words if w != test_word]
    else:
        stop_words = stop_words + [test_word]

    response = client.patch(
        f"/indexes/{index_uid}/settings",
        json={"stopWords": stop_words},
    )

    if response.status_code == 202:
        return response.json().get("taskUid")
    return None


def add_documents(client, index_uid: str) -> int | None:
    """Add documents to create a documentAdditionOrUpdate task."""
    timestamp = int(datetime.now().timestamp() * 1000)

    # Generate random documents based on the index type
    if index_uid == "products":
        docs = [
            {
                "id": timestamp + i,
                "name": f"Test Product {timestamp + i}",
                "price": round(random.uniform(10, 500), 2),
                "category": random.choice(["Electronics", "Books", "Clothing"]),
                "test_data": True,
            }
            for i in range(random.randint(5, 20))
        ]
    elif index_uid == "users":
        docs = [
            {
                "id": timestamp + i,
                "email": f"testuser{timestamp + i}@example.com",
                "first_name": random.choice(["Test", "Demo", "Sample"]),
                "last_name": f"User{i}",
                "test_data": True,
            }
            for i in range(random.randint(3, 10))
        ]
    elif index_uid == "articles":
        docs = [
            {
                "id": timestamp + i,
                "title": f"Test Article {timestamp + i}",
                "content": "This is test content for task generation. " * 10,
                "author": "Test Author",
                "test_data": True,
            }
            for i in range(random.randint(2, 8))
        ]
    elif index_uid == "orders":
        docs = [
            {
                "id": timestamp + i,
                "order_id": f"ORD-TEST-{timestamp + i}",
                "total": round(random.uniform(50, 1000), 2),
                "status": random.choice(["pending", "processing", "shipped"]),
                "test_data": True,
            }
            for i in range(random.randint(5, 15))
        ]
    else:
        # Generic documents for unknown indexes
        docs = [
            {
                "id": timestamp + i,
                "name": f"Test Document {timestamp + i}",
                "test_data": True,
            }
            for i in range(random.randint(5, 10))
        ]

    response = client.post(f"/indexes/{index_uid}/documents", json=docs)

    if response.status_code == 202:
        return response.json().get("taskUid")
    return None


def delete_documents(client, index_uid: str) -> int | None:
    """Delete test documents to create a documentDeletion task."""
    # Delete documents marked as test_data
    response = client.post(
        f"/indexes/{index_uid}/documents/delete",
        json={"filter": "test_data = true"},
    )

    if response.status_code == 202:
        return response.json().get("taskUid")

    # If filter delete fails (maybe test_data not filterable), try deleting by IDs
    # Get some document IDs first
    response = client.get(f"/indexes/{index_uid}/documents?limit=5")
    if response.status_code == 200:
        docs = response.json().get("results", [])
        if docs:
            # Don't actually delete real data, just return None
            return None

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate MeiliSearch tasks for testing"
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://localhost:7700",
        help="MeiliSearch instance URL (default: http://localhost:7700)",
    )
    parser.add_argument(
        "--api-key",
        "-k",
        help="MeiliSearch API key",
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=10,
        help="Number of tasks to generate (default: 10)",
    )

    args = parser.parse_args()
    generate_tasks(args.url, args.api_key, args.count)


if __name__ == "__main__":
    main()
