from io import BytesIO
from collections import defaultdict
from typing import Dict, Any, List
from pymongo.database import Database
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


def _parse_seat(seat_no: str):
    """
    Parse a seat label like 'A1' into (col_index, row_index) zero-based.
    """
    if not seat_no or len(seat_no) < 2:
        return None, None
    col_letter = seat_no[0].upper()
    try:
        row_number = int(seat_no[1:])
    except ValueError:
        return None, None

    col_index = ord(col_letter) - ord("A")
    row_index = row_number - 1
    return col_index, row_index


def generate_seating_pdf(db: Database) -> BytesIO:
    """
    Generates the Seating Matrix PDF in PORTRAIT mode.
    - Each room falls on a separate paper.
    - Explicit padding added to prevent TypeError: int + NoneType.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    heading_style = styles["Heading2"]
    heading_style.alignment = 1 

    story: List[Any] = []

    rooms_map = {r["room_no"]: {"rows": int(r["no_of_rows"]), "cols": int(r["no_of_columns"])} 
                 for r in db.rooms.find({})}

    students_by_room = defaultdict(list)
    for s in db.students.find({"room_no": {"$ne": None}}):
        students_by_room[s["room_no"]].append(s)

    if not students_by_room:
        story.append(Paragraph("No allocated students to display.", heading_style))
        doc.build(story)
        buffer.seek(0)
        return buffer

    sorted_rooms = sorted(students_by_room.keys())
    for i, room_no in enumerate(sorted_rooms):
        room_cfg = rooms_map.get(room_no)
        if not room_cfg: continue

        rows, cols = room_cfg["rows"], room_cfg["cols"]
        grid = [["" for _ in range(cols)] for _ in range(rows)]

        for s in students_by_room[room_no]:
            col_idx, row_idx = _parse_seat(str(s.get("seat_no")))
            if col_idx is not None and 0 <= col_idx < cols and 0 <= row_idx < rows:
                grid[row_idx][col_idx] = f"{s.get('student_id')}\n({s.get('seat_no')})"

        header_row = [""] + [chr(ord("A") + c) for c in range(cols)]
        table_data = [header_row] + [[str(r + 1)] + grid[r] for r in range(rows)]

        # --- SCALE MATRIX TO FILL A4 ---
        available_width = 535 
        col_width = available_width / (cols + 1)
        
        # Use rowHeights argument instead of _argH to avoid internal NoneType issues
        row_heights = [35] * len(table_data)
        table = Table(table_data, colWidths=[col_width] * (cols + 1), rowHeights=row_heights, repeatRows=1)
        
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            # FIX: Explicit padding prevents the TypeError crash
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(Paragraph(f"Room Arrangement: {room_no}", heading_style))
        story.append(Spacer(1, 15))
        story.append(table)
        
        if i < len(sorted_rooms) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_attendance_pdf(db: Database) -> BytesIO:
    """
    Generates a Room-wise Attendance Sheet.
    - Updated with explicit padding for safety.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    title_style.alignment = 1 
    normal_style = styles["Normal"]

    story: List[Any] = []

    cursor = db.students.find({"room_no": {"$ne": None}}).sort([
        ("room_no", 1),
        ("div", 1),
        ("student_id", 1)
    ])

    room_data = defaultdict(list)
    for s in cursor:
        room_data[s["room_no"]].append(s)

    if not room_data:
        story.append(Paragraph("No allocated students found.", title_style))
        doc.build(story)
        buffer.seek(0)
        return buffer

    for room_no in sorted(room_data.keys()):
        students = room_data[room_no]
        
        story.append(Paragraph("EXAM ATTENDANCE SHEET", title_style))
        story.append(Spacer(1, 10))

        header_data = [[f"Room No: {room_no}", "Date: ____________________"]]
        header_table = Table(header_data, colWidths=[235, 235])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 15))

        table_data = [["Sr. No", "Div", "Student ID", "Student Name", "Signature"]]
        for i, s in enumerate(students, 1):
            table_data.append([
                str(i),
                str(s.get("div", "")),
                str(s.get("student_id", "")),
                str(s.get("name", "")),
                "" 
            ])

        table = Table(table_data, colWidths=[35, 35, 90, 200, 110], repeatRows=1)
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (3, 0), (3, -1), 'LEFT'), 
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(table)
        story.append(Spacer(1, 30))

        footer_data = [
            [Paragraph(f"<b>Invigilator Name:</b> ____________________", normal_style), 
             Paragraph(f"<b>Signature:</b> ____________________", normal_style)],
            [Paragraph(f"<br/><br/><b>Absentees:</b><br/>"
                       f"________________________________________________________________________", normal_style), ""]
        ]
        
        footer_table = Table(footer_data, colWidths=[235, 235])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('SPAN', (0, 1), (1, 1)),
        ]))
        
        story.append(footer_table)
        story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer