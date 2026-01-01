#!/usr/bin/env python3
"""Generate mock MeiliSearch dump files or seed a live instance with test data.

This script creates realistic test data with intentional issues that the
MeiliSearch Analyzer can detect, making it useful for development and testing.

Usage:
    # Create a mock dump file
    python scripts/seed_data.py dump --output test-dump.dump

    # Seed a live MeiliSearch instance
    python scripts/seed_data.py seed --url http://localhost:7700

    # Seed with API key
    python scripts/seed_data.py seed --url http://localhost:7700 --api-key your-key

    # Clean up (delete all indexes from instance)
    python scripts/seed_data.py clean --url http://localhost:7700
"""

import argparse
import json
import random
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Sample data for generating realistic documents
PRODUCT_NAMES = [
    "Wireless Bluetooth Headphones",
    "Ergonomic Office Chair",
    "Mechanical Gaming Keyboard",
    "4K Ultra HD Monitor",
    "Portable Power Bank",
    "Smart Home Speaker",
    "Laptop Stand Adjustable",
    "USB-C Hub Multiport",
    "Noise Cancelling Earbuds",
    "LED Desk Lamp",
]

PRODUCT_CATEGORIES = ["Electronics", "Office", "Gaming", "Audio", "Accessories"]
PRODUCT_BRANDS = ["TechPro", "HomeMax", "GamerX", "SoundWave", "OfficePlus"]

USER_FIRST_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
USER_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]

ARTICLE_TITLES = [
    "Getting Started with MeiliSearch",
    "Advanced Search Techniques",
    "Optimizing Index Performance",
    "Understanding Ranking Rules",
    "Faceted Search Implementation",
    "Multi-tenancy Best Practices",
    "Typo Tolerance Configuration",
    "Stop Words and Synonyms Guide",
]

ARTICLE_CONTENT_SNIPPETS = [
    "MeiliSearch is a powerful, fast, open-source search engine...",
    "When configuring your search, consider the following best practices...",
    "Performance optimization starts with understanding your data structure...",
    "Ranking rules determine the order of search results...",
    "<p>This article contains <strong>HTML tags</strong> that should be stripped.</p>",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50,  # Very long text
]


def generate_products(count: int = 500) -> list[dict]:
    """Generate sample product documents with intentional issues."""
    products = []
    for i in range(count):
        product = {
            "id": i + 1,
            "product_id": f"PROD-{i+1:05d}",  # ID field that shouldn't be searchable
            "sku": f"SKU{random.randint(10000, 99999)}",
            "name": random.choice(PRODUCT_NAMES),
            "description": f"High-quality {random.choice(PRODUCT_NAMES).lower()} for everyday use.",
            "category": random.choice(PRODUCT_CATEGORIES),
            "brand": random.choice(PRODUCT_BRANDS),
            "price": round(random.uniform(9.99, 999.99), 2),
            "stock": random.randint(0, 1000),
            "rating": round(random.uniform(1.0, 5.0), 1),
            "reviews_count": random.randint(0, 500),
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
        }

        # Add some inconsistencies (D002 - inconsistent schema)
        if random.random() < 0.1:
            product["discount_percent"] = random.randint(5, 50)
        if random.random() < 0.15:
            product["warranty_months"] = random.randint(12, 36)
        if random.random() < 0.05:
            # Empty values (D006)
            product["description"] = ""
        if random.random() < 0.05:
            # Mixed types (D007) - sometimes string, sometimes int
            product["stock"] = str(product["stock"])
        if random.random() < 0.1:
            # Nested objects (D003)
            product["metadata"] = {
                "dimensions": {
                    "width": random.randint(10, 100),
                    "height": random.randint(10, 100),
                    "depth": random.randint(10, 100),
                },
                "weight": random.uniform(0.1, 10.0),
            }
        if random.random() < 0.1:
            # Large arrays (D004)
            product["tags"] = [f"tag-{j}" for j in range(random.randint(50, 100))]

        products.append(product)

    return products


