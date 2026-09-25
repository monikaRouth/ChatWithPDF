
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# Load AI model
model = SentenceTransformer("all-MiniLM-L6-v2")


def find_answer(question, chunks):

    if not chunks:
        return "No PDF content is available."

    question_lower = question.lower().strip()

    # -------------------------------------------------
    # GENERAL / SUMMARY QUESTIONS
    # -------------------------------------------------

    summary_keywords = [
        "what is this pdf about",
        "what is the pdf about",
        "what does this pdf contain",
        "what does the pdf contain",
        "summarize this pdf",
        "summarise this pdf",
        "summary of this pdf",
        "give me a summary",
        "give summary",
        "main topic",
        "main topics",
        "what are the topics",
        "what topics are covered",
        "explain the pdf",
        "overview of the pdf",
        "give me an overview"
    ]

    is_summary_question = any(
        keyword in question_lower
        for keyword in summary_keywords
    )

    # -------------------------------------------------
    # PDF SUMMARY
    # -------------------------------------------------

    if is_summary_question:

        # Take text from all chunks
        all_text = []

        for chunk in chunks:
            content = chunk.get("content", "").strip()

            if content:
                all_text.append(content)

        if not all_text:
            return "No readable text was found in the PDF."

        # Combine the text
        full_text = "\n\n".join(all_text)

        # Avoid sending an extremely large amount of text
        max_characters = 12000

        if len(full_text) > max_characters:
            full_text = full_text[:max_characters]

        # Create a simple extractive overview
        paragraphs = [
            p.strip()
            for p in full_text.split("\n")
            if p.strip()
        ]

        # Remove very short lines
        paragraphs = [
            p for p in paragraphs
            if len(p) > 40
        ]

        # Select important-looking paragraphs
        selected = paragraphs[:8]

        if not selected:
            selected = paragraphs[:5]

        summary = "\n\n".join(selected)

        return (
            "📚 PDF Overview:\n\n"
            + summary
            + "\n\n"
            "This overview is based on the content of your uploaded PDF."
        )

    # -------------------------------------------------
    # SPECIFIC QUESTIONS
    # -------------------------------------------------

    # Convert question into embedding
    question_embedding = model.encode(
        [question]
    )

    # Get PDF text
    chunk_texts = [
        chunk.get("content", "")
        for chunk in chunks
    ]

    # Convert PDF chunks into embeddings
    chunk_embeddings = model.encode(
        chunk_texts
    )

    # Calculate similarity
    similarities = cosine_similarity(
        question_embedding,
        chunk_embeddings
    )[0]

    # Sort chunks from most relevant to least relevant
    ranked_indexes = similarities.argsort()[::-1]

    # Best match
    best_index = ranked_indexes[0]
    best_score = similarities[best_index]

    # -------------------------------------------------
    # CONFIDENCE CHECK
    # -------------------------------------------------

    if best_score < 0.30:

        return (
            "I could not find a relevant answer "
            "in your uploaded PDF."
        )

    # -------------------------------------------------
    # COMBINE TOP RELEVANT CHUNKS
    # -------------------------------------------------

    relevant_chunks = []

    for index in ranked_indexes[:3]:

        score = similarities[index]

        # Only use reasonably relevant chunks
        if score >= 0.30:

            relevant_chunks.append(
                chunks[index]
            )

    # -------------------------------------------------
    # CREATE ANSWER
    # -------------------------------------------------

    answer_parts = []

    used_pages = []

    for chunk in relevant_chunks:

        content = chunk.get(
            "content",
            ""
        ).strip()

        page_number = chunk.get(
            "page_number",
            "Unknown"
        )

        if content:

            answer_parts.append(
                content
            )

            if page_number not in used_pages:
                used_pages.append(
                    page_number
                )

    if not answer_parts:

        return (
            "I could not find a relevant answer "
            "in your uploaded PDF."
        )

    answer = "\n\n".join(answer_parts)

    # -------------------------------------------------
    # SOURCE INFORMATION
    # -------------------------------------------------

    pages = ", ".join(
        str(page)
        for page in used_pages
    )

    return (
        answer
        + "\n\n"
        + f"📄 Source: Page {pages}"
    )

