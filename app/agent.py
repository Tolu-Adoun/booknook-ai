# ruff: noqa
import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid

import google.auth
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

# Hardcoded GCP Project ID, Bucket Name, and Memory Bank ID
PROJECT_ID = "qwiklabs-gcp-02-6b724dcd6ef3"
BUCKET_NAME = "booknook-ai-assets-qwiklabs-gcp-02-6b724dcd6ef3"
MEMORY_BANK_ID = "4548935790318583808"


def get_agent_engine_resource_name() -> str | None:
    """Reads Agent Engine resource name from deployment_metadata.json if available."""
    metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                data = json.load(f)
                return data.get("remote_agent_runtime_id")
        except Exception:
            pass
    return None


def get_firestore_client() -> firestore.Client:
    """Helper to initialize a Firestore client with hardcoded project ID and scoped credentials."""
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return firestore.Client(project=PROJECT_ID, credentials=creds)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: After each turn, send the session events to Memory Bank for extraction."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def generate_book_cover(prompt: str, tool_context: ToolContext) -> str:
    """Generates custom book cover artwork or milestone badge artwork using Gemini image generation,
    saves it as an artifact in the playground, and uploads it directly to public Cloud Storage.

    Args:
        prompt: Description of the book cover or badge to generate (e.g. 'Desert sand dunes under two moons, sci-fi book cover').

    Returns:
        The public HTTPS URL of the generated image in Cloud Storage.
    """
    try:
        genai_client = genai.Client(
            vertexai=True, project=PROJECT_ID, location="global"
        )
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"High quality book cover artwork: {prompt}",
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

        image_bytes = None
        mime_type = "image/png"
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return "Failed to generate image bytes from model."

        filename = f"book_cover_{uuid.uuid4().hex[:8]}.png"

        # (1) Save artifact for ADK Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload image bytes directly to public Cloud Storage bucket (no local file)
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        storage_client = storage.Client(project=PROJECT_ID, credentials=creds)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"🎨 Image generated successfully!\nArtifact saved: '{filename}'\nPublic URL: {public_url}"

    except Exception as e:
        return f"Error generating or uploading book cover image: {str(e)}"


def generate_book_trailer_video(prompt: str, tool_context: ToolContext) -> str:
    """Generates a short animated book trailer video or teaser video for an item in the agent's domain using Google's Omni model (gemini-omni-flash-preview) in the global region,
    saves it as an artifact in the playground, and uploads it directly to public Cloud Storage.

    Args:
        prompt: Description of the short video to generate (e.g. 'Short animated trailer for a sci-fi book set in space').

    Returns:
        The public HTTPS URL of the generated video in Cloud Storage.
    """
    try:
        genai_client = genai.Client(
            vertexai=True, project=PROJECT_ID, location="global"
        )
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"Short animated book trailer video: {prompt}",
            response_modalities=["text", "video"],
        )

        video_bytes = None
        mime_type = "video/mp4"

        if interaction and hasattr(interaction, "output_video") and interaction.output_video:
            v_dict = interaction.output_video.model_dump()
            data_str = v_dict.get("data") or v_dict.get("bytes") or getattr(interaction.output_video, "data", None)
            if data_str:
                if isinstance(data_str, bytes):
                    video_bytes = data_str
                elif isinstance(data_str, str):
                    video_bytes = base64.b64decode(data_str)
            if v_dict.get("mime_type"):
                mime_type = v_dict.get("mime_type")

        if not video_bytes:
            return "Failed to extract video bytes from gemini-omni-flash-preview response."

        filename = f"book_trailer_{uuid.uuid4().hex[:8]}.mp4"

        # (1) Save artifact for ADK Playground Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload video bytes directly to public Cloud Storage bucket (no local file)
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        storage_client = storage.Client(project=PROJECT_ID, credentials=creds)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"🎬 Video generated successfully!\nArtifact saved: '{filename}'\nPublic URL: {public_url}"

    except Exception as e:
        return f"Error generating or uploading book trailer video: {str(e)}"




