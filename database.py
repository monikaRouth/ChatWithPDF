import mysql.connector


def get_connection():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="chat_pdf_db"
    )

    return connection


# Step 23: Test MySQL connection
if __name__ == "__main__":
    try:
        connection = get_connection()

        if connection.is_connected():
            print("MySQL connection successful!")

        connection.close()

    except mysql.connector.Error as error:
        print("MySQL connection failed:", error)