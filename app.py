from flask import Flask, request, render_template, jsonify
import re

app = Flask(__name__)

def parse_schedule(text):
    """Parse the exam schedule text and extract all duty assignments."""
    duties = []
    current_date, current_time = None, None
    
    lines = text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and headers
        if not line or 'Port City International University' in line or 'Dean, Faculty' in line or 'Updated on' in line:
            i += 1
            continue
            
        # Detect Date & Time
        date_time_match = re.search(r'Date:\s*(\d{2}/\d{2}/\d{4}.*?)\s+Time:\s*([0-9:apm\-\s()]+)', line)
        if date_time_match:
            current_date = date_time_match.group(1).strip()
            current_time = date_time_match.group(2).strip()
            i += 1
            continue
            
        # Skip table headers and separators
        if any(header in line for header in ['Course Code', 'Course Title', 'Program', 'Room', 'ID No', 'Invigilator', '---', 'Rest=', 'Page |']):
            i += 1
            continue
            
        # Look for course entries - they start with a course code pattern
        course_match = re.match(r'^([A-Z]{2,4}\s*\d{3})\s+(.+)', line)
        if course_match and current_date and current_time:
            course_code = course_match.group(1).strip()
            remaining_text = course_match.group(2).strip()
            
            # Extract course title (keeping for parsing, but not using in results)
            title_match = re.search(r'^(.*?)(?:\s+[A-Z]{2,4}-\d+|\s+\d{3}\s*\()', remaining_text)
            course_title = title_match.group(1).strip() if title_match else remaining_text.split()[0] if remaining_text else "Unknown"
            
            # Now parse the room and invigilator assignments
            full_entry = remaining_text
            j = i + 1
            
            # Collect all lines that belong to this course until we hit another course or date
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                    
                # Stop if we hit another course code or date
                if re.match(r'^[A-Z]{2,4}\s*\d{3}\s+', next_line) or 'Date:' in next_line:
                    break
                    
                # Stop if we hit separators or headers
                if any(sep in next_line for sep in ['---', 'Course Code', 'Port City International', 'Page |']):
                    break
                    
                full_entry += ' ' + next_line
                j += 1
            
            # Parse room assignments from the full entry
            room_duties = parse_room_assignments(course_code, course_title, full_entry, current_date, current_time)
            duties.extend(room_duties)
            i = j
        else:
            i += 1
    
    return duties

def parse_room_assignments(course_code, course_title, entry_text, date, time):
    """Parse room assignments and invigilators from course entry text."""
    duties = []
    
    # Clean up the entry text
    entry_text = re.sub(r'\s+', ' ', entry_text).strip()
    
    # Method 1: Look for explicit room patterns like "308 (20)3509803-822 ZBS+MNJ"
    room_pattern = r'(\d{3})\s*\([^)]+\)[^A-Z]*([A-Z][A-Za-z0-9+\s]*?)(?=\s+\d{3}\s*\(|\s+[A-Z]{2,4}-\d+|$)'
    room_matches = re.findall(room_pattern, entry_text)
    
    for room, invig_text in room_matches:
        invigilators = extract_invigilator_codes(invig_text)
        if invigilators:
            duties.append({
                "date": date,
                "time": time,
                "course": course_code,
                "title": course_title,
                "room": room,
                "invigilators": invigilators
            })
    
    # Method 2: If no clear patterns found, try a more flexible approach
    if not duties:
        # Extract all room numbers and all invigilator codes
        rooms = re.findall(r'\b(\d{3})\b', entry_text)
        all_invig_text = entry_text
        
        # Remove program codes, ID numbers, and other non-invigilator text
        all_invig_text = re.sub(r'[A-Z]{2,4}-\d+\(\d+\)', '', all_invig_text)  # Remove program codes
        all_invig_text = re.sub(r'\d{3}\s*\([^)]+\)[0-9\-+rest\s]*', ' ', all_invig_text)  # Remove room info
        all_invig_text = re.sub(r'\d{7,}', '', all_invig_text)  # Remove ID numbers
        
        invigilators = extract_invigilator_codes(all_invig_text)
        
        # Create entries for each room found
        for room in rooms:
            duties.append({
                "date": date,
                "time": time,
                "course": course_code,
                "title": course_title,
                "room": room,
                "invigilators": invigilators
            })
    
    # Method 3: Handle cases with single room and clear invigilator list
    if not duties:
        single_room_match = re.search(r'(\d{3})\s*\([^)]+\)', entry_text)
        if single_room_match:
            room = single_room_match.group(1)
            # Get text after the room info
            after_room = entry_text[single_room_match.end():]
            invigilators = extract_invigilator_codes(after_room)
            
            duties.append({
                "date": date,
                "time": time,
                "course": course_code,
                "title": course_title,
                "room": room,
                "invigilators": invigilators
            })
    
    return duties