def search_online_books(query: str) -> str:
    """Searches the public Open Library online book catalog for real book details, authors, page counts, and cover links.

    Args:
        query: Book title, author, or search query.

    Returns:
        A list of matching books with author, publish year, page count, and cover image link.
    """
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://openlibrary.org/search.json?q={encoded_query}&limit=3"
        req = urllib.request.Request(
            url, headers={"User-Agent": "BookNookAI/1.0 (LabDemo)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        docs = data.get("docs", [])
        if not docs:
            return f"No online books found matching query: '{query}'."

        results = []
        for doc in docs:
            title = doc.get("title", "Unknown Title")
            authors = ", ".join(doc.get("author_name", ["Unknown Author"]))
            publish_year = doc.get("first_publish_year", "N/A")
            pages = doc.get("number_of_pages_median") or doc.get("number_of_pages", "N/A")
            cover_i = doc.get("cover_i")
            cover_url = (
                f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                if cover_i
                else "No cover available"
            )
            results.append(
                f"• **{title}** by {authors} (Published: {publish_year}) | Pages: {pages} | Cover: {cover_url}"
            )

        return "\n".join(results)
    except Exception as e:
        return f"Error searching online book catalog: {str(e)}"


def get_free_ebooks(search_term: str) -> str:
    """Searches Gutendex (Project Gutenberg public domain library) for free downloadable eBooks, classic literature, and download counts.

    Args:
        search_term: Book title, author, or topic (e.g., 'Frankenstein', 'Jane Austen', 'Sherlock Holmes').

    Returns:
        Formatted list of free public domain eBooks with read/download links.
    """
    try:
        encoded = urllib.parse.quote(search_term)
        url = f"https://gutendex.com/books/?search={encoded}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "BookNookAI/1.0 (LabDemo)"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = data.get("results", [])
        if not results:
            return f"No free public domain eBooks found on Gutendex for '{search_term}'."

        formatted = []
        for b in results[:3]:
            title = b.get("title", "Unknown Title")
            authors = ", ".join([a.get("name", "Unknown") for a in b.get("authors", [])])
            downloads = b.get("download_count", 0)
            formats = b.get("formats", {})
            html_link = formats.get("text/html") or formats.get("text/plain; charset=us-ascii") or "https://www.gutenberg.org"
            formatted.append(
                f"• **{title}** by {authors} ({downloads:,} downloads) - Free Read/Download: {html_link}"
            )

        return "\n".join(formatted)
    except Exception as e:
        return f"Error fetching free eBooks from Gutendex API: {str(e)}"


def list_books(status: str = None, genre: str = None) -> str:
    """Retrieves books from the user's Firestore reading collection.

    Args:
        status: Optional filter by reading status ('read', 'currently_reading', 'want_to_read').
        genre: Optional filter by genre (e.g. 'Sci-Fi', 'Fantasy', 'Non-Fiction').

    Returns:
        A formatted list of matching books with details.
    """
    try:
        db = get_firestore_client()
        books_ref = db.collection("books")
        docs = books_ref.stream()

        books = []
        for doc in docs:
            b = doc.to_dict()
            if status and b.get("status", "").lower() != status.lower():
                continue
            if genre and b.get("genre", "").lower() != genre.lower():
                continue
            books.append(b)

        if not books:
            filter_str = f" with status='{status}'" if status else ""
            filter_str += f" and genre='{genre}'" if genre else ""
            return f"No books found in your library{filter_str}."

        formatted_list = []
        for b in books:
            rating_str = f"⭐ {b.get('rating')}/5" if b.get("rating") and b.get("rating") > 0 else "Unrated"
            review_str = f" - Review: '{b.get('review')}'" if b.get("review") else ""
            pages_str = f" ({b.get('pages_read', 0)}/{b.get('pages', 0)} pages)" if b.get("pages") else ""
            formatted_list.append(
                f"• **{b.get('title')}** by {b.get('author')} [{b.get('genre')}] - Status: {b.get('status')} | {rating_str}{pages_str}{review_str}"
            )

        return "\n".join(formatted_list)
    except Exception as e:
        return f"Error accessing Firestore books collection: {str(e)}"


def add_book(
    title: str,
    author: str,
    genre: str,
    status: str = "want_to_read",
    rating: float = 0.0,
    review: str = "",
    pages: int = 0,
    pages_read: int = 0,
) -> str:
    """Adds a new book to the user's Firestore reading log.

    Args:
        title: Title of the book.
        author: Author of the book.
        genre: Genre of the book (e.g., 'Sci-Fi', 'Fiction', 'Fantasy', 'Non-Fiction').
        status: Reading status ('read', 'currently_reading', or 'want_to_read').
        rating: Optional star rating from 1.0 to 5.0.
        review: Optional short review or notes.
        pages: Total page count.
        pages_read: Pages read so far.

    Returns:
        Confirmation message.
    """
    try:
        db = get_firestore_client()
        doc_id = title.lower().replace(" ", "-").replace("'", "")
        book_data = {
            "id": doc_id,
            "title": title,
            "author": author,
            "genre": genre,
            "status": status.lower(),
            "rating": float(rating),
            "review": review,
            "pages": int(pages),
            "pages_read": int(pages_read) if status != "read" else int(pages),
            "date_added": datetime.date.today().isoformat(),
            "date_completed": datetime.date.today().isoformat() if status == "read" else "",
        }
        db.collection("books").document(doc_id).set(book_data)
        return f"✅ Successfully added '{title}' by {author} to your '{status}' list in Firestore!"
    except Exception as e:
        return f"Error adding book to Firestore: {str(e)}"


def update_book_status(
    title: str,
    status: str = None,
    pages_read: int = None,
    rating: float = None,
    review: str = "",
) -> str:
    """Updates an existing book's status, rating, pages read, or review in Firestore.

    Args:
        title: Title of the book to update.
        status: New status ('read', 'currently_reading', 'want_to_read').
        pages_read: Updated page count read so far.
        rating: Updated star rating (1.0 to 5.0).
        review: Updated review or notes.

    Returns:
        Confirmation message.
    """
    try:
        db = get_firestore_client()
        doc_id = title.lower().replace(" ", "-").replace("'", "")
        doc_ref = db.collection("books").document(doc_id)
        doc = doc_ref.get()

        if not doc.exists:
            all_docs = db.collection("books").stream()
            found_doc = None
            for d in all_docs:
                if title.lower() in d.to_dict().get("title", "").lower():
                    found_doc = d
                    break
            if found_doc:
                doc_ref = db.collection("books").document(found_doc.id)
                doc = found_doc
            else:
                return f"Could not find book matching '{title}' in your library."

        updates = {}
        if status:
            updates["status"] = status.lower()
            if status.lower() == "read":
                updates["date_completed"] = datetime.date.today().isoformat()
        if pages_read is not None:
            updates["pages_read"] = int(pages_read)
        if rating is not None:
            updates["rating"] = float(rating)
        if review:
            updates["review"] = review

        if updates:
            doc_ref.update(updates)
            return f"✅ Successfully updated '{title}' with: {updates}"
        return f"No updates provided for '{title}'."
    except Exception as e:
        return f"Error updating book in Firestore: {str(e)}"


# Configure AgentEngineSandboxCodeExecutor using Agent Engine resource ID from deployment_metadata.json
code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=get_agent_engine_resource_name()
)

# Configure A2UI Schema Manager version 0.8 with BasicCatalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are BookNook AI, a personalized reading concierge and book tracker assistant.",
    workflow_description=(
        "You help users search for books online (`search_online_books`), find free downloadable classics (`get_free_ebooks`), "
        "generate custom book covers (`generate_book_cover`), generate short book trailer videos (`generate_book_trailer_video`), manage their personal bookshelf in Firestore (`list_books`, `add_book`), "
        "update reading progress (`update_book_status`), and execute Python code in a secure Agent Engine sandbox to compute statistics or data analysis.\n\n"
        "You remember the user's stated reading preferences, favorite authors, and facts across conversations using your Memory Bank (`PreloadMemoryTool`).\n\n"
        "When executing Python code to perform calculations, data processing, or stats, output the Python code inside a markdown block (```python ... ```). Do NOT attempt to call a function named `run_code`."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use Table or Heading (unsupported), "
        "or Buttons, actions, or forms (they do nothing in adk web). You may include one Image component, but only when "
        "you have a public https URL for the image (for example the URL an image tool returns after uploading to a public bucket). "
        "Set the Image url to that exact https link, for example {\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. "
        "Never point an Image at a bare filename, an artifact name, or a non-http(s) path. If you do not have a public URL, add a short "
        "Text line noting the image instead. No markdown in text; use the usageHint property ('h1', 'h2', 'body') for headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in <a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        generate_book_cover,
        generate_book_trailer_video,
        search_online_books,
        get_free_ebooks,
        list_books,
        add_book,
        update_book_status,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
