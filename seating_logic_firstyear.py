import random
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Any, Optional
from pymongo.database import Database

# Group students by Department (since Year is fixed at 1)
GroupKey = str  # Department Name

def _seat_label(col_index: int, row_index: int) -> str:
    column_letter = chr(ord("A") + col_index)
    return f"{column_letter}{row_index + 1}"

def _fetch_unallocated_students(db: Database) -> Dict[GroupKey, deque]:
    groups: Dict[GroupKey, deque] = defaultdict(deque)
    # Sort by student_id to maintain sequential roll numbers (01, 02, 03...)
    cursor = db.students.find({"room_no": None}).sort("student_id", 1)
    for student in cursor:
        key: GroupKey = str(student["dept"]).upper()
        groups[key].append(student)
    return groups

def _fetch_rooms(db: Database) -> List[Dict[str, Any]]:
    # Sort by room_no to follow the uploaded file sequence
    rooms_cursor = db.rooms.find({}).sort("room_no", 1)
    rooms = []
    for r in rooms_cursor:
        rooms.append({
            "room_no": r["room_no"], 
            "capacity": int(r["capacity"]), 
            "rows": int(r["no_of_rows"]), 
            "cols": int(r["no_of_columns"])
        })
    return rooms

def is_compatible(dept_a: str, dept_b: str) -> bool:
    """Checks if two departments are allowed to sit in adjacent columns."""
    if dept_a == dept_b:
        return False
    
    FORBIDDEN_PAIRS = [
        {"CSE", "AIML"},
        {"ECE", "EEE"}
    ]
    pair = {dept_a.upper(), dept_b.upper()}
    for forbidden in FORBIDDEN_PAIRS:
        if forbidden.issubset(pair):
            return False
    return True

def _assign_seats_for_hall(room: Dict[str, Any], all_group_keys: List[GroupKey], remaining_groups: Dict[GroupKey, deque]) -> List[Dict[str, Any]]:
    room_no = room["room_no"]
    rows, cols = room["rows"], room["cols"]
    assignments = []
    grid = [[None for _ in range(cols)] for _ in range(rows)]

    for col_index in range(cols):
        # 1. Identify left neighbor to check for clashes
        left_neighbor_dept = grid[0][col_index - 1]["dept"] if col_index > 0 else None
        
        # TIER 1: Compatible & Randomized Candidates
        valid_keys = [
            gk for gk in all_group_keys 
            if remaining_groups[gk] and (left_neighbor_dept is None or is_compatible(gk, left_neighbor_dept))
        ]
        
        # TIER 2: Compromise (If no compatible partners left, pick any different dept)
        if not valid_keys:
            valid_keys = [gk for gk in all_group_keys if remaining_groups[gk] and gk != left_neighbor_dept]
        
        # TIER 3: Absolute Compromise (Pick anything left)
        if not valid_keys:
            valid_keys = [gk for gk in all_group_keys if remaining_groups[gk]]
            
        if not valid_keys: 
            break
        
        # RANDOMIZATION: Pick a random dept from the current valid candidates
        chosen_dept = random.choice(valid_keys)

        # 2. Fill the column vertically sequentially
        for row_index in range(rows):
            # If the dept runs out mid-column, find a new candidate using the same priority tiers
            if not remaining_groups[chosen_dept]:
                left_dept = grid[row_index][col_index - 1]["dept"] if col_index > 0 else None
                
                # Re-apply Tiers
                tier1 = [gk for gk in all_group_keys if remaining_groups[gk] and (left_dept is None or is_compatible(gk, left_dept))]
                if tier1:
                    chosen_dept = random.choice(tier1)
                else:
                    tier2 = [gk for gk in all_group_keys if remaining_groups[gk]]
                    if not tier2: break
                    chosen_dept = random.choice(tier2)

            student = remaining_groups[chosen_dept].popleft()
            grid[row_index][col_index] = student
            assignments.append({
                "student_id": student["student_id"],
                "room_no": room_no,
                "seat_no": _seat_label(col_index, row_index),
                "col_index": col_index,
                "row_index": row_index,
                "dept": student["dept"]
            })
            
    return assignments

def allocate_firstyear_seating(db: Database):
    """Main function to trigger First Year Allocation."""
    remaining_groups = _fetch_unallocated_students(db)
    rooms = _fetch_rooms(db)
    if not remaining_groups or not rooms: return []
    
    all_group_keys = [k for k, v in remaining_groups.items() if v]
    all_hall_assignments = defaultdict(list)
    
    # Process rooms in sequential order as per the file
    for room in rooms:
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