def extract_invigilator_codes(text):
    """Extract invigilator codes from text."""
    if not text:
        return []
    
    # Clean the text
    text = text.strip()
    
    # Remove obvious non-invigilator patterns
    text = re.sub(r'\d{7,}', '', text)  # Remove long ID numbers
    text = re.sub(r'[A-Z]{2,4}-\d+', '', text)  # Remove program codes
    text = re.sub(r'\(\d+\)', '', text)  # Remove capacity numbers
    text = re.sub(r'\d{3}', '', text)  # Remove room numbers
    text = re.sub(r'rest', '', text)  # Remove 'rest' keyword
    
    # Extract invigilator codes - allow 2-4 letters (mixed case) optionally followed by a number
    invig_pattern = r'\b([A-Za-z]{2,4}\d{0,2})\b'
    codes = re.findall(invig_pattern, text)
    
    # Filter out codes that are too short or look like other identifiers
    valid_codes = []
    for code in codes:
        # Must be at least 2 characters
        if len(code) >= 2:
            # Exclude obvious non-invigilator codes (case-insensitive)
            if not re.match(r'^(BBA|CSE|ENG|TEX|BTE|EEE|CEN|LLB|JRN|BFT|LLM|MJR|ENF)$', code, re.IGNORECASE):
                valid_codes.append(code.upper())  # Normalize to uppercase for consistency
    
    return valid_codes

def find_invigilator_duties(duties, code):
    """Find all duties for a specific invigilator code."""
    code = code.upper()
    matching_duties = []
    for duty in duties:
        for invig in duty["invigilators"]:
            if invig.upper() == code:
                matching_duties.append(duty)
                break
    return matching_duties

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_duties():
    try:
        data = request.get_json()
        schedule_text = data.get('schedule_text', '').strip()
        invigilator_code = data.get('invigilator_code', '').strip().upper()
        
        if not schedule_text:
            return jsonify({'error': 'Please provide the exam schedule text.'})
        
        if not invigilator_code:
            return jsonify({'error': 'Please provide an invigilator code.'})
        
        # Parse the schedule
        duties = parse_schedule(schedule_text)
        
        if not duties:
            return jsonify({'error': 'No duties could be parsed from the text. Please check the format.'})
        
        # Find duties for the specific invigilator
        invig_duties = find_invigilator_duties(duties, invigilator_code)
        
        if not invig_duties:
            # Get sample invigilator codes
            all_invigilators = set()
            for duty in duties:
                all_invigilators.update(duty['invigilators'])
            sample_codes = sorted(list(all_invigilators))[:20]
            
            return jsonify({
                'error': f'No duties found for invigilator "{invigilator_code}".',
                'sample_codes': sample_codes
            })
        
        # Format the results without courses
        results = []
        for duty in invig_duties:
            # Get other invigilators
            others = [x for x in duty["invigilators"] if x.upper() != invigilator_code]
            
            results.append({
                'date': duty['date'],
                'time': duty['time'],
                'room': duty['room'],
                'other_invigilators': others
            })
        
        return jsonify({
            'success': True,
            'invigilator': invigilator_code,
            'total_duties': len(invig_duties),
            'duties': results
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'})

@app.route('/debug', methods=['POST'])
def debug_info():
    try:
        data = request.get_json()
        schedule_text = data.get('schedule_text', '').strip()
        
        if not schedule_text:
            return jsonify({'error': 'Please provide the exam schedule text.'})
        
        duties = parse_schedule(schedule_text)
        
        # Get sample duties
        sample_duties = duties[:5]
        
        # Get all unique invigilator codes
        all_invigilators = set()
        for duty in duties:
            all_invigilators.update(duty['invigilators'])
        
        return jsonify({
            'success': True,
            'total_duties': len(duties),
            'sample_duties': sample_duties,
            'total_invigilators': len(all_invigilators),
            'all_invigilators': sorted(list(all_invigilators))
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True)
