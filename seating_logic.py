import random
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Any, Optional
from pymongo import MongoClient
from pymongo.database import Database

GroupKey = Tuple[int, str, str] 

def _seat_label(col_index: int, row_index: int) -> str:
    column_letter = chr(ord("A") + col_index)
    return f"{column_letter}{row_index + 1}"

def _fetch_unallocated_students(db: Database) -> Dict[GroupKey, deque]:
    groups: Dict[GroupKey, deque] = defaultdict(deque)
    # We still sort student_id so that WITHIN a column, they are sequential (01, 02, 03)
    cursor = db.students.find({"room_no": None}).sort([
        ("year", 1), ("dept", 1), ("div", 1), ("student_id", 1)
    ])
    for student in cursor:
        key: GroupKey = (int(student["year"]), str(student["dept"]), str(student["div"]))
        groups[key].append(student)
    return groups

def _fetch_rooms(db: Database) -> List[Dict[str, Any]]:
    rooms_cursor = db.rooms.find({})
    rooms = []
    for r in rooms_cursor:
        rooms.append({
            "room_no": r["room_no"], 
            "capacity": int(r["capacity"]), 
            "rows": int(r["no_of_rows"]), 
            "cols": int(r["no_of_columns"])
        })
    return rooms

def _assign_seats_for_hall(room: Dict[str, Any], all_group_keys: List[GroupKey], remaining_groups: Dict[GroupKey, deque]) -> List[Dict[str, Any]]:
    room_no = room["room_no"]
    rows, cols = room["rows"], room["cols"]
    assignments = []
    grid = [[None for _ in range(cols)] for _ in range(rows)]

    for col_index in range(cols):
        # 1. Identify valid groups that don't clash horizontally with the previous column
        left_neighbor_at_start = grid[0][col_index - 1] if col_index > 0 else None
        
        valid_keys = []
        for gk in all_group_keys:
            if remaining_groups[gk]:
                # Horizontal rule: Different Dept OR Different Year
                if left_neighbor_at_start is None or (str(gk[1]) != str(left_neighbor_at_start["dept"]) or int(gk[0]) != int(left_neighbor_at_start["year"])):
                    valid_keys.append(gk)
        
        if not valid_keys:
            # Emergency fallback: pick any group that has students left
            valid_keys = [gk for gk in all_group_keys if remaining_groups[gk]]
            if not valid_keys: break
        
        # RANDOMNESS INTRODUCED HERE: 
        # Pick a random group from the valid candidates for this column
        chosen_group_key = random.choice(valid_keys)

        # 2. Fill the column vertically with the CHOSEN group sequentially
        for row_index in range(rows):
            # If the group runs out of students mid-column, pick a new valid group
            if not remaining_groups[chosen_group_key]:
                valid_keys = [gk for gk in all_group_keys if remaining_groups[gk]]
                left_neighbor = grid[row_index][col_index - 1] if col_index > 0 else None
                
                row_valid = [
                    gk for gk in valid_keys 
                    if left_neighbor is None or (str(gk[1]) != str(left_neighbor["dept"]) or int(gk[0]) != int(left_neighbor["year"]))
                ]
                if not row_valid: break
                chosen_group_key = random.choice(row_valid)

            student = remaining_groups[chosen_group_key].popleft()
            grid[row_index][col_index] = student
            assignments.append({
                "student_id": student["student_id"],
                "room_no": room_no,
                "seat_no": _seat_label(col_index, row_index),
                "col_index": col_index,
                "row_index": row_index,
                "dept": student["dept"],
                "year": student["year"]
            })
            
    return assignments

def allocate_exam_seating_for_db(db: Database):
    remaining_groups = _fetch_unallocated_students(db)
    rooms = _fetch_rooms(db)
    if not remaining_groups or not rooms: return {}
    
    # Get all groups that actually have students
    all_group_keys = [k for k, v in remaining_groups.items() if v]
    
    all_hall_assignments = defaultdict(list)
    
    # Shuffle the rooms so different rooms get assigned different students each run
    random.shuffle(rooms)
    
    for room in rooms:
        # Every time we assign a hall, we pass the full list of groups.
        # The internal logic now uses random.choice() to pick the column group.
        hall_assignments = _assign_seats_for_hall(room, all_group_keys, remaining_groups)
        if not hall_assignments: continue
        
        all_hall_assignments[room["room_no"]].extend(hall_assignments)
        
        # Batch update database
        for assign in hall_assignments:
            db.students.update_one(
                {"student_id": assign["student_id"]}, 
                {"$set": {"room_no": room["room_no"], "seat_no": assign["seat_no"]}}
            )
            
    return all_hall_assignments

def allocate_seating(db: Database):
    all_hall_assignments = allocate_exam_seating_for_db(db)
    table_rows = []
    # Sorting keys for a consistent final report view, even if allocation was random
    for room_no in sorted(all_hall_assignments.keys()):
        assignments = all_hall_assignments[room_no]
        sorted_assignments = sorted(assignments, key=lambda a: (a["col_index"], a["row_index"]))
        for a in sorted_assignments:
            table_rows.append({
                "hall": room_no, 
                "column": chr(ord("A") + a["col_index"]), 
                "seat": a["seat_no"], 
                "student_id": a["student_id"]
            })
    return table_rows