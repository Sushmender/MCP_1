import arxiv
import httpx
import json
import os
import re
from typing import List
from mcp.server.fastmcp import FastMCP


# Directory (relative to project root) where paper metadata is persisted.
# The filesystem MCP server is scoped to this same directory so the LLM can
# read/write files here via file_system tool calls.
PAPER_DIR = "papers"

# Initialize the FastMCP server — the name "research" is what appears in
# the MCP tool namespace exposed to the client.
mcp = FastMCP("research")


# ===========================================================================
# TOOLS
# ===========================================================================

@mcp.tool()
def search_papers(topic: str, max_results: int = 5) -> List[str]:
    """
    Search for papers on arXiv based on a topic and store their information.

    Fetches the most relevant papers for the given topic from arXiv, then
    saves their metadata (title, authors, summary, PDF URL, publish date)
    into a JSON file at:

        papers/<topic>/papers_info.json

    If the file already exists, new results are merged in (existing entries
    are preserved; new entries are added / overwritten by paper ID).

    Args:
        topic: The topic to search for (e.g. "attention mechanisms").
        max_results: Maximum number of results to retrieve (default: 5).

    Returns:
        List of paper IDs (short arXiv IDs) found in the search.
    """
    client = arxiv.Client()

    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    papers = client.results(search)

    # Create a topic-specific sub-directory inside PAPER_DIR
    safe_topic = topic.lower().replace(" ", "_")
    path = os.path.join(PAPER_DIR, safe_topic)
    os.makedirs(path, exist_ok=True)

    file_path = os.path.join(path, "papers_info.json")

    # Load any previously stored papers for this topic
    try:
        with open(file_path, "r", encoding="utf-8") as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Process each result and merge into papers_info
    paper_ids: List[str] = []
    for paper in papers:
        paper_id = paper.get_short_id()
        paper_ids.append(paper_id)
        papers_info[paper_id] = {
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": paper.summary,
            "pdf_url": paper.pdf_url,
            "published": str(paper.published.date()),
        }

    # Persist the updated metadata
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump(papers_info, json_file, indent=2, ensure_ascii=False)

    print(f"Results saved in: {file_path}")
    return paper_ids


@mcp.tool()
def fetch_url(url: str, max_chars: int = 8000) -> str:
    """
    Fetch the content of any publicly accessible URL and return its text.

    Makes a real HTTP GET request to the given URL, strips HTML markup, and
    returns up to ``max_chars`` characters of the resulting plain text so the
    LLM can read and reason about the actual page content.

    Args:
        url: The full URL to fetch (e.g. "https://example.com/article").
        max_chars: Maximum number of characters to return (default: 8000).
                   Keeps responses within typical LLM context limits.

    Returns:
        Plain-text content of the page (truncated if necessary), or an
        error message describing why the fetch failed.
    """
    # Basic sanity-check: only allow http/https
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return f"Error: Only http:// and https:// URLs are supported. Got: {url!r}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MCPResearchBot/1.0; +https://github.com/Sushmender/MCP_1)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
    }

    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            response = client.get(url, headers=headers)
        response.raise_for_status()
    except httpx.TimeoutException:
        return f"Error: Request timed out after 20 seconds while fetching {url!r}."
    except httpx.HTTPStatusError as exc:
        return f"Error: HTTP {exc.response.status_code} when fetching {url!r}."
    except httpx.RequestError as exc:
        return f"Error: Network error fetching {url!r} — {exc}."

    raw = response.text

    # ── Strip HTML ──────────────────────────────────────────────────────────
    # Remove <script> and <style> blocks entirely
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode common HTML entities
    raw = (
        raw.replace("&amp;", "&")
           .replace("&lt;", "<")
           .replace("&gt;", ">")
           .replace("&quot;", '"')
           .replace("&#39;", "'")
           .replace("&nbsp;", " ")
    )
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", raw)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[… content truncated at {max_chars} characters …]"

    return text if text else "(Page fetched successfully but no readable text was found.)"


@mcp.tool()
def extract_info(paper_id: str) -> str:
    """
    Retrieve stored metadata for a specific paper by its arXiv ID.

    Searches across all topic sub-directories under the papers/ directory
    for a papers_info.json that contains the requested paper ID.

    Args:
        paper_id: The short arXiv ID of the paper (e.g. "2301.01234").

    Returns:
        JSON-formatted string with the paper's metadata if found,
        or an informative message if the paper has not been stored yet.
    """
    if not os.path.isdir(PAPER_DIR):
        return (
            f"No papers have been stored yet. "
            f"Use search_papers() first to populate the '{PAPER_DIR}' directory."
        )

    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if not os.path.isdir(item_path):
            continue
        file_path = os.path.join(item_path, "papers_info.json")
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as json_file:
                papers_info = json.load(json_file)
            if paper_id in papers_info:
                return json.dumps(papers_info[paper_id], indent=2, ensure_ascii=False)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading {file_path}: {e}")
            continue

    return f"No stored information found for paper ID '{paper_id}'."


