import os
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from dotenv import load_dotenv
from gridfs import GridFS
from pymongo import ASCENDING, DESCENDING, MongoClient


load_dotenv()

_client = None
_database = None


def get_database():
    global _client, _database

    if _database is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not configured.")

        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _database = _client[os.environ.get("MONGODB_DATABASE", "chat_pdf_db")]
        _database.users.create_index("email", unique=True)
        _database.pdfs.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        _database.chat_messages.create_index([("pdf_id", ASCENDING), ("created_at", ASCENDING)])

    return _database


def get_file_store():
    return GridFS(get_database())


def new_id():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


def find_user_by_email(email):
    return get_database().users.find_one({"email": email})


def create_user(name, email, password_hash):
    user = {
        "_id": new_id(),
        "name": name,
        "email": email,
        "password_hash": password_hash,
        "created_at": now(),
    }
    get_database().users.insert_one(user)
    return user


def claim_unowned_pdfs(user_id):
    get_database().pdfs.update_many(
        {"user_id": None},
        {"$set": {"user_id": user_id}},
    )


def list_pdfs(user_id):
    database = get_database()
    pdfs = list(database.pdfs.find({"user_id": user_id}).sort("created_at", DESCENDING))
    for pdf in pdfs:
        pdf["id"] = pdf.pop("_id")
        pdf["message_count"] = database.chat_messages.count_documents({"pdf_id": pdf["id"]})
        pdf.setdefault("file_size", 0)
    return pdfs


def get_pdf(pdf_id, user_id):
    pdf = get_database().pdfs.find_one({"_id": pdf_id, "user_id": user_id})
    if pdf:
        pdf["id"] = pdf.pop("_id")
    return pdf


def store_pdf(filename, content):
    return get_file_store().put(
        BytesIO(content),
        filename=filename,
        content_type="application/pdf",
        uploadDate=now(),
    )


def create_pdf(filename, user_id, file_id, file_size, page_count):
    pdf = {
        "_id": new_id(),
        "filename": filename,
        "user_id": user_id,
        "file_id": file_id,
        "file_size": file_size,
        "page_count": page_count,
        "created_at": now(),
    }
    get_database().pdfs.insert_one(pdf)
    return pdf["_id"]


def add_pdf_chunk(pdf_id, page_number, content):
    get_database().pdf_chunks.insert_one({
        "pdf_id": pdf_id,
        "page_number": page_number,
        "content": content,
    })


def get_pdf_chunks(pdf_id, user_id):
    database = get_database()
    if not database.pdfs.find_one({"_id": pdf_id, "user_id": user_id}, {"_id": 1}):
        return []
    return list(database.pdf_chunks.find(
        {"pdf_id": pdf_id}, {"_id": 0, "page_number": 1, "content": 1}
    ).sort("page_number", ASCENDING))


def list_conversations(user_id, pdf_id):
    database = get_database()
    if not database.pdfs.find_one({"_id": pdf_id, "user_id": user_id}, {"_id": 1}):
        return []
    return list(database.chat_messages.find(
        {"pdf_id": pdf_id}, {"_id": 0, "question": 1, "answer": 1, "created_at": 1}
    ).sort("created_at", ASCENDING))


def add_chat_message(pdf_id, question, answer):
    get_database().chat_messages.insert_one({
        "pdf_id": pdf_id,
        "question": question,
        "answer": answer,
        "created_at": now(),
    })


def delete_pdf(pdf_id, user_id):
    database = get_database()
    pdf = database.pdfs.find_one_and_delete({"_id": pdf_id, "user_id": user_id})
    if pdf:
        if pdf.get("file_id"):
            get_file_store().delete(pdf["file_id"])
        database.pdf_chunks.delete_many({"pdf_id": pdf_id})
        database.chat_messages.delete_many({"pdf_id": pdf_id})
    return pdf


if __name__ == "__main__":
    get_database().command("ping")
    print("MongoDB connection successful!")