def generate_users(count: int = 200) -> list[dict]:
    """Generate sample user documents."""
    users = []
    for i in range(count):
        user = {
            "id": i + 1,
            "user_id": f"USR-{i+1:06d}",
            "email": f"user{i+1}@example.com",
            "first_name": random.choice(USER_FIRST_NAMES),
            "last_name": random.choice(USER_LAST_NAMES),
            "age": random.randint(18, 80),
            "country": random.choice(["US", "UK", "DE", "FR", "JP", "AU"]),
            "signup_date": (datetime.now() - timedelta(days=random.randint(1, 1000))).isoformat(),
            "is_active": random.choice([True, False]),
            "orders_count": random.randint(0, 100),
        }
        users.append(user)

    return users


def generate_articles(count: int = 100) -> list[dict]:
    """Generate sample article documents with intentional issues."""
    articles = []
    for i in range(count):
        content = random.choice(ARTICLE_CONTENT_SNIPPETS)
        # Some articles have HTML (D005)
        if random.random() < 0.2:
            content = f"<div class='article'><h1>{random.choice(ARTICLE_TITLES)}</h1><p>{content}</p></div>"

        article = {
            "id": i + 1,
            "article_id": f"ART-{i+1:04d}",
            "title": random.choice(ARTICLE_TITLES),
            "content": content,
            "author": f"{random.choice(USER_FIRST_NAMES)} {random.choice(USER_LAST_NAMES)}",
            "published_at": (datetime.now() - timedelta(days=random.randint(1, 500))).isoformat(),
            "views": random.randint(0, 10000),
            "likes": random.randint(0, 500),
        }

        # Very long text (D008)
        if random.random() < 0.1:
            article["content"] = "This is a very detailed article. " * 1000

        articles.append(article)

    return articles


def generate_orders(count: int = 1000) -> list[dict]:
    """Generate sample order documents - large index for testing."""
    orders = []
    for i in range(count):
        order = {
            "id": i + 1,
            "order_id": f"ORD-{i+1:08d}",
            "user_id": f"USR-{random.randint(1, 200):06d}",
            "product_ids": [f"PROD-{random.randint(1, 500):05d}" for _ in range(random.randint(1, 5))],
            "total": round(random.uniform(10.0, 2000.0), 2),
            "status": random.choice(["pending", "processing", "shipped", "delivered", "cancelled"]),
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat(),
        }
        orders.append(order)

    return orders


# Index configurations with intentional issues for the analyzer to detect
INDEX_CONFIGS = {
    "products": {
        "primaryKey": "id",
        "settings": {
            # S001: Wildcard searchableAttributes (Critical)
            "searchableAttributes": ["*"],
            # S004: Empty filterableAttributes (Info)
            "filterableAttributes": [],
            "sortableAttributes": ["price", "rating", "created_at"],
            "displayedAttributes": ["*"],
            # S007: Default ranking rules (Info)
            "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
            # S006: No stop words (Suggestion)
            "stopWords": [],
            "synonyms": {},
            # S008: No distinct attribute (Suggestion)
            "distinctAttribute": None,
        },
        "documents": generate_products,
        "doc_count": 500,
    },
    "users": {
        "primaryKey": "id",
        "settings": {
            # S002: ID fields in searchableAttributes (Warning)
            "searchableAttributes": ["user_id", "email", "first_name", "last_name", "country"],
            # S003: Numeric fields in searchableAttributes (Suggestion)
            # age is numeric but searchable
            "filterableAttributes": ["country", "is_active", "age"],
            "sortableAttributes": ["signup_date", "orders_count"],
            "displayedAttributes": ["*"],
            "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_users,
        "doc_count": 200,
    },
    "articles": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["title", "content", "author"],
            "filterableAttributes": ["author"],
            "sortableAttributes": ["published_at", "views", "likes"],
            "displayedAttributes": ["*"],
            "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
            # Some stop words configured
            "stopWords": ["the", "a", "an"],
            "synonyms": {"article": ["post", "blog"]},
            "distinctAttribute": None,
            # S010: High pagination limit (Suggestion)
            "pagination": {"maxTotalHits": 50000},
        },
        "documents": generate_articles,
        "doc_count": 100,
    },
    "orders": {
        "primaryKey": "id",
        "settings": {
            # Has some good practices
            "searchableAttributes": ["order_id", "status"],
            "filterableAttributes": ["status", "user_id", "created_at"],
            "sortableAttributes": ["total", "created_at"],
            "displayedAttributes": ["id", "order_id", "total", "status", "created_at"],
            "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
            # S009: Very low pagination limit (Warning)
            "pagination": {"maxTotalHits": 50},
        },
        "documents": generate_orders,
        "doc_count": 1000,
    },
}


