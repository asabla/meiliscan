#!/usr/bin/env python3

"""Generate mock MeiliSearch dump files or seed a live instance with test data.

This script creates realistic test data with intentional issues that the
Meiliscan can detect, making it useful for development and testing.

Usage:
    # Create a mock dump file (default size)
    python scripts/seed_data.py dump --output test-dump.dump

    # Create a large dump file for testing
    python scripts/seed_data.py dump --output test-dump.dump --size large

    # Create a minimal dump file for quick testing
    python scripts/seed_data.py dump --output test-dump.dump --size small

    # Scale all indexes to a total document count (distributed proportionally)
    python scripts/seed_data.py dump --output test-dump.dump --documents 100000

    # Seed only a specific index with a custom document count
    python scripts/seed_data.py dump --output test-dump.dump --index products --documents 50000

    # Seed a live MeiliSearch instance
    python scripts/seed_data.py seed --url http://localhost:7700

    # Seed with API key
    python scripts/seed_data.py seed --url http://localhost:7700 --api-key your-key

    # Seed a specific index on live instance
    python scripts/seed_data.py seed --url http://localhost:7700 --index products --documents 100000

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
    "Wireless Mouse",
    "Webcam HD 1080p",
    "External SSD 1TB",
    "Graphics Tablet",
    "Standing Desk Converter",
    "Mesh WiFi Router",
    "Smart Watch Fitness",
    "Portable Projector",
    "Microphone USB Condenser",
    "Ring Light LED",
]

PRODUCT_CATEGORIES = [
    "Electronics",
    "Office",
    "Gaming",
    "Audio",
    "Accessories",
    "Home",
    "Computing",
    "Mobile",
]
PRODUCT_BRANDS = [
    "TechPro",
    "HomeMax",
    "GamerX",
    "SoundWave",
    "OfficePlus",
    "SmartLife",
    "ProGear",
    "UltraTech",
]

USER_FIRST_NAMES = [
    "Alice",
    "Bob",
    "Charlie",
    "Diana",
    "Eve",
    "Frank",
    "Grace",
    "Henry",
    "Ivy",
    "Jack",
    "Kate",
    "Leo",
    "Mia",
    "Noah",
    "Olivia",
    "Peter",
    "Quinn",
    "Rachel",
    "Sam",
    "Tina",
    "Uma",
    "Victor",
    "Wendy",
    "Xavier",
]
USER_LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Anderson",
    "Taylor",
    "Thomas",
    "Moore",
]

# PII patterns for testing sensitive data detection
SAMPLE_EMAILS = [
    "john.doe@company.com",
    "jane.smith@example.org",
    "admin@internal.net",
    "support@helpdesk.io",
    "user123@mail.com",
    "contact@business.co",
]

SAMPLE_PHONES = [
    "+1-555-123-4567",
    "1-800-555-0199",
    "(555) 987-6543",
    "+44 20 7946 0958",
    "+49 30 12345678",
    "+81 3-1234-5678",
]

SAMPLE_SSN_LIKE = [
    "123-45-6789",
    "987-65-4321",
    "555-12-3456",
]

SAMPLE_CREDIT_CARDS = [
    "4111-1111-1111-1111",
    "5500-0000-0000-0004",
    "3400-0000-0000-009",
]

SAMPLE_IP_ADDRESSES = [
    "192.168.1.100",
    "10.0.0.50",
    "172.16.0.25",
    "203.0.113.42",
]

ARTICLE_TITLES = [
    "Getting Started with MeiliSearch",
    "Advanced Search Techniques",
    "Optimizing Index Performance",
    "Understanding Ranking Rules",
    "Faceted Search Implementation",
    "Multi-tenancy Best Practices",
    "Typo Tolerance Configuration",
    "Stop Words and Synonyms Guide",
    "Building Real-time Search",
    "Search Analytics Deep Dive",
    "Geo Search Implementation",
    "Document Schema Best Practices",
]

ARTICLE_CONTENT_SNIPPETS = [
    "MeiliSearch is a powerful, fast, open-source search engine...",
    "When configuring your search, consider the following best practices...",
    "Performance optimization starts with understanding your data structure...",
    "Ranking rules determine the order of search results...",
    "<p>This article contains <strong>HTML tags</strong> that should be stripped.</p>",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50,  # Very long text
    "Search relevancy is critical for user experience. Learn how to tune...",
    "Faceted navigation allows users to filter results by category...",
]

# Size presets for dump generation
SIZE_PRESETS = {
    "small": {
        "products": 50,
        "users": 20,
        "articles": 10,
        "orders": 100,
        "locations": 10,
        "events": 20,
        "reviews": 30,
        "categories": 10,
        "tags": 20,
        "logs": 50,
        "notifications": 20,
        "inventory": 40,
        "analytics": 100,
        "customers": 30,
        "employees": 10,
        "support_tickets": 20,
        "knowledge_base": 5,
    },
    "medium": {
        "products": 500,
        "users": 200,
        "articles": 100,
        "orders": 1000,
        "locations": 50,
        "events": 100,
        "reviews": 300,
        "categories": 50,
        "tags": 100,
        "logs": 500,
        "notifications": 200,
        "inventory": 400,
        "analytics": 1000,
        "customers": 500,
        "employees": 50,
        "support_tickets": 200,
        "knowledge_base": 20,
    },
    "large": {
        "products": 2000,
        "users": 1000,
        "articles": 500,
        "orders": 5000,
        "locations": 200,
        "events": 500,
        "reviews": 2000,
        "categories": 200,
        "tags": 500,
        "logs": 3000,
        "notifications": 1000,
        "inventory": 2000,
        "analytics": 5000,
        "customers": 2000,
        "employees": 200,
        "support_tickets": 1000,
        "knowledge_base": 50,
    },
}


def generate_products(count: int = 500) -> list[dict]:
    """Generate sample product documents with intentional issues."""
    products = []
    for i in range(count):
        product = {
            "id": i + 1,
            "product_id": f"PROD-{i + 1:05d}",  # ID field that shouldn't be searchable
            "sku": f"SKU{random.randint(10000, 99999)}",
            "name": random.choice(PRODUCT_NAMES),
            "description": f"High-quality {random.choice(PRODUCT_NAMES).lower()} for everyday use.",
            "category": random.choice(PRODUCT_CATEGORIES),
            "brand": random.choice(PRODUCT_BRANDS),
            "price": round(random.uniform(9.99, 999.99), 2),
            "stock": random.randint(0, 1000),
            "rating": round(random.uniform(1.0, 5.0), 1),
            "reviews_count": random.randint(0, 500),
            "created_at": (
                datetime.now() - timedelta(days=random.randint(1, 365))
            ).isoformat(),
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

        # D001: Large documents - add verbose product descriptions (~15KB+)
        if random.random() < 0.08:
            # Generate a very detailed product specification
            specs = []
            for _ in range(50):
                specs.append(
                    {
                        "attribute": f"spec_{random.randint(1, 100)}",
                        "value": "Detailed specification value " * 20,
                        "unit": random.choice(["mm", "kg", "watts", "lumens", "Hz"]),
                    }
                )
            product["detailed_specifications"] = specs
            product["full_description"] = (
                "This is an extremely detailed product description. " * 200
            )
            product["user_manual_excerpt"] = (
                "Installation instructions and safety guidelines. " * 150
            )

        products.append(product)

    return products


def generate_users(count: int = 200) -> list[dict]:
    """Generate sample user documents."""
    users = []
    for i in range(count):
        user = {
            "id": i + 1,
            "user_id": f"USR-{i + 1:06d}",
            "email": f"user{i + 1}@example.com",
            "first_name": random.choice(USER_FIRST_NAMES),
            "last_name": random.choice(USER_LAST_NAMES),
            "age": random.randint(18, 80),
            "country": random.choice(["US", "UK", "DE", "FR", "JP", "AU"]),
            "signup_date": (
                datetime.now() - timedelta(days=random.randint(1, 1000))
            ).isoformat(),
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
            "article_id": f"ART-{i + 1:04d}",
            "title": random.choice(ARTICLE_TITLES),
            "content": content,
            "author": f"{random.choice(USER_FIRST_NAMES)} {random.choice(USER_LAST_NAMES)}",
            "published_at": (
                datetime.now() - timedelta(days=random.randint(1, 500))
            ).isoformat(),
            "views": random.randint(0, 10000),
            "likes": random.randint(0, 500),
        }

        # Very long text (D008)
        if random.random() < 0.1:
            article["content"] = "This is a very detailed article. " * 1000

        # D001: Large documents - create comprehensive articles (~20KB+)
        if random.random() < 0.1:
            # Generate a full-length article with multiple sections
            sections = []
            for s in range(10):
                sections.append(
                    {
                        "heading": f"Section {s + 1}: {random.choice(ARTICLE_TITLES)}",
                        "content": "In-depth analysis and explanation of this topic. "
                        * 100,
                        "code_examples": [
                            f"# Example {e}\n" + "print('code sample')\n" * 20
                            for e in range(5)
                        ],
                    }
                )
            article["sections"] = sections
            article["full_content"] = (
                "Comprehensive guide covering all aspects of this topic. " * 300
            )
            article["references"] = [
                {"title": f"Reference {r}", "url": f"https://example.com/ref/{r}"}
                for r in range(20)
            ]
            article["revision_history"] = [
                {
                    "version": f"1.{v}",
                    "date": (datetime.now() - timedelta(days=v * 30)).isoformat(),
                    "changes": "Updated content and fixed issues. " * 10,
                }
                for v in range(15)
            ]

        articles.append(article)

    return articles


def generate_orders(count: int = 1000) -> list[dict]:
    """Generate sample order documents - large index for testing."""
    orders = []
    for i in range(count):
        order = {
            "id": i + 1,
            "order_id": f"ORD-{i + 1:08d}",
            "user_id": f"USR-{random.randint(1, 200):06d}",
            "product_ids": [
                f"PROD-{random.randint(1, 500):05d}"
                for _ in range(random.randint(1, 5))
            ],
            "total": round(random.uniform(10.0, 2000.0), 2),
            "status": random.choice(
                ["pending", "processing", "shipped", "delivered", "cancelled"]
            ),
            "created_at": (
                datetime.now() - timedelta(days=random.randint(1, 365))
            ).isoformat(),
        }
        orders.append(order)

    return orders


def generate_locations(count: int = 50) -> list[dict]:
    """Generate sample location documents for D011, D012, D013 testing."""
    locations = []

    # Sample cities with coordinates
    cities = [
        ("New York", 40.7128, -74.0060),
        ("Los Angeles", 34.0522, -118.2437),
        ("Chicago", 41.8781, -87.6298),
        ("Houston", 29.7604, -95.3698),
        ("Phoenix", 33.4484, -112.0740),
        ("Philadelphia", 39.9526, -75.1652),
        ("San Antonio", 29.4241, -98.4936),
        ("San Diego", 32.7157, -117.1611),
        ("Dallas", 32.7767, -96.7970),
        ("San Jose", 37.3382, -121.8863),
        ("Montreal", 45.5017, -73.5673),
        ("Toronto", 43.6532, -79.3832),
        ("Vancouver", 49.2827, -123.1207),
        ("London", 51.5074, -0.1278),
        ("Paris", 48.8566, 2.3522),
        ("Berlin", 52.5200, 13.4050),
        ("Tokyo", 35.6762, 139.6503),
        ("Sydney", -33.8688, 151.2093),
    ]

    for i in range(count):
        city_name, base_lat, base_lng = random.choice(cities)
        # Add small random offset
        lat = base_lat + random.uniform(-0.1, 0.1)
        lng = base_lng + random.uniform(-0.1, 0.1)

        location = {
            "id": i + 1,
            "name": f"{city_name} Location #{i + 1}",
            "type": random.choice(["store", "warehouse", "office", "restaurant"]),
            # D012: Geo coordinates as separate lat/lng fields (should trigger suggestion)
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            # D013: Date strings (should trigger suggestion for sorting)
            "opened_at": (
                datetime.now() - timedelta(days=random.randint(30, 1000))
            ).strftime("%Y-%m-%d"),
            "last_inspection": (
                datetime.now() - timedelta(days=random.randint(1, 180))
            ).isoformat(),
            # D011: Arrays of objects (should trigger warning if filterable)
            "operating_hours": [
                {"day": "Monday", "open": "09:00", "close": "18:00"},
                {"day": "Tuesday", "open": "09:00", "close": "18:00"},
                {"day": "Wednesday", "open": "09:00", "close": "18:00"},
                {"day": "Thursday", "open": "09:00", "close": "18:00"},
                {"day": "Friday", "open": "09:00", "close": "17:00"},
            ],
            "rating": round(random.uniform(3.0, 5.0), 1),
            "reviews_count": random.randint(10, 500),
        }

        # Some locations have contact info array of objects
        if random.random() < 0.5:
            location["contacts"] = [
                {
                    "name": f"Manager {i}",
                    "phone": f"+1-555-{random.randint(1000, 9999)}",
                },
                {"name": f"Support {i}", "email": f"support{i}@example.com"},
            ]

        locations.append(location)

    return locations


def generate_events(count: int = 100) -> list[dict]:
    """Generate sample event documents for D012 (nested geo) and D013 testing."""
    events = []

    event_types = ["conference", "meetup", "workshop", "concert", "exhibition"]

    for i in range(count):
        lat = round(random.uniform(25.0, 50.0), 6)
        lng = round(random.uniform(-125.0, -70.0), 6)

        event = {
            "id": i + 1,
            "title": f"Event #{i + 1}: {random.choice(event_types).title()}",
            "description": f"Join us for this amazing {random.choice(event_types)}!",
            "type": random.choice(event_types),
            # D012: Nested location object (should trigger suggestion)
            "venue": {
                "name": f"Venue {i + 1}",
                "address": f"{random.randint(100, 9999)} Main Street",
                "coordinates": {
                    "latitude": lat,
                    "longitude": lng,
                },
            },
            # D013: Multiple date string formats
            "event_date": (
                datetime.now() + timedelta(days=random.randint(1, 180))
            ).strftime("%Y-%m-%d"),
            "start_time": (
                datetime.now() + timedelta(days=random.randint(1, 180))
            ).isoformat(),
            "registration_deadline": (
                datetime.now() + timedelta(days=random.randint(1, 30))
            ).strftime("%m/%d/%Y"),  # US format
            "capacity": random.randint(50, 500),
            "registered": random.randint(10, 200),
            "price": round(random.uniform(0, 200.0), 2),
        }

        # Some events have speakers (array of objects)
        if random.random() < 0.6:
            event["speakers"] = [
                {
                    "name": f"Speaker {j}",
                    "topic": f"Topic {j}",
                    "bio": f"Expert in field {j}",
                }
                for j in range(random.randint(1, 5))
            ]

        events.append(event)

    return events


def generate_reviews(count: int = 300) -> list[dict]:
    """Generate sample review documents."""
    reviews = []
    sentiments = ["positive", "neutral", "negative"]

    for i in range(count):
        review = {
            "id": i + 1,
            "review_id": f"REV-{i + 1:06d}",
            "product_id": f"PROD-{random.randint(1, 500):05d}",
            "user_id": f"USR-{random.randint(1, 200):06d}",
            "title": f"Review for product {random.randint(1, 500)}",
            "content": f"This is a {'great' if random.random() > 0.3 else 'disappointing'} product. "
            * random.randint(1, 5),
            "rating": random.randint(1, 5),
            "sentiment": random.choice(sentiments),
            "helpful_votes": random.randint(0, 100),
            "verified_purchase": random.choice([True, False]),
            "created_at": (
                datetime.now() - timedelta(days=random.randint(1, 365))
            ).isoformat(),
        }
        reviews.append(review)

    return reviews


def generate_categories(count: int = 50) -> list[dict]:
    """Generate sample category documents."""
    categories = []
    parent_categories = ["Electronics", "Clothing", "Home", "Sports", "Books", "Food"]

    for i in range(count):
        category = {
            "id": i + 1,
            "category_id": f"CAT-{i + 1:04d}",
            "name": f"Category {i + 1}",
            "slug": f"category-{i + 1}",
            "parent": random.choice(parent_categories)
            if random.random() > 0.3
            else None,
            "level": random.randint(1, 3),
            "product_count": random.randint(0, 500),
            "is_active": random.choice([True, True, True, False]),  # 75% active
        }
        categories.append(category)

    return categories


def generate_tags(count: int = 100) -> list[dict]:
    """Generate sample tag documents."""
    tags = []
    tag_types = ["product", "article", "user", "system"]

    for i in range(count):
        tag = {
            "id": i + 1,
            "tag_id": f"TAG-{i + 1:05d}",
            "name": f"tag-{i + 1}",
            "display_name": f"Tag {i + 1}",
            "type": random.choice(tag_types),
            "usage_count": random.randint(0, 1000),
            "created_at": (
                datetime.now() - timedelta(days=random.randint(1, 500))
            ).isoformat(),
        }
        tags.append(tag)

    return tags


def generate_logs(count: int = 500) -> list[dict]:
    """Generate sample log documents."""
    logs = []
    log_levels = ["debug", "info", "warning", "error", "critical"]
    services = ["api", "worker", "scheduler", "indexer", "search"]

    for i in range(count):
        log = {
            "id": i + 1,
            "log_id": f"LOG-{i + 1:08d}",
            "timestamp": (
                datetime.now() - timedelta(hours=random.randint(1, 168))
            ).isoformat(),
            "level": random.choice(log_levels),
            "service": random.choice(services),
            "message": f"Log message {i + 1}: {'Operation completed successfully' if random.random() > 0.2 else 'Error occurred during processing'}",
            "request_id": f"req-{random.randint(10000, 99999)}",
            "user_id": f"USR-{random.randint(1, 200):06d}"
            if random.random() > 0.3
            else None,
            "duration_ms": random.randint(1, 5000),
        }
        logs.append(log)

    return logs


def generate_notifications(count: int = 200) -> list[dict]:
    """Generate sample notification documents."""
    notifications = []
    notification_types = ["email", "push", "sms", "in_app"]
    statuses = ["pending", "sent", "delivered", "failed", "read"]

    for i in range(count):
        notification = {
            "id": i + 1,
            "notification_id": f"NOTIF-{i + 1:06d}",
            "user_id": f"USR-{random.randint(1, 200):06d}",
            "type": random.choice(notification_types),
            "title": f"Notification {i + 1}",
            "message": f"This is notification message {i + 1}",
            "status": random.choice(statuses),
            "created_at": (
                datetime.now() - timedelta(hours=random.randint(1, 72))
            ).isoformat(),
            "sent_at": (
                datetime.now() - timedelta(hours=random.randint(0, 71))
            ).isoformat()
            if random.random() > 0.2
            else None,
        }
        notifications.append(notification)

    return notifications


def generate_inventory(count: int = 400) -> list[dict]:
    """Generate sample inventory documents."""
    inventory = []
    warehouses = ["WH-EAST", "WH-WEST", "WH-CENTRAL", "WH-SOUTH"]

    for i in range(count):
        item = {
            "id": i + 1,
            "inventory_id": f"INV-{i + 1:06d}",
            "product_id": f"PROD-{random.randint(1, 500):05d}",
            "warehouse": random.choice(warehouses),
            "quantity": random.randint(0, 1000),
            "reserved": random.randint(0, 50),
            "reorder_point": random.randint(10, 100),
            "last_restocked": (
                datetime.now() - timedelta(days=random.randint(1, 60))
            ).isoformat(),
        }
        inventory.append(item)

    return inventory


def generate_analytics(count: int = 1000) -> list[dict]:
    """Generate sample analytics/metrics documents."""
    analytics = []
    metrics = ["page_view", "click", "conversion", "signup", "purchase"]
    sources = ["organic", "paid", "social", "email", "direct"]

    for i in range(count):
        record = {
            "id": i + 1,
            "event_id": f"EVT-{i + 1:08d}",
            "metric": random.choice(metrics),
            "source": random.choice(sources),
            "value": random.randint(1, 100),
            "session_id": f"sess-{random.randint(100000, 999999)}",
            "user_id": f"USR-{random.randint(1, 200):06d}"
            if random.random() > 0.4
            else None,
            "timestamp": (
                datetime.now() - timedelta(hours=random.randint(1, 168))
            ).isoformat(),
            "page": f"/page-{random.randint(1, 50)}",
            # Add IP address for PII detection testing
            "ip_address": random.choice(SAMPLE_IP_ADDRESSES)
            if random.random() > 0.5
            else None,
        }
        analytics.append(record)

    return analytics


def generate_customers(count: int = 500) -> list[dict]:
    """Generate sample customer documents with PII data for sensitive data detection testing.

    This index intentionally contains various forms of PII to test the --detect-sensitive flag:
    - Email addresses
    - Phone numbers
    - Social Security Number-like patterns
    - Credit card-like patterns
    - Physical addresses
    - Date of birth
    - IP addresses
    """
    customers = []
    countries = ["US", "UK", "DE", "FR", "JP", "AU", "CA", "NL", "SE", "NO"]
    membership_tiers = ["bronze", "silver", "gold", "platinum"]

    street_names = [
        "Main St",
        "Oak Ave",
        "Park Rd",
        "Broadway",
        "Elm St",
        "1st Ave",
        "2nd St",
    ]
    cities = [
        "New York",
        "Los Angeles",
        "Chicago",
        "Houston",
        "Phoenix",
        "London",
        "Berlin",
        "Paris",
        "Tokyo",
        "Sydney",
    ]

    for i in range(count):
        first_name = random.choice(USER_FIRST_NAMES)
        last_name = random.choice(USER_LAST_NAMES)

        customer = {
            "id": i + 1,
            "customer_id": f"CUST-{i + 1:06d}",
            # PII: Full name
            "full_name": f"{first_name} {last_name}",
            "first_name": first_name,
            "last_name": last_name,
            # PII: Email
            "email": f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}@example.com",
            # PII: Phone number
            "phone": random.choice(SAMPLE_PHONES),
            # PII: Physical address
            "address": {
                "street": f"{random.randint(100, 9999)} {random.choice(street_names)}",
                "city": random.choice(cities),
                "state": f"ST-{random.randint(1, 50)}",
                "zip_code": f"{random.randint(10000, 99999)}",
                "country": random.choice(countries),
            },
            # PII: Date of birth
            "date_of_birth": (
                datetime.now()
                - timedelta(days=random.randint(6570, 25550))  # 18-70 years old
            ).strftime("%Y-%m-%d"),
            # Membership info
            "membership_tier": random.choice(membership_tiers),
            "loyalty_points": random.randint(0, 50000),
            "signup_date": (
                datetime.now() - timedelta(days=random.randint(1, 1000))
            ).isoformat(),
            "last_purchase_date": (
                datetime.now() - timedelta(days=random.randint(1, 180))
            ).isoformat()
            if random.random() > 0.2
            else None,
            "total_spent": round(random.uniform(0, 10000.0), 2),
            "orders_count": random.randint(0, 100),
            "is_verified": random.choice([True, True, True, False]),
            "marketing_consent": random.choice([True, False]),
        }

        # Add SSN-like field for some customers (testing sensitive detection)
        if random.random() < 0.2:
            customer["tax_id"] = random.choice(SAMPLE_SSN_LIKE)

        # Add credit card (masked) for some customers
        if random.random() < 0.15:
            customer["payment_method_last4"] = (
                f"**** **** **** {random.randint(1000, 9999)}"
            )

        # Add IP address for some customers
        if random.random() < 0.3:
            customer["last_login_ip"] = random.choice(SAMPLE_IP_ADDRESSES)

        customers.append(customer)

    return customers


def generate_employees(count: int = 50) -> list[dict]:
    """Generate sample employee documents with HR-related PII.

    This index contains employment-related sensitive data:
    - Social Security Numbers
    - Salary information
    - Personal contact details
    - Emergency contacts
    - Bank account info patterns
    """
    employees = []
    departments = [
        "Engineering",
        "Sales",
        "Marketing",
        "HR",
        "Finance",
        "Operations",
        "Support",
        "Legal",
    ]
    job_titles = [
        "Software Engineer",
        "Senior Developer",
        "Product Manager",
        "Designer",
        "Sales Representative",
        "Account Manager",
        "HR Specialist",
        "Financial Analyst",
        "Operations Manager",
        "Support Agent",
        "Marketing Coordinator",
        "Legal Counsel",
    ]
    employment_types = ["full-time", "part-time", "contractor", "intern"]

    for i in range(count):
        first_name = random.choice(USER_FIRST_NAMES)
        last_name = random.choice(USER_LAST_NAMES)

        employee = {
            "id": i + 1,
            "employee_id": f"EMP-{i + 1:05d}",
            # PII: Full name
            "full_name": f"{first_name} {last_name}",
            "first_name": first_name,
            "last_name": last_name,
            # PII: Work email
            "work_email": f"{first_name.lower()}.{last_name.lower()}@company.com",
            # PII: Personal email
            "personal_email": f"{first_name.lower()}{random.randint(1, 99)}@gmail.com",
            # PII: Phone numbers
            "work_phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
            "personal_phone": random.choice(SAMPLE_PHONES),
            # PII: SSN
            "ssn": random.choice(SAMPLE_SSN_LIKE),
            # PII: Salary
            "salary": random.randint(40000, 250000),
            "salary_currency": "USD",
            # PII: Bank routing (pattern)
            "bank_routing": f"{random.randint(100000000, 999999999)}",
            "bank_account_last4": f"****{random.randint(1000, 9999)}",
            # Employment info
            "department": random.choice(departments),
            "job_title": random.choice(job_titles),
            "employment_type": random.choice(employment_types),
            "manager_id": f"EMP-{random.randint(1, max(1, i)):05d}" if i > 5 else None,
            "hire_date": (
                datetime.now() - timedelta(days=random.randint(30, 3650))
            ).strftime("%Y-%m-%d"),
            # PII: Date of birth
            "date_of_birth": (
                datetime.now()
                - timedelta(days=random.randint(7300, 23725))  # 20-65 years old
            ).strftime("%Y-%m-%d"),
            # PII: Emergency contact
            "emergency_contact": {
                "name": f"{random.choice(USER_FIRST_NAMES)} {random.choice(USER_LAST_NAMES)}",
                "relationship": random.choice(
                    ["spouse", "parent", "sibling", "friend"]
                ),
                "phone": random.choice(SAMPLE_PHONES),
            },
            "is_active": random.choice([True, True, True, True, False]),
            "vacation_days_remaining": random.randint(0, 25),
        }

        employees.append(employee)

    return employees


def generate_support_tickets(count: int = 200) -> list[dict]:
    """Generate sample support ticket documents.

    This index tests:
    - Long text content
    - Various status workflows
    - Nested conversation threads
    - PII in ticket content (customer info mentioned)
    """
    tickets = []
    statuses = [
        "open",
        "in_progress",
        "pending_customer",
        "resolved",
        "closed",
        "escalated",
    ]
    priorities = ["low", "medium", "high", "critical"]
    categories = [
        "billing",
        "technical",
        "account",
        "product",
        "shipping",
        "refund",
        "general",
    ]
    channels = ["email", "chat", "phone", "web_form", "social_media"]

    issue_templates = [
        "I can't log into my account since yesterday",
        "My order #{order_id} hasn't arrived yet",
        "I was charged twice for my subscription",
        "The product stopped working after {days} days",
        "I need help setting up the integration",
        "Request to cancel my subscription",
        "Question about pricing for enterprise plan",
        "Bug report: {feature} not working as expected",
        "Feature request: Add support for {feature}",
        "Urgent: Production system is down",
    ]

    response_templates = [
        "Thank you for contacting support. We're looking into this.",
        "I've escalated this to our engineering team.",
        "Could you please provide more details about the issue?",
        "This has been resolved. Please let us know if you need anything else.",
        "We apologize for the inconvenience. Here's what we can do...",
    ]

    for i in range(count):
        created_at = datetime.now() - timedelta(days=random.randint(1, 180))
        status = random.choice(statuses)

        # Generate conversation thread
        num_messages = random.randint(1, 8)
        conversation = []
        for j in range(num_messages):
            is_customer = j % 2 == 0
            message_time = created_at + timedelta(hours=j * random.randint(1, 24))
            conversation.append(
                {
                    "message_id": f"MSG-{i + 1:06d}-{j + 1}",
                    "sender_type": "customer" if is_customer else "agent",
                    "sender_id": f"CUST-{random.randint(1, 500):06d}"
                    if is_customer
                    else f"AGENT-{random.randint(1, 20):03d}",
                    "content": random.choice(
                        issue_templates if is_customer else response_templates
                    )
                    .replace("{order_id}", str(random.randint(10000, 99999)))
                    .replace("{days}", str(random.randint(1, 30)))
                    .replace(
                        "{feature}",
                        random.choice(["search", "export", "import", "dashboard"]),
                    ),
                    "timestamp": message_time.isoformat(),
                }
            )

        ticket = {
            "id": i + 1,
            "ticket_id": f"TKT-{i + 1:06d}",
            "subject": random.choice(issue_templates)
            .replace("{order_id}", str(random.randint(10000, 99999)))
            .replace("{days}", str(random.randint(1, 30)))
            .replace("{feature}", random.choice(["search", "export", "dashboard"])),
            "description": "Detailed description of the issue. "
            * random.randint(2, 10),
            "status": status,
            "priority": random.choice(priorities),
            "category": random.choice(categories),
            "channel": random.choice(channels),
            "customer_id": f"CUST-{random.randint(1, 500):06d}",
            # PII: Customer email in ticket
            "customer_email": f"{random.choice(USER_FIRST_NAMES).lower()}.{random.choice(USER_LAST_NAMES).lower()}@example.com",
            "assigned_agent_id": f"AGENT-{random.randint(1, 20):03d}"
            if status != "open"
            else None,
            "conversation": conversation,
            "tags": random.sample(
                ["urgent", "vip", "bug", "feature", "billing", "followup"],
                k=random.randint(0, 3),
            ),
            "created_at": created_at.isoformat(),
            "updated_at": (
                created_at + timedelta(hours=random.randint(1, 72))
            ).isoformat(),
            "resolved_at": (
                created_at + timedelta(hours=random.randint(24, 168))
            ).isoformat()
            if status in ["resolved", "closed"]
            else None,
            "first_response_time_hours": round(random.uniform(0.5, 24.0), 1),
            "resolution_time_hours": round(random.uniform(1.0, 168.0), 1)
            if status in ["resolved", "closed"]
            else None,
            "satisfaction_rating": random.randint(1, 5)
            if status == "closed" and random.random() > 0.3
            else None,
        }

        tickets.append(ticket)

    return tickets


def generate_knowledge_base(count: int = 20) -> list[dict]:
    """Generate sample knowledge base documents that are intentionally large (D001).

    This index is designed to trigger the large document detection (D001) by
    containing documentation-style content that exceeds the recommended 10KB average.
    Each document is approximately 15-50KB to ensure detection.
    """
    kb_articles = []

    doc_types = [
        "API Reference",
        "User Guide",
        "Installation Manual",
        "Troubleshooting Guide",
        "Best Practices",
        "Architecture Overview",
        "Migration Guide",
        "Security Guidelines",
        "Performance Tuning",
        "FAQ",
    ]

    topics = [
        "Authentication",
        "Database Configuration",
        "Search Optimization",
        "Indexing",
        "API Integration",
        "Webhooks",
        "Rate Limiting",
        "Caching",
        "Monitoring",
        "Backup & Recovery",
        "Multi-tenancy",
        "Data Import",
        "Filtering",
        "Sorting",
        "Faceted Search",
    ]

    for i in range(count):
        doc_type = random.choice(doc_types)
        topic = random.choice(topics)

        # Generate multiple large sections to ensure document exceeds 10KB
        sections = []
        num_sections = random.randint(8, 15)
        for s in range(num_sections):
            section_content = (
                f"This section covers important details about {topic}. "
                "Understanding this concept is crucial for proper implementation. "
                "The following paragraphs explain the key aspects in detail. "
            ) * random.randint(30, 50)

            code_blocks = []
            for c in range(random.randint(2, 5)):
                code_blocks.append(
                    {
                        "language": random.choice(
                            ["python", "javascript", "bash", "json"]
                        ),
                        "code": f"# Example {c + 1} for {topic}\n"
                        + "def example_function():\n"
                        + "    # Implementation details\n" * 15
                        + "    return result\n",
                        "description": f"Code example demonstrating {topic} implementation. "
                        * 5,
                    }
                )

            sections.append(
                {
                    "id": f"section-{s + 1}",
                    "title": f"Section {s + 1}: {topic} - Part {s + 1}",
                    "content": section_content,
                    "code_examples": code_blocks,
                    "notes": [
                        "Important note about this section. " * 10
                        for _ in range(random.randint(2, 4))
                    ],
                    "warnings": [
                        f"Warning {w}: Be careful when implementing this feature. " * 5
                        for w in range(random.randint(1, 3))
                    ],
                }
            )

        # Generate a comprehensive changelog
        changelog = []
        for v in range(random.randint(10, 25)):
            changelog.append(
                {
                    "version": f"{random.randint(1, 5)}.{v}.{random.randint(0, 10)}",
                    "date": (datetime.now() - timedelta(days=v * 14)).isoformat(),
                    "changes": [
                        f"- Updated {topic} functionality with new features and improvements. "
                        f"This change affects how users interact with the system. " * 3
                        for _ in range(random.randint(5, 10))
                    ],
                    "breaking_changes": [
                        f"Breaking: API endpoint changed from v{v} to v{v + 1}. " * 3
                    ]
                    if random.random() < 0.3
                    else [],
                }
            )

        # Generate related articles references
        related = [
            {
                "id": f"KB-{random.randint(1, 1000):04d}",
                "title": f"{random.choice(doc_types)}: {random.choice(topics)}",
                "summary": f"Related documentation about {random.choice(topics)}. "
                * 10,
            }
            for _ in range(random.randint(5, 15))
        ]

        # Generate FAQ section
        faqs = [
            {
                "question": f"How do I configure {topic} for {random.choice(['production', 'development', 'testing'])}?",
                "answer": f"To configure {topic}, you need to follow these steps. "
                * 20,
                "helpful_votes": random.randint(0, 100),
            }
            for _ in range(random.randint(10, 20))
        ]

        kb_article = {
            "id": i + 1,
            "article_id": f"KB-{i + 1:04d}",
            "type": doc_type,
            "topic": topic,
            "title": f"{doc_type}: Complete Guide to {topic}",
            "summary": (
                f"This comprehensive guide covers everything you need to know about {topic}. "
                f"From basic concepts to advanced implementation patterns, this {doc_type.lower()} "
                f"provides detailed explanations and practical examples. "
            )
            * 5,
            "introduction": (
                f"Welcome to the complete guide on {topic}. This documentation provides "
                f"in-depth coverage of all aspects related to {topic} implementation. "
                f"Whether you are a beginner or an experienced developer, this guide "
                f"will help you understand and implement {topic} effectively. "
            )
            * 10,
            "sections": sections,
            "changelog": changelog,
            "related_articles": related,
            "faq": faqs,
            "metadata": {
                "author": f"{random.choice(USER_FIRST_NAMES)} {random.choice(USER_LAST_NAMES)}",
                "reviewers": [
                    f"{random.choice(USER_FIRST_NAMES)} {random.choice(USER_LAST_NAMES)}"
                    for _ in range(random.randint(2, 5))
                ],
                "created_at": (
                    datetime.now() - timedelta(days=random.randint(30, 365))
                ).isoformat(),
                "updated_at": (
                    datetime.now() - timedelta(days=random.randint(1, 30))
                ).isoformat(),
                "word_count": random.randint(5000, 15000),
                "reading_time_minutes": random.randint(15, 45),
            },
            "tags": random.sample(
                [
                    "beginner",
                    "advanced",
                    "tutorial",
                    "reference",
                    "howto",
                    "guide",
                    "api",
                    "configuration",
                    "security",
                    "performance",
                ],
                k=random.randint(3, 6),
            ),
            "status": random.choice(
                ["published", "published", "published", "draft", "review"]
            ),
            "visibility": random.choice(["public", "public", "internal"]),
            "views": random.randint(100, 10000),
            "helpful_votes": random.randint(10, 500),
        }

        kb_articles.append(kb_article)

    return kb_articles


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
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
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
            "searchableAttributes": [
                "user_id",
                "email",
                "first_name",
                "last_name",
                "country",
            ],
            # S003: Numeric fields in searchableAttributes (Suggestion)
            # age is numeric but searchable
            "filterableAttributes": ["country", "is_active", "age"],
            "sortableAttributes": ["signup_date", "orders_count"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
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
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
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
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
            # S009: Very low pagination limit (Warning)
            "pagination": {"maxTotalHits": 50},
        },
        "documents": generate_orders,
        "doc_count": 1000,
    },
    "locations": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["name", "type"],
            # D011: operating_hours is filterable but contains arrays of objects
            "filterableAttributes": ["type", "rating", "operating_hours"],
            # D013: sorting on date strings (should suggest timestamps)
            "sortableAttributes": ["opened_at", "last_inspection", "rating"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_locations,
        "doc_count": 50,
    },
    "events": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["title", "description", "type"],
            # D011: speakers is filterable and contains arrays of objects
            "filterableAttributes": ["type", "price", "speakers"],
            # D013: sorting on date strings
            "sortableAttributes": ["event_date", "start_time", "price", "capacity"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_events,
        "doc_count": 100,
    },
    "reviews": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["title", "content"],
            "filterableAttributes": [
                "rating",
                "sentiment",
                "verified_purchase",
                "product_id",
            ],
            "sortableAttributes": ["rating", "helpful_votes", "created_at"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_reviews,
        "doc_count": 300,
    },
    "categories": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["name", "slug"],
            "filterableAttributes": ["parent", "level", "is_active"],
            "sortableAttributes": ["product_count", "level"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_categories,
        "doc_count": 50,
    },
    "tags": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["name", "display_name"],
            "filterableAttributes": ["type"],
            "sortableAttributes": ["usage_count", "created_at"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_tags,
        "doc_count": 100,
    },
    "logs": {
        "primaryKey": "id",
        "settings": {
            # S001: Wildcard searchable (Critical)
            "searchableAttributes": ["*"],
            "filterableAttributes": ["level", "service"],
            "sortableAttributes": ["timestamp", "duration_ms"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_logs,
        "doc_count": 500,
    },
    "notifications": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["title", "message"],
            "filterableAttributes": ["type", "status", "user_id"],
            "sortableAttributes": ["created_at", "sent_at"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_notifications,
        "doc_count": 200,
    },
    "inventory": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["product_id", "warehouse"],
            "filterableAttributes": ["warehouse", "quantity"],
            "sortableAttributes": ["quantity", "last_restocked"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_inventory,
        "doc_count": 400,
    },
    "analytics": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": ["page"],
            "filterableAttributes": ["metric", "source"],
            "sortableAttributes": ["timestamp", "value"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
            # S010: High pagination limit
            "pagination": {"maxTotalHits": 100000},
        },
        "documents": generate_analytics,
        "doc_count": 1000,
    },
    # ---- NEW: Indexes with PII/sensitive data for --detect-sensitive testing ----
    "customers": {
        "primaryKey": "id",
        "settings": {
            # S001: Wildcard searchableAttributes - CRITICAL: exposes all PII to search
            "searchableAttributes": ["*"],
            # PII fields are filterable - could be intentional but worth flagging
            "filterableAttributes": ["membership_tier", "country", "is_verified"],
            "sortableAttributes": ["signup_date", "total_spent", "orders_count"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_customers,
        "doc_count": 500,
    },
    "employees": {
        "primaryKey": "id",
        "settings": {
            # Sensitive fields explicitly searchable - very bad practice
            # S002: ID fields in searchableAttributes
            "searchableAttributes": [
                "employee_id",
                "full_name",
                "first_name",
                "last_name",
                "work_email",
                "job_title",
                "department",
            ],
            "filterableAttributes": [
                "department",
                "employment_type",
                "is_active",
                "hire_date",
            ],
            "sortableAttributes": ["hire_date", "salary"],
            # Explicitly limiting displayed attributes to hide sensitive data
            # This is actually a GOOD practice when PII exists
            "displayedAttributes": [
                "employee_id",
                "full_name",
                "work_email",
                "job_title",
                "department",
                "employment_type",
                "is_active",
            ],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            "distinctAttribute": None,
        },
        "documents": generate_employees,
        "doc_count": 50,
    },
    "support_tickets": {
        "primaryKey": "id",
        "settings": {
            "searchableAttributes": [
                "ticket_id",
                "subject",
                "description",
                "category",
                "tags",
            ],
            "filterableAttributes": [
                "status",
                "priority",
                "category",
                "channel",
                "assigned_agent_id",
            ],
            "sortableAttributes": [
                "created_at",
                "updated_at",
                "first_response_time_hours",
                "satisfaction_rating",
            ],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {},
            # D010: conversation field contains nested arrays of objects
            # which can cause issues with search/filter
            "distinctAttribute": None,
        },
        "documents": generate_support_tickets,
        "doc_count": 200,
    },
    # ---- NEW: Index with intentionally large documents for D001 testing ----
    "knowledge_base": {
        "primaryKey": "id",
        "settings": {
            # S001: Wildcard searchableAttributes on large docs = very slow search
            "searchableAttributes": ["*"],
            "filterableAttributes": ["type", "topic", "status", "visibility", "tags"],
            "sortableAttributes": ["views", "helpful_votes", "metadata.updated_at"],
            "displayedAttributes": ["*"],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness",
            ],
            "stopWords": [],
            "synonyms": {
                "guide": ["tutorial", "howto", "manual"],
                "api": ["interface", "endpoint"],
            },
            "distinctAttribute": None,
            # S010: High pagination combined with large docs = memory issues
            "pagination": {"maxTotalHits": 10000},
        },
        "documents": generate_knowledge_base,
        "doc_count": 20,
    },
}


def _calculate_proportional_counts(total_documents: int) -> dict[str, int]:
    """Calculate document counts for each index proportionally based on their default weights.

    Args:
        total_documents: Target total number of documents across all indexes

    Returns:
        Dictionary mapping index_uid to document count
    """
    # Use medium preset as the base for proportions
    base_counts = SIZE_PRESETS["medium"]
    base_total = sum(base_counts.values())

    # Calculate proportional counts
    counts: dict[str, int] = {}
    for index_uid in INDEX_CONFIGS:
        base = base_counts.get(index_uid) or INDEX_CONFIGS[index_uid]["doc_count"]
        proportion = float(base) / float(base_total)
        counts[index_uid] = max(1, int(total_documents * proportion))

    return counts


def create_dump_file(
    output_path: str | Path,
    size: str = "medium",
    total_documents: int | None = None,
    single_index: str | None = None,
) -> None:
    """Create a mock MeiliSearch dump file.

    Args:
        output_path: Path to write the dump file to
        size: Size preset - "small", "medium", or "large"
        total_documents: If specified, scale document counts to reach this total
        single_index: If specified, only create this index with total_documents count
    """
    output_path = Path(output_path)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dump_name = f"dump-{timestamp}"

    # Determine which indexes to create and their document counts
    if single_index:
        # Single index mode
        if single_index not in INDEX_CONFIGS:
            available = ", ".join(INDEX_CONFIGS.keys())
            print(f"Error: Unknown index '{single_index}'")
            print(f"Available indexes: {available}")
            sys.exit(1)

        doc_count = total_documents or INDEX_CONFIGS[single_index]["doc_count"]
        index_doc_counts = {single_index: doc_count}
        print(f"Creating single index '{single_index}' with {doc_count:,} documents")
    elif total_documents:
        # Scale all indexes proportionally to reach total_documents
        index_doc_counts = _calculate_proportional_counts(total_documents)
        actual_total = sum(index_doc_counts.values())
        print(
            f"Scaling all indexes to ~{total_documents:,} total documents (actual: {actual_total:,})"
        )
    else:
        # Use size preset
        size_config = SIZE_PRESETS.get(size, SIZE_PRESETS["medium"])
        index_doc_counts = {
            uid: size_config.get(uid, config["doc_count"])
            for uid, config in INDEX_CONFIGS.items()
        }
        print(f"Using size preset: {size}")

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

        for index_uid in index_doc_counts:
            # Document addition task (earlier)
            tasks.append(
                {
                    "uid": task_id,
                    "indexUid": index_uid,
                    "status": "succeeded",
                    "type": "documentAdditionOrUpdate",
                    "enqueuedAt": (base_time + timedelta(minutes=task_id)).isoformat(),
                    "startedAt": (
                        base_time + timedelta(minutes=task_id, seconds=1)
                    ).isoformat(),
                    "finishedAt": (
                        base_time + timedelta(minutes=task_id, seconds=5)
                    ).isoformat(),
                }
            )
            task_id += 1

            # Settings update task (later) - triggers B001
            tasks.append(
                {
                    "uid": task_id,
                    "indexUid": index_uid,
                    "status": "succeeded",
                    "type": "settingsUpdate",
                    "enqueuedAt": (
                        base_time + timedelta(minutes=task_id + 10)
                    ).isoformat(),
                    "startedAt": (
                        base_time + timedelta(minutes=task_id + 10, seconds=1)
                    ).isoformat(),
                    "finishedAt": (
                        base_time + timedelta(minutes=task_id + 10, seconds=2)
                    ).isoformat(),
                }
            )
            task_id += 1

        # Add some failed tasks (for P001 detection)
        for i in range(5):
            tasks.append(
                {
                    "uid": task_id,
                    "indexUid": "products",
                    "status": "failed",
                    "type": "documentAdditionOrUpdate",
                    "error": {"message": "Simulated error", "code": "internal"},
                    "enqueuedAt": (base_time + timedelta(minutes=task_id)).isoformat(),
                    "startedAt": (
                        base_time + timedelta(minutes=task_id, seconds=1)
                    ).isoformat(),
                    "finishedAt": (
                        base_time + timedelta(minutes=task_id, seconds=2)
                    ).isoformat(),
                }
            )
            task_id += 1

        (tasks_dir / "queue.json").write_text(json.dumps(tasks, indent=2))

        # Create indexes directory
        indexes_dir = dump_dir / "indexes"
        indexes_dir.mkdir()

        total_docs = 0
        for index_uid in index_doc_counts:
            config = INDEX_CONFIGS[index_uid]
            index_dir = indexes_dir / index_uid
            index_dir.mkdir()

            # Index metadata
            index_metadata = {
                "uid": index_uid,
                "primaryKey": config["primaryKey"],
                "createdAt": (datetime.now() - timedelta(days=30)).isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            (index_dir / "metadata.json").write_text(
                json.dumps(index_metadata, indent=2)
            )

            # Settings
            (index_dir / "settings.json").write_text(
                json.dumps(config["settings"], indent=2)
            )

            # Documents (JSONL format)
            doc_count = index_doc_counts[index_uid]
            docs = config["documents"](doc_count)
            with open(index_dir / "documents.jsonl", "w") as f:
                for doc in docs:
                    f.write(json.dumps(doc) + "\n")

            print(f"  Created index '{index_uid}' with {len(docs):,} documents")
            total_docs += len(docs)

        # Create tar.gz archive
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(dump_dir, arcname=dump_name)

    print(f"\nDump file created: {output_path}")
    print(f"  Total indexes: {len(index_doc_counts)}")
    print(f"  Total documents: {total_docs:,}")
    print(f"  File size: {Path(output_path).stat().st_size / 1024:.1f} KB")


def seed_instance(
    url: str,
    api_key: str | None = None,
    total_documents: int | None = None,
    single_index: str | None = None,
) -> None:
    """Seed a live MeiliSearch instance with test data.

    Args:
        url: MeiliSearch instance URL
        api_key: Optional API key for authentication
        total_documents: If specified, scale document counts to reach this total
        single_index: If specified, only create this index with total_documents count
    """
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

    # Determine which indexes to create and their document counts
    if single_index:
        if single_index not in INDEX_CONFIGS:
            available = ", ".join(INDEX_CONFIGS.keys())
            print(f"Error: Unknown index '{single_index}'")
            print(f"Available indexes: {available}")
            sys.exit(1)

        doc_count = total_documents or INDEX_CONFIGS[single_index]["doc_count"]
        index_doc_counts = {single_index: doc_count}
        print(f"\nSeeding single index '{single_index}' with {doc_count:,} documents")
    elif total_documents:
        index_doc_counts = _calculate_proportional_counts(total_documents)
        actual_total = sum(index_doc_counts.values())
        print(
            f"\nScaling all indexes to ~{total_documents:,} total documents (actual: {actual_total:,})"
        )
    else:
        # Default counts from INDEX_CONFIGS
        index_doc_counts = {
            uid: config["doc_count"] for uid, config in INDEX_CONFIGS.items()
        }
        print("\nCreating indexes and seeding data...")

    for index_uid, doc_count in index_doc_counts.items():
        config = INDEX_CONFIGS[index_uid]
        print(f"\n  Processing '{index_uid}' ({doc_count:,} documents)...")

        # Create/update index
        response = client.post(
            "/indexes",
            json={
                "uid": index_uid,
                "primaryKey": config["primaryKey"],
            },
        )

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

        # Add documents (in batches for large counts)
        docs = config["documents"](doc_count)
        batch_size = 10000  # MeiliSearch handles this well

        if len(docs) <= batch_size:
            # Single batch
            response = client.post(
                f"/indexes/{index_uid}/documents",
                json=docs,
            )
            task_info = response.json()
            print(f"    Document addition task: {task_info.get('taskUid', 'N/A')}")
            print(f"    Adding {len(docs):,} documents...")
            _wait_for_task(client, response)
        else:
            # Multiple batches
            total_batches = (len(docs) + batch_size - 1) // batch_size
            print(f"    Adding {len(docs):,} documents in {total_batches} batches...")
            for batch_num, i in enumerate(range(0, len(docs), batch_size), 1):
                batch = docs[i : i + batch_size]
                response = client.post(
                    f"/indexes/{index_uid}/documents",
                    json=batch,
                )
                task_info = response.json()
                print(
                    f"    Batch {batch_num}/{total_batches}: {len(batch):,} docs (task {task_info.get('taskUid', 'N/A')})"
                )
                _wait_for_task(client, response)

        print("    Done!")

    print("\nSeeding complete!")
    print("\nYou can now analyze with:")
    print(f"  meiliscan analyze --url {url}")
    print(f"  meiliscan serve --url {url}")


def _wait_for_task(client, response) -> None:
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
                print(
                    f"    Task failed: {task.get('error', {}).get('message', 'Unknown error')}"
                )
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
        "--output",
        "-o",
        default="test-dump.dump",
        help="Output file path (default: test-dump.dump)",
    )
    dump_parser.add_argument(
        "--size",
        "-s",
        choices=["small", "medium", "large"],
        default="medium",
        help="Size preset for document counts (default: medium). Ignored if --documents is specified.",
    )
    dump_parser.add_argument(
        "--documents",
        "-d",
        type=int,
        help="Total number of documents to generate. Distributes proportionally across all indexes, "
        "or sets exact count when used with --index.",
    )
    dump_parser.add_argument(
        "--index",
        "-i",
        help="Generate only this specific index. Use with --documents to set count.",
    )

    # Seed command
    seed_parser = subparsers.add_parser("seed", help="Seed a live MeiliSearch instance")
    seed_parser.add_argument(
        "--url",
        "-u",
        required=True,
        help="MeiliSearch instance URL",
    )
    seed_parser.add_argument(
        "--api-key",
        "-k",
        help="MeiliSearch API key",
    )
    seed_parser.add_argument(
        "--documents",
        "-d",
        type=int,
        help="Total number of documents to generate. Distributes proportionally across all indexes, "
        "or sets exact count when used with --index.",
    )
    seed_parser.add_argument(
        "--index",
        "-i",
        help="Seed only this specific index. Use with --documents to set count.",
    )

    # Clean command
    clean_parser = subparsers.add_parser(
        "clean", help="Delete all indexes from instance"
    )
    clean_parser.add_argument(
        "--url",
        "-u",
        required=True,
        help="MeiliSearch instance URL",
    )
    clean_parser.add_argument(
        "--api-key",
        "-k",
        help="MeiliSearch API key",
    )

    args = parser.parse_args()

    if args.command == "dump":
        print("Creating mock dump file...")
        create_dump_file(
            args.output,
            args.size,
            total_documents=args.documents,
            single_index=args.index,
        )
    elif args.command == "seed":
        seed_instance(
            args.url,
            args.api_key,
            total_documents=args.documents,
            single_index=args.index,
        )
    elif args.command == "clean":
        clean_instance(args.url, args.api_key)


if __name__ == "__main__":
    main()