# ===========================================================================
# RESOURCES
# Resources expose data that clients can read directly (like a GET endpoint).
# URI scheme: papers://
# ===========================================================================

@mcp.resource("papers://list")
def list_stored_papers() -> str:
    """
    List all paper IDs stored locally, grouped by topic.

    Returns a JSON object mapping each topic folder name to the list of
    arXiv paper IDs stored under it.  Useful for the client to discover
    what has already been fetched without calling a tool.

    Returns:
        JSON string: { "<topic>": ["<paper_id>", ...], ... }
    """
    result: dict = {}

    if not os.path.isdir(PAPER_DIR):
        return json.dumps(result)

    for topic in sorted(os.listdir(PAPER_DIR)):
        topic_path = os.path.join(PAPER_DIR, topic, "papers_info.json")
        if os.path.isfile(topic_path):
            try:
                with open(topic_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result[topic] = list(data.keys())
            except (FileNotFoundError, json.JSONDecodeError):
                result[topic] = []

    return json.dumps(result, indent=2)


@mcp.resource("papers://{topic}/info")
def get_topic_papers(topic: str) -> str:
    """
    Return all stored paper metadata for a given topic.

    The topic name should match the folder name under papers/ (spaces are
    stored as underscores, e.g. "attention_mechanisms").

    Args:
        topic: The topic folder name (e.g. "attention_mechanisms").

    Returns:
        JSON string with all paper metadata for that topic, or an error
        message if no papers have been stored for the topic yet.
    """
    path = os.path.join(PAPER_DIR, topic, "papers_info.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": f"No papers found for topic '{topic}'. Run search_papers first."})


# ===========================================================================
# PROMPTS
# Prompts are reusable message templates that pre-fill the LLM context with
# a structured instruction, so the user (or client) can trigger common
# research workflows without typing the full prompt every time.
# ===========================================================================

@mcp.prompt()
def summarize_paper(paper_id: str) -> str:
    """
    Generate a prompt that instructs the LLM to summarize a stored paper.

    Args:
        paper_id: The short arXiv ID of the paper to summarize.
    """
    return (
        f"Please summarize the research paper with arXiv ID '{paper_id}'.\n\n"
        "Steps:\n"
        "1. Use the `extract_info` tool to retrieve the paper's stored metadata.\n"
        "2. Write a clear, concise summary (3–4 paragraphs) covering:\n"
        "   - The problem the paper addresses\n"
        "   - The proposed approach or methodology\n"
        "   - Key results and contributions\n"
        "   - Potential limitations or future work\n"
        "3. End with a one-sentence takeaway."
    )


@mcp.prompt()
def compare_papers(paper_id_1: str, paper_id_2: str) -> str:
    """
    Generate a prompt that instructs the LLM to compare two stored papers.
    If a paper is not stored locally, the LLM is instructed to search for
    it first using search_papers before comparing.

    Args:
        paper_id_1: arXiv ID of the first paper.
        paper_id_2: arXiv ID of the second paper.
    """
    return (
        f"Compare the following two research papers:\n"
        f"  • Paper A: '{paper_id_1}'\n"
        f"  • Paper B: '{paper_id_2}'\n\n"
        "Steps:\n"
        "1. Call `extract_info` for each paper ID.\n"
        f"   - If `extract_info` returns 'No stored information found' for '{paper_id_1}',\n"
        f"     call `search_papers(topic='{paper_id_1}', max_results=1)` first, then retry `extract_info`.\n"
        f"   - Do the same for '{paper_id_2}' if it is also not found.\n"
        "2. Once you have metadata for both papers, produce a structured comparison covering:\n"
        "   - Research problem & motivation\n"
        "   - Methodology / approach\n"
        "   - Key results & contributions\n"
        "   - Strengths and weaknesses of each\n"
        "3. Conclude with a recommendation: which paper would you read first and why?\n\n"
        "Important: Do NOT give up if a paper is not found locally — always try searching first."
    )


@mcp.prompt()
def find_and_summarize(topic: str, max_results: int = 3) -> str:
    """
    Generate a prompt that instructs the LLM to search for papers on a topic
    and then summarize the top results.

    Args:
        topic: The research topic to search for.
        max_results: How many papers to fetch and summarize (default: 3).
    """
    return (
        f"Find and summarize the top {max_results} research papers on the topic: '{topic}'.\n\n"
        "Steps:\n"
        f"1. Call `search_papers` with topic='{topic}' and max_results={max_results}.\n"
        "2. For each returned paper ID, call `extract_info` to get its metadata.\n"
        "3. Write a brief summary (1–2 paragraphs) for each paper.\n"
        "4. After all summaries, write a short synthesis paragraph highlighting "
        "common themes and open research questions across the papers."
    )


if __name__ == "__main__":
    # Run with stdio transport so MCP clients can launch this as a subprocess.
    # Command: python research_server.py
    mcp.run(transport="stdio")
