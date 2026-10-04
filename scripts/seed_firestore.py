"""Seed script to populate Firestore with sample books for BookNook AI."""

import google.auth
from google.cloud import firestore

# Hardcoded GCP Project ID (crucial for Agent Platform compatibility)
PROJECT_ID = "qwiklabs-gcp-02-6b724dcd6ef3"

SAMPLE_BOOKS = [
    {
        "id": "book-1",
        "title": "Dune",
        "author": "Frank Herbert",
        "genre": "Sci-Fi",
        "status": "read",
        "rating": 5.0,
        "review": "A masterpiece of world-building and political intrigue on Arrakis.",
        "pages": 688,
        "pages_read": 688,
        "date_added": "2026-01-10",
        "date_completed": "2026-02-15",
    },
    {
        "id": "book-2",
        "title": "Project Hail Mary",
        "author": "Andy Weir",
        "genre": "Sci-Fi",
        "status": "read",
        "rating": 4.8,
        "review": "Thrilling interstellar survival story with amazing science problem-solving.",
        "pages": 496,
        "pages_read": 496,
        "date_added": "2026-03-01",
        "date_completed": "2026-03-20",
    },
    {
        "id": "book-3",
        "title": "Atomic Habits",
        "author": "James Clear",
        "genre": "Non-Fiction",
        "status": "read",
        "rating": 4.5,
        "review": "Practical and actionable framework for building good habits every day.",
        "pages": 320,
        "pages_read": 320,
        "date_added": "2026-04-05",
        "date_completed": "2026-04-18",
    },
    {
        "id": "book-4",
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "genre": "Fantasy",
        "status": "currently_reading",
        "rating": 0.0,
        "review": "Enjoying Bilbo's journey across Middle-earth.",
        "pages": 310,
        "pages_read": 180,
        "date_added": "2026-09-01",
        "date_completed": "",
    },
    {
        "id": "book-5",
        "title": "Klara and the Sun",
        "author": "Kazuo Ishiguro",
        "genre": "Fiction",
        "status": "want_to_read",
        "rating": 0.0,
        "review": "",
        "pages": 307,
        "pages_read": 0,
        "date_added": "2026-10-01",
        "date_completed": "",
    },
]


def get_firestore_client() -> firestore.Client:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return firestore.Client(project=PROJECT_ID, credentials=creds)


def seed_database():
    print(f"Connecting to Firestore with project_id={PROJECT_ID}...")
    db = get_firestore_client()
    books_ref = db.collection("books")

    for book in SAMPLE_BOOKS:
        doc_id = book["id"]
        doc_ref = books_ref.document(doc_id)
        doc_ref.set(book)
        print(f"Seeded: '{book['title']}' by {book['author']} [{book['status']}]")

    print(f"✅ Successfully seeded {len(SAMPLE_BOOKS)} books into 'books' collection!")


if __name__ == "__main__":
    seed_database()
