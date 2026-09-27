import os

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


def find_answer(question, chunks):
    if not chunks:
        return "No PDF content is available."

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Groq is not configured. Add GROQ_API_KEY to the .env file."

    document_parts = []
    for chunk in chunks:
        content = chunk.get("content", "").strip()
        if content:
            page_number = chunk.get("page_number", "Unknown")
            document_parts.append(f"[Page {page_number}]\n{content}")

    document = "\n\n".join(document_parts)
    if not document:
        return "No readable text was found in the PDF."

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        temperature=0.2,
        max_tokens=2048,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions about the provided PDF. Read and use the "
                    "entire document context, not just a few matching passages. "
                    "Answer any question that is related to the document, including "
                    "summaries, explanations, comparisons, calculations, and details. "
                    "Do not invent facts. If the answer cannot be found in the PDF, "
                    "say clearly that it is not available in the document. Include "
                    "relevant page numbers when possible."
                ),
            },
            {
                "role": "user",
                "content": f"PDF DOCUMENT:\n\n{document}\n\nQUESTION:\n{question}",
            },
        ],
    )

    return completion.choices[0].message.content.strip()
