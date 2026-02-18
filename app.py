from flask import Flask, render_template, request, send_file
from pymongo import MongoClient
import csv
from io import StringIO
from pdf_service import generate_seating_pdf
from datetime import datetime
from seating_logic import allocate_seating

connection_string = "mongodb+srv://avanthikapraveen:avanthikapraveen@miniproject.dqiy1p3.mongodb.net/?appName=Miniproject"
client = MongoClient(connection_string)
db = client["exam_seating_db"]
students_collection = db["students"]

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    registration_number = request.form.get('registration_number', '').strip().upper()
    if not registration_number:
        return render_template('index.html', error="Please enter a registration number.")
    
    student_info = students_collection.find_one({"student_id": registration_number})
    if student_info:
        return render_template('result.html', registration_number=registration_number, student_info=student_info)
    else:
        return render_template('index.html', error=f"Registration number '{registration_number}' not found.")

@app.route("/admin/upload", methods=["GET", "POST"])
def admin_upload():
    message = None
    error = None

    if request.method == "POST":
        if "upload_students" in request.form:
            file = request.files.get("students_csv")
            if not file or file.filename == "":
                error = "Please choose a Students CSV file to upload."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    required_fields = {"student_id", "dept", "year", "div"}
                    if not required_fields.issubset(reader.fieldnames or []):
                        error = "Students CSV must contain columns: student_id, dept, year, div."
                    else:
                        docs = []
                        for row in reader:
                            if not row.get("student_id"):
                                continue
                            doc = {
                                "student_id": row["student_id"].strip().upper(),
                                "dept": row["dept"].strip(),
                                "year": int(row["year"]),
                                "div": row["div"].strip(),
                                "room_no": None,
                                "seat_no": None,
                            }
                            docs.append(doc)
                        if docs:
                            db.drop_collection("students")
                            global students_collection
                            students_collection = db["students"]
                            students_collection.insert_many(docs)
                            message = f"Uploaded {len(docs)} students successfully."
                        else:
                            error = "No valid student records found in the CSV."
                except Exception as e:
                    error = f"Error processing Students CSV: {e}"

        elif "upload_halls" in request.form:
            file = request.files.get("halls_csv")
            if not file or file.filename == "":
                error = "Please choose a Halls CSV file to upload."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    required_fields = {"room_no", "capacity", "no_of_rows", "no_of_columns"}
                    if not required_fields.issubset(reader.fieldnames or []):
                        error = "Halls CSV must contain columns: room_no, capacity, no_of_rows, no_of_columns."
                    else:
                        rooms_collection = db["rooms"]
                        docs = []
                        for row in reader:
                            if not row.get("room_no"):
                                continue
                            doc = {
                                "room_no": row["room_no"].strip(),
                                "capacity": int(row["capacity"]),
                                "no_of_rows": int(row["no_of_rows"]),
                                "no_of_columns": int(row["no_of_columns"]),
                            }
                            docs.append(doc)
                        if docs:
                            db.drop_collection("rooms")
                            rooms_collection = db["rooms"]
                            rooms_collection.insert_many(docs)
                            message = f"Uploaded {len(docs)} halls successfully."
                        else:
                            error = "No valid hall records found in the CSV."
                except Exception as e:
                    error = f"Error processing Halls CSV: {e}"

    return render_template("admin_upload.html", message=message, error=error)

@app.route("/admin/allocate")
def admin_allocate():
    """
    Admin dashboard for seating.
    Triggers allocation (if needed) but does not expose individual
    student details in the UI.
    """
    # Run allocation so that any newly uploaded/updated data is seated.
    # The returned table is ignored here to keep details hidden.
    allocate_seating(db)
    last_generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("admin_allocate.html", last_generated=last_generated)


@app.route("/admin/download-seating-pdf")
def download_seating_pdf():
    """
    Generate and download a PDF of the current seating arrangement,
    organized by room_no.
    """
    pdf_buffer = generate_seating_pdf(db)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="exam_seating.pdf",
    )

if __name__ == '__main__':
    app.run(debug=True)
