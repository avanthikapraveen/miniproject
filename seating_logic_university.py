from collections import deque

def allocate_university_seating(db):
    """
    Deterministic University Seating:
    - Zero Randomization: Uses fixed alphabetical sorting.
    - Sequential Start: Begins with student '01' for every department.
    - Custom Combination: Slot 0 and Slot 1 start with different department offsets
      to create a specific pairing, then waterfall sequentially.
    - Continuity: Pointers never reset between rooms.
    """
    
    # 1. Clear previous data
    db.students.update_many({}, {"$set": {"room_no": None, "seat_no": None}})

    # 2. Group students by Dept and sort by ID (Roll No order)
    # Sorting by 'student_id' ensures we start with ...01, ...02, etc.
    students_cursor = db.students.find({}).sort("student_id", 1)
    
    dept_queues = {}
    for s in students_cursor:
        dept = s['dept']
        if dept not in dept_queues:
            dept_queues[dept] = deque()
        dept_queues[dept].append(s)
    
    # 3. FIXED Alphabetical Department List
    # Sorting ensures the order is always the same (e.g., CSE, ECE, EEE)
    dept_list = sorted(list(dept_queues.keys()))
    
    if not dept_list:
        return "No students found."

    # 4. Initialize Active Slot Pointers
    # Slot 0 (Even Columns) starts at index 0 (e.g., CSE)
    # Slot 1 (Odd Columns) starts at index 1 (e.g., ECE)
    # This creates a fixed combination (CSE-ECE) without randomization.
    active_slots = [0, 1 if len(dept_list) > 1 else 0]

    # 5. Process Rooms in the order they were uploaded
    rooms = list(db.rooms.find({}).sort("room_no", 1))

    for room in rooms:
        room_no = room['room_no']
        cols = int(room['no_of_columns'])
        rows = int(room['no_of_rows'])

        # Vertical Column-by-Column Filling
        for c in range(cols):
            # Binary Interleaving: Even (A,C,E) = Slot 0, Odd (B,D,F) = Slot 1
            slot_idx = c % 2
            
            for r in range(rows):
                dept_idx = active_slots[slot_idx]
                current_dept_name = dept_list[dept_idx]

                # Waterfall Logic: If current dept is exhausted, move to next available
                if not dept_queues[current_dept_name]:
                    found_next = False
                    other_slot_idx = (slot_idx + 1) % 2
                    other_dept_idx = active_slots[other_slot_idx]

                    # Deterministically search the next dept in the sorted list
                    for i in range(len(dept_list)):
                        next_idx = (dept_idx + i) % len(dept_list)
                        if next_idx != other_dept_idx and dept_queues[dept_list[next_idx]]:
                            active_slots[slot_idx] = next_idx
                            current_dept_name = dept_list[next_idx]
                            found_next = True
                            break
                    
                    if not found_next:
                        # Only one dept remains in the entire dataset
                        if dept_queues[dept_list[other_dept_idx]]:
                            active_slots[slot_idx] = other_dept_idx
                            current_dept_name = dept_list[other_dept_idx]
                        else:
                            # Hall is empty or all students seated
                            continue

                # Pop student in strict ID order
                student = dept_queues[current_dept_name].popleft()
                
                # Seat Label (A1, A2, A3...)
                seat_label = f"{chr(65 + c)}{r + 1}"

                db.students.update_one(
                    {"_id": student["_id"]},
                    {"$set": {
                        "room_no": room_no, 
                        "seat_no": seat_label
                    }}
                )

    return "Deterministic Allocation Complete."