def create_dump_file(output_path: str) -> None:
    """Create a mock MeiliSearch dump file."""
    output_path = Path(output_path)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dump_name = f"dump-{timestamp}"

    with tempfile.TemporaryDirectory() as temp_dir:
        dump_dir = Path(temp_dir) / dump_name
        dump_dir.mkdir()

        # Create metadata.json
        metadata = {
            "dumpVersion": "V6",
            "dbVersion": "1.12.0",
            "dumpDate": datetime.now().isoformat(),
            "instanceUid": "test-instance-12345",
        }
        (dump_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # Create keys.json (empty)
        (dump_dir / "keys.json").write_text("[]")

        # Create tasks directory
        tasks_dir = dump_dir / "tasks"
        tasks_dir.mkdir()

        # Generate some task history (for B001 detection - settings after documents)
        tasks = []
        base_time = datetime.now() - timedelta(hours=24)
        task_id = 0

        for index_uid in INDEX_CONFIGS:
            # Document addition task (earlier)
            tasks.append({
                "uid": task_id,
                "indexUid": index_uid,
                "status": "succeeded",
                "type": "documentAdditionOrUpdate",
                "enqueuedAt": (base_time + timedelta(minutes=task_id)).isoformat(),
                "startedAt": (base_time + timedelta(minutes=task_id, seconds=1)).isoformat(),
                "finishedAt": (base_time + timedelta(minutes=task_id, seconds=5)).isoformat(),
            })
            task_id += 1

            # Settings update task (later) - triggers B001
            tasks.append({
                "uid": task_id,
                "indexUid": index_uid,
                "status": "succeeded",
                "type": "settingsUpdate",
                "enqueuedAt": (base_time + timedelta(minutes=task_id + 10)).isoformat(),
                "startedAt": (base_time + timedelta(minutes=task_id + 10, seconds=1)).isoformat(),
                "finishedAt": (base_time + timedelta(minutes=task_id + 10, seconds=2)).isoformat(),
            })
            task_id += 1

        # Add some failed tasks (for P001 detection)
        for i in range(5):
            tasks.append({
                "uid": task_id,
                "indexUid": "products",
                "status": "failed",
                "type": "documentAdditionOrUpdate",
                "error": {"message": "Simulated error", "code": "internal"},
                "enqueuedAt": (base_time + timedelta(minutes=task_id)).isoformat(),
                "startedAt": (base_time + timedelta(minutes=task_id, seconds=1)).isoformat(),
                "finishedAt": (base_time + timedelta(minutes=task_id, seconds=2)).isoformat(),
            })
            task_id += 1

        (tasks_dir / "queue.json").write_text(json.dumps(tasks, indent=2))

        # Create indexes directory
        indexes_dir = dump_dir / "indexes"
        indexes_dir.mkdir()

        for index_uid, config in INDEX_CONFIGS.items():
            index_dir = indexes_dir / index_uid
            index_dir.mkdir()

            # Index metadata
            index_metadata = {
                "uid": index_uid,
                "primaryKey": config["primaryKey"],
                "createdAt": (datetime.now() - timedelta(days=30)).isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            (index_dir / "metadata.json").write_text(json.dumps(index_metadata, indent=2))

            # Settings
            (index_dir / "settings.json").write_text(json.dumps(config["settings"], indent=2))

            # Documents (JSONL format)
            docs = config["documents"](config["doc_count"])
            with open(index_dir / "documents.jsonl", "w") as f:
                for doc in docs:
                    f.write(json.dumps(doc) + "\n")

            print(f"  Created index '{index_uid}' with {len(docs)} documents")

        # Create tar.gz archive
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(dump_dir, arcname=dump_name)

    print(f"\nDump file created: {output_path}")
    print(f"  Total size: {output_path.stat().st_size / 1024:.1f} KB")


def seed_instance(url: str, api_key: str | None = None) -> None:
    """Seed a live MeiliSearch instance with test data."""
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

    # Get version
    try:
        response = client.get("/version")
        version = response.json().get("pkgVersion", "unknown")
        print(f"MeiliSearch version: {version}")
    except Exception:
        pass

    print("\nCreating indexes and seeding data...")

    for index_uid, config in INDEX_CONFIGS.items():
        print(f"\n  Processing '{index_uid}'...")

        # Create/update index
        response = client.post("/indexes", json={
            "uid": index_uid,
            "primaryKey": config["primaryKey"],
        })

        if response.status_code not in [200, 201, 202]:
            # Index might already exist, try to get it
            response = client.get(f"/indexes/{index_uid}")
            if response.status_code != 200:
                print(f"    Error creating index: {response.text}")
                continue

        # Wait for index creation
        _wait_for_task(client, response)

        # Update settings
        response = client.patch(
            f"/indexes/{index_uid}/settings",
            json=config["settings"],
        )
        task_info = response.json()
        print(f"    Settings update task: {task_info.get('taskUid', 'N/A')}")
        _wait_for_task(client, response)

        # Add documents
        docs = config["documents"](config["doc_count"])
        response = client.post(
            f"/indexes/{index_uid}/documents",
            json=docs,
        )
        task_info = response.json()
        print(f"    Document addition task: {task_info.get('taskUid', 'N/A')}")
        print(f"    Adding {len(docs)} documents...")
        _wait_for_task(client, response)

        print(f"    Done!")

    print("\nSeeding complete!")
    print(f"\nYou can now analyze with:")
    print(f"  meilisearch-analyzer analyze --url {url}")
    print(f"  meilisearch-analyzer serve --url {url}")


def _wait_for_task(client: "httpx.Client", response: "httpx.Response") -> None:
    """Wait for a MeiliSearch task to complete."""
    import time

    if response.status_code not in [200, 201, 202]:
        return

    task_info = response.json()
    task_uid = task_info.get("taskUid")
    if not task_uid:
        return

    while True:
        response = client.get(f"/tasks/{task_uid}")
        if response.status_code != 200:
            break

        task = response.json()
        status = task.get("status")
        if status in ["succeeded", "failed", "canceled"]:
            if status == "failed":
                print(f"    Task failed: {task.get('error', {}).get('message', 'Unknown error')}")
            break

        time.sleep(0.5)


def clean_instance(url: str, api_key: str | None = None) -> None:
    """Delete all indexes from a MeiliSearch instance."""
    try:
        import httpx
    except ImportError:
        print("Error: httpx is required. Install with: pip install httpx")
        sys.exit(1)

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    client = httpx.Client(base_url=url, headers=headers, timeout=30.0)

    # Get all indexes
    try:
        response = client.get("/indexes")
        if response.status_code != 200:
            print(f"Error: Cannot connect to MeiliSearch at {url}")
            sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error connecting to MeiliSearch: {e}")
        sys.exit(1)

    indexes = response.json().get("results", [])
    if not indexes:
        print("No indexes found.")
        return

    print(f"Found {len(indexes)} indexes to delete:")
    for idx in indexes:
        uid = idx["uid"]
        print(f"  Deleting '{uid}'...")
        response = client.delete(f"/indexes/{uid}")
        _wait_for_task(client, response)

    print("\nAll indexes deleted.")


def main():
    parser = argparse.ArgumentParser(
        description="Generate mock MeiliSearch data for testing the analyzer"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Dump command
    dump_parser = subparsers.add_parser("dump", help="Create a mock dump file")
    dump_parser.add_argument(
        "--output", "-o",
        default="test-dump.dump",
        help="Output file path (default: test-dump.dump)",
    )

    # Seed command
    seed_parser = subparsers.add_parser("seed", help="Seed a live MeiliSearch instance")
    seed_parser.add_argument(
        "--url", "-u",
        required=True,
        help="MeiliSearch instance URL",
    )
    seed_parser.add_argument(
        "--api-key", "-k",
        help="MeiliSearch API key",
    )

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Delete all indexes from instance")
    clean_parser.add_argument(
        "--url", "-u",
        required=True,
        help="MeiliSearch instance URL",
    )
    clean_parser.add_argument(
        "--api-key", "-k",
        help="MeiliSearch API key",
    )

    args = parser.parse_args()

    if args.command == "dump":
        print("Creating mock dump file...")
        create_dump_file(args.output)
    elif args.command == "seed":
        seed_instance(args.url, args.api_key)
    elif args.command == "clean":
        clean_instance(args.url, args.api_key)


if __name__ == "__main__":
    main()
