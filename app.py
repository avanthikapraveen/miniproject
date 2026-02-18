from flask import Flask, render_template, request, send_file
from pymongo import MongoClient
import csv
from io import StringIO
from pdf_service import generate_seating_pdf, generate_attendance_pdf
from datetime import datetime
from seating_logic import allocate_seating
# Import all logic modules
from seating_logic_firstyear import allocate_firstyear_seating
from seating_logic_university import allocate_university_seating

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
        # --- HANDLER 1: REGULAR STUDENTS (Multi-year) ---
        if "upload_students" in request.form:
            file = request.files.get("students_csv")
            if not file or file.filename == "":
                error = "Please choose a Students CSV file."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    required_fields = {"student_id", "dept", "year", "div", "name"}
                    if not required_fields.issubset(reader.fieldnames or []):
                        error = "CSV must contain: student_id, dept, year, div, name."
                    else:
                        docs = []
                        for row in reader:
                            if not row.get("student_id"): continue
                            docs.append({
                                "student_id": row["student_id"].strip().upper(),
                                "dept": row["dept"].strip(),
                                "year": int(row["year"]),
                                "div": row["div"].strip(),
                                "name": row["name"].upper(),
                                "room_no": None,
                                "seat_no": None,
                                "type": "regular"
                            })
                        if docs:
                            db.drop_collection("students")
                            db.students.insert_many(docs)
                            message = f"Uploaded {len(docs)} regular students successfully."
                except Exception as e:
                    error = f"Error: {e}"

        # --- HANDLER 2: UNIVERSITY STUDENTS (3year_sem.csv format) ---
        elif "upload_university" in request.form:
            file = request.files.get("university_csv")
            if not file or file.filename == "":
                error = "Please choose the University CSV file."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    required_fields = {"reg_no", "dept", "student_name"}
                    if not required_fields.issubset(reader.fieldnames or []):
                        error = "University CSV must contain: reg_no, dept, student_name."
                    else:
                        docs = []
                        for row in reader:
                            if not row.get("reg_no"): continue
                            docs.append({
                                "student_id": row["reg_no"].strip().upper(),
                                "dept": row["dept"].strip(),
                                "name": row["student_name"].upper(),
                                "year": None,
                                "div": None,
                                "room_no": None,
                                "seat_no": None,
                                "type": "university"
                            })
                        if docs:
                            db.drop_collection("students")
                            db.students.insert_many(docs)
                            message = f"Uploaded {len(docs)} university students successfully."
                except Exception as e:
                    error = f"Error: {e}"

        # --- HANDLER 3: FIRST YEAR INTERNAL (Specific Constraints) ---
        elif "upload_firstyear" in request.form:
            file = request.files.get("firstyear_csv")
            if not file or file.filename == "":
                error = "Please choose the First Year CSV file."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    required_fields = {"student_id", "dept", "name"}
                    if not required_fields.issubset(reader.fieldnames or []):
                        error = "First Year CSV must contain: student_id, dept, name."
                    else:
                        docs = []
                        for row in reader:
                            if not row.get("student_id"): continue
                            docs.append({
                                "student_id": row["student_id"].strip().upper(),
                                "dept": row["dept"].strip(),
                                "name": row["name"].upper(),
                                "year": 1, 
                                "div": None,
                                "room_no": None,
                                "seat_no": None,
                                "type": "firstyear"
                            })
                        if docs:
                            db.drop_collection("students")
                            db.students.insert_many(docs)
                            message = f"Uploaded {len(docs)} first-year students successfully."
                except Exception as e:
                    error = f"Error: {e}"

        # --- HANDLER 4: HALLS ---
        elif "upload_halls" in request.form:
            file = request.files.get("halls_csv")
            if not file or file.filename == "":
                error = "Please choose a Halls CSV file."
            else:
                try:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(StringIO(content))
                    if not {"room_no", "no_of_rows", "no_of_columns"}.issubset(reader.fieldnames or []):
                        error = "Halls CSV missing required columns."
                    else:
                        docs = []
                        for row in reader:
                            if not row.get("room_no"): continue
                            docs.append({
                                "room_no": row["room_no"].strip(),
                                "no_of_rows": int(row["no_of_rows"]),
                                "no_of_columns": int(row["no_of_columns"]),
                                "capacity": int(row.get("capacity", 0))
                            })
                        if docs:
                            db.drop_collection("rooms")
                            db.rooms.insert_many(docs)
                            message = f"Uploaded {len(docs)} halls successfully."
                except Exception as e:
                    error = f"Error: {e}"

    return render_template("admin_upload.html", message=message, error=error)

@app.route("/admin/allocate")
def admin_allocate():
    allocate_seating(db)
    last_generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("admin_allocate.html", last_generated=last_generated, exam_type="Regular")

@app.route("/admin/allocate-university")
def admin_allocate_university():
    allocate_university_seating(db)
    last_generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("admin_allocate.html", last_generated=last_generated, exam_type="University")

@app.route("/admin/allocate-firstyear")
def admin_allocate_firstyear():
    allocate_firstyear_seating(db)
    last_generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("admin_allocate.html", last_generated=last_generated, exam_type="First Year Internal")

@app.route("/admin/download-seating-pdf")
def download_seating_pdf():
    pdf_buffer = generate_seating_pdf(db)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="exam_seating_plan.pdf",
    )

@app.route("/admin/download-attendance-pdf")
def download_attendance_pdf():
    pdf_buffer = generate_attendance_pdf(db)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="attendance_sheets.pdf",
    )

if __name__ == '__main__':
    app.run(debug=True)