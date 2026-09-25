from flask import Flask, render_template, request
import os
import pymupdf

from database import get_connection
from ai_model import find_answer

app = Flask(__name__)

# Upload folder
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --------------------------------------------------
# GET ALL UPLOADED PDFs
# --------------------------------------------------

def get_uploaded_pdfs():

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, filename
            FROM pdfs
            ORDER BY id DESC
        """)

        pdfs = cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

    return pdfs


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():

    return render_template(
        "index.html",
        pdfs=get_uploaded_pdfs()
    )


# --------------------------------------------------
# UPLOAD PDF
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload_pdf():

    try:

        # Check if PDF was received
        if "pdf" not in request.files:

            return render_template(
                "index.html",
                message="❌ No PDF file was received.",
                pdfs=get_uploaded_pdfs()
            )

        pdf = request.files["pdf"]

        # Check filename
        if pdf.filename == "":

            return render_template(
                "index.html",
                message="❌ No PDF selected.",
                pdfs=get_uploaded_pdfs()
            )

        # Check extension
        if not pdf.filename.lower().endswith(".pdf"):

            return render_template(
                "index.html",
                message="❌ Please upload a PDF file.",
                pdfs=get_uploaded_pdfs()
            )

        # Get safe filename
        filename = os.path.basename(pdf.filename)

        # File path
        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        # Save PDF
        pdf.save(filepath)

        print("PDF saved:", filepath)

        # Open PDF
        document = pymupdf.open(filepath)

        # Connect database
        connection = get_connection()
        cursor = connection.cursor()

        # Insert PDF into database
        cursor.execute("""
            INSERT INTO pdfs (filename)
            VALUES (%s)
        """, (filename,))

        pdf_id = cursor.lastrowid

        # Extract text page by page
        for page_number, page in enumerate(document, start=1):

            text = page.get_text().strip()

            if text:

                cursor.execute("""
                    INSERT INTO pdf_chunks
                    (pdf_id, page_number, content)
                    VALUES (%s, %s, %s)
                """, (
                    pdf_id,
                    page_number,
                    text
                ))

        # Save database changes
        connection.commit()

        cursor.close()
        connection.close()

        document.close()

        return render_template(
            "index.html",
            message=f"✅ '{filename}' uploaded successfully!",
            pdfs=get_uploaded_pdfs()
        )

    except Exception as e:

        print("UPLOAD ERROR:", str(e))

        return render_template(
            "index.html",
            message=f"❌ Upload error: {str(e)}",
            pdfs=get_uploaded_pdfs()
        )


# --------------------------------------------------
# ASK AI
# --------------------------------------------------

@app.route("/ask", methods=["POST"])
def ask_ai():

    question = request.form.get(
        "question",
        ""
    ).strip()

    pdf_id = request.form.get("pdf_id")

    # Check question
    if not question:

        return render_template(
            "index.html",
            answer="Please enter a question.",
            pdfs=get_uploaded_pdfs()
        )

    # Check PDF selection
    if not pdf_id:

        return render_template(
            "index.html",
            answer="❌ Please select a PDF first.",
            pdfs=get_uploaded_pdfs()
        )

    try:

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Get content ONLY from selected PDF
        cursor.execute("""
            SELECT page_number, content
            FROM pdf_chunks
            WHERE pdf_id = %s
            ORDER BY page_number
        """, (pdf_id,))

        chunks = cursor.fetchall()

        cursor.close()
        connection.close()

        # No text found
        if not chunks:

            return render_template(
                "index.html",
                question=question,
                answer="❌ No text was found in this PDF.",
                pdfs=get_uploaded_pdfs(),
                selected_pdf=pdf_id
            )

        # Ask AI
        answer = find_answer(
            question,
            chunks
        )

        return render_template(
            "index.html",
            question=question,
            answer=answer,
            pdfs=get_uploaded_pdfs(),
            selected_pdf=pdf_id
        )

    except Exception as e:

        print("AI ERROR:", str(e))

        return render_template(
            "index.html",
            question=question,
            answer=f"❌ Error: {str(e)}",
            pdfs=get_uploaded_pdfs(),
            selected_pdf=pdf_id
        )


# --------------------------------------------------
# DELETE PDF
# --------------------------------------------------

@app.route("/delete/<int:pdf_id>", methods=["POST"])
def delete_pdf(pdf_id):

    connection = None
    cursor = None

    try:

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Find PDF
        cursor.execute("""
            SELECT filename
            FROM pdfs
            WHERE id = %s
        """, (pdf_id,))

        pdf = cursor.fetchone()

        # PDF doesn't exist
        if not pdf:

            return render_template(
                "index.html",
                message="❌ PDF not found.",
                pdfs=get_uploaded_pdfs()
            )

        filename = pdf["filename"]

        # Delete PDF chunks
        cursor.execute("""
            DELETE FROM pdf_chunks
            WHERE pdf_id = %s
        """, (pdf_id,))

        # Delete PDF record
        cursor.execute("""
            DELETE FROM pdfs
            WHERE id = %s
        """, (pdf_id,))

        # Save changes
        connection.commit()

        # Close database
        cursor.close()
        cursor = None

        connection.close()
        connection = None

        # Delete actual PDF file
        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        if os.path.exists(filepath):

            os.remove(filepath)

        return render_template(
            "index.html",
            message=f"✅ '{filename}' deleted successfully!",
            pdfs=get_uploaded_pdfs()
        )

    except Exception as e:

        print("DELETE ERROR:", str(e))

        if connection:
            connection.rollback()

        return render_template(
            "index.html",
            message=f"❌ Delete error: {str(e)}",
            pdfs=get_uploaded_pdfs()
        )

    finally:

        if cursor:
            cursor.close()

        if connection:
            connection.close()


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(debug=True)