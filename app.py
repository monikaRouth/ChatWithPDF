from flask import Flask, jsonify, render_template, request, redirect, session, url_for
import os
import pymupdf
from datetime import datetime
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

from database import (
    add_chat_message,
    add_pdf_chunk,
    claim_unowned_pdfs,
    create_pdf,
    create_user,
    delete_pdf as delete_pdf_record,
    find_user_by_email,
    get_pdf,
    get_pdf_chunks,
    list_conversations,
    list_pdfs,
    store_pdf,
)
from ai_model import find_answer

app = Flask(__name__)
app.secret_key = os.environ.get("PAPERTRAIL_SECRET_KEY", "papertrail-development-key")

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


@app.context_processor
def inject_user():
    return {"current_user": session.get("user_name")}


# --------------------------------------------------
# GET ALL UPLOADED PDFs
# --------------------------------------------------

def get_uploaded_pdfs(user_id):
    pdfs = list_pdfs(user_id)

    for pdf in pdfs:
        file_size = pdf.get("file_size", 0)
        pdf["file_size"] = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.1f} MB"
        pdf["page_count"] = pdf.get("page_count", "Unavailable")
        uploaded_date = pdf.get("created_at")
        pdf["uploaded_date"] = uploaded_date.strftime("%d %b %Y") if uploaded_date else "Unavailable"

    return pdfs


def get_conversations(user_id, pdf_id):
    if not pdf_id:
        return []
    return list_conversations(user_id, pdf_id)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or len(password) < 6:
        return render_template("signup.html", error="Enter your name, a valid email, and a password of at least 6 characters.")

    if find_user_by_email(email):
        return render_template("signup.html", error="An account with that email already exists.")

    user = create_user(name, email, generate_password_hash(password))
    user_id = user["_id"]
    claim_unowned_pdfs(user_id)

    session.clear()
    session["user_id"] = user_id
    session["user_name"] = name
    return redirect(url_for("home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = find_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Email or password is incorrect.")

    session.clear()
    session["user_id"] = user["_id"]
    session["user_name"] = user["name"]
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
@login_required
def home():

    pdfs = get_uploaded_pdfs(session["user_id"])
    selected_pdf = request.args.get("pdf_id") or (pdfs[0]["id"] if pdfs else None)

    return render_template(
        "index.html",
        pdfs=pdfs,
        show_upload=request.args.get("upload") == "1",
        selected_pdf=selected_pdf,
        conversations=get_conversations(session["user_id"], selected_pdf)
    )


@app.route("/library")
@login_required
def library():
    return render_template(
        "library.html",
        pdfs=get_uploaded_pdfs(session["user_id"]),
    )


# --------------------------------------------------
# UPLOAD PDF
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload_pdf():

    try:

        # Check if PDF was received
        if "pdf" not in request.files:

            return render_template(
                "index.html",
                message="❌ No PDF file was received.",
                pdfs=get_uploaded_pdfs(session["user_id"])
            )

        pdf = request.files["pdf"]

        # Check filename
        if pdf.filename == "":

            return render_template(
                "index.html",
                message="❌ No PDF selected.",
                pdfs=get_uploaded_pdfs(session["user_id"])
            )

        # Check extension
        if not pdf.filename.lower().endswith(".pdf"):

            return render_template(
                "index.html",
                message="❌ Please upload a PDF file.",
                pdfs=get_uploaded_pdfs(session["user_id"])
            )

        # Get safe filename
        filename = os.path.basename(pdf.filename)

        # File path
        content = pdf.read()
        document = pymupdf.open(stream=content, filetype="pdf")
        file_id = store_pdf(filename, content)
        pdf_id = create_pdf(filename, session["user_id"], file_id, len(content), len(document))

        # Extract text page by page
        for page_number, page in enumerate(document, start=1):

            text = page.get_text().strip()

            if text:

                add_pdf_chunk(pdf_id, page_number, text)

        document.close()

        return render_template(
            "index.html",
            message=f"✅ '{filename}' uploaded successfully!",
            pdfs=get_uploaded_pdfs(session["user_id"]),
            selected_pdf=pdf_id,
            conversations=[]
        )

    except Exception as e:

        print("UPLOAD ERROR:", str(e))

        return render_template(
            "index.html",
            message=f"❌ Upload error: {str(e)}",
            pdfs=get_uploaded_pdfs(session["user_id"])
        )


# --------------------------------------------------
# ASK AI
# --------------------------------------------------

@app.route("/ask", methods=["POST"])
@login_required
def ask_ai():

    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    question = request.form.get(
        "question",
        ""
    ).strip()

    pdf_id = request.form.get("pdf_id")

    # Check question
    if not question:

        if wants_json:
            return jsonify({"error": "Please enter a question."}), 400

        return render_template(
            "index.html",
            answer="Please enter a question.",
            pdfs=get_uploaded_pdfs(session["user_id"])
        )

    # Check PDF selection
    if not pdf_id:

        if wants_json:
            return jsonify({"error": "Please select a PDF first."}), 400

        return render_template(
            "index.html",
            answer="❌ Please select a PDF first.",
            pdfs=get_uploaded_pdfs(session["user_id"])
        )

    try:

        chunks = get_pdf_chunks(pdf_id, session["user_id"])

        # No text found
        if not chunks:

            if wants_json:
                return jsonify({"error": "No text was found in this PDF."}), 400

            return render_template(
                "index.html",
                question=question,
                answer="❌ No text was found in this PDF.",
                pdfs=get_uploaded_pdfs(session["user_id"]),
                selected_pdf=pdf_id,
                conversations=get_conversations(session["user_id"], pdf_id)
            )

        # Ask AI
        answer = find_answer(
            question,
            chunks
        )

        add_chat_message(pdf_id, question, answer)

        if wants_json:
            return jsonify({"answer": answer})

        return render_template(
            "index.html",
            question=question,
            answer=answer,
            pdfs=get_uploaded_pdfs(session["user_id"]),
            selected_pdf=pdf_id,
            conversations=get_conversations(session["user_id"], pdf_id)
        )

    except Exception as e:

        print("AI ERROR:", str(e))

        if wants_json:
            return jsonify({"error": str(e)}), 500

        return render_template(
            "index.html",
            question=question,
            answer=f"❌ Error: {str(e)}",
            pdfs=get_uploaded_pdfs(session["user_id"]),
            selected_pdf=pdf_id,
            conversations=get_conversations(session["user_id"], pdf_id)
        )


# --------------------------------------------------
# DELETE PDF
# --------------------------------------------------

@app.route("/delete/<pdf_id>", methods=["POST"])
@login_required
def delete_pdf(pdf_id):

    try:
        pdf = get_pdf(pdf_id, session["user_id"])

        # PDF doesn't exist
        if not pdf:

            return render_template(
                "index.html",
                message="❌ PDF not found.",
                pdfs=get_uploaded_pdfs(session["user_id"])
            )

        filename = pdf["filename"]

        delete_pdf_record(pdf_id, session["user_id"])

        return render_template(
            "index.html",
            message=f"✅ '{filename}' deleted successfully!",
            pdfs=get_uploaded_pdfs(session["user_id"])
        )

    except Exception as e:

        print("DELETE ERROR:", str(e))

        return render_template(
            "index.html",
            message=f"❌ Delete error: {str(e)}",
            pdfs=get_uploaded_pdfs(session["user_id"])
        )

# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(debug=True)