from io import BytesIO
from collections import defaultdict
from typing import Dict, Any, List

from pymongo.database import Database
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


def _parse_seat(seat_no: str):
    """
    Parse a seat label like 'A1' into (col_index, row_index) zero-based.
    Assumes a single-letter column (A-Z) and 1-based row numbers.
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
    Generate a PDF containing the exam seating arrangement for all rooms
    that have allocated students.

    Layout:
      - One section per room (room_no), with a centered heading.
      - Below each heading, a table representing the physical grid.
      - Rows correspond to row_index (1..N), columns to letters (A, B, C...).
      - Each cell shows "student_id\n(seat_no)" when occupied, otherwise blank.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    heading_style = styles["Heading2"]
    heading_style.alignment = 1  # center

    story: List[Any] = []

    # Fetch room definitions
    rooms_map: Dict[Any, Dict[str, Any]] = {}
    for r in db.rooms.find({}):
        rooms_map[r["room_no"]] = {
            "rows": int(r["no_of_rows"]),
            "cols": int(r["no_of_columns"]),
        }

    # Group students by room_no (only allocated students)
    students_by_room: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for s in db.students.find({"room_no": {"$ne": None}}):
        students_by_room[s["room_no"]].append(s)

    # If no allocated students, still create an empty PDF with a note
    if not students_by_room:
        story.append(Paragraph("No allocated students to display.", heading_style))
        doc.build(story)
        buffer.seek(0)
        return buffer

    for room_no in sorted(students_by_room.keys()):
        room_cfg = rooms_map.get(room_no)
        if not room_cfg:
            # Skip rooms without layout info
            continue

        rows = room_cfg["rows"]
        cols = room_cfg["cols"]

        # Initialize grid with empty strings
        grid = [["" for _ in range(cols)] for _ in range(rows)]

        for s in students_by_room[room_no]:
            seat_no = s.get("seat_no")
            student_id = s.get("student_id", "")
            col_index, row_index = _parse_seat(str(seat_no))
            if (
                col_index is None
                or row_index is None
                or col_index < 0
                or row_index < 0
                or col_index >= cols
                or row_index >= rows
            ):
                continue
            grid[row_index][col_index] = f"{student_id}\n({seat_no})"

        # Build table data with header row/column labels
        header_row = [""] + [chr(ord("A") + c) for c in range(cols)]
        table_data = [header_row]
        for r_idx in range(rows):
            row_label = str(r_idx + 1)
            table_data.append([row_label] + grid[r_idx])

        # Add room heading
        story.append(Paragraph(f"Room {room_no}", heading_style))
        story.append(Spacer(1, 12))

        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )

        story.append(table)
        story.append(Spacer(1, 24))

    doc.build(story)
    buffer.seek(0)
    return buffer

