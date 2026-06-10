# app.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import base64
import os 
from dotenv import load_dotenv
import json
import logging
import sqlite3
import hashlib
from typing import Optional, Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# ============== API KEYS CONFIGURATION ==============

GROQ_API_KEYS_STR = os.getenv('GROQ_API_KEYS', '')
GROQ_API_KEYS = [key.strip() for key in GROQ_API_KEYS_STR.split(',') if key.strip()]

SINGLE_GROQ_KEY = os.getenv('RESULTS_PROJ_APIKEY')
if SINGLE_GROQ_KEY and SINGLE_GROQ_KEY not in GROQ_API_KEYS:
    GROQ_API_KEYS.insert(0, SINGLE_GROQ_KEY)

logger.info(f"Loaded {len(GROQ_API_KEYS)} API keys")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False
)

# ============== DATABASE CONFIGURATION ==============

DB_FILE = "student_data.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # Table to store student records and computed GPAs
        conn.execute('''
            CREATE TABLE IF NOT EXISTS students (
                regno TEXT PRIMARY KEY,
                name TEXT,
                prev_cgpa REAL,
                prev_credits INTEGER,
                current_gpa REAL,
                current_credits INTEGER,
                new_cgpa REAL,
                results_json TEXT
            )
        ''')
        # Table to cache OCR results using SHA256 image hashes
        conn.execute('''
            CREATE TABLE IF NOT EXISTS image_cache (
                image_hash TEXT,
                prompt_type TEXT,
                ocr_result TEXT,
                PRIMARY KEY (image_hash, prompt_type)
            )
        ''')
        conn.commit()

init_db()

# ============== CUSTOM EXCEPTIONS ==============

class AppException(Exception):
    def __init__(
        self, 
        code: str, 
        message: str, 
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(AppException):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__("VALIDATION_ERROR", message, 400, details)

class SubjectNotFoundError(AppException):
    def __init__(self, subject_code: str):
        super().__init__(
            "SUBJECT_NOT_FOUND",
            f"Subject '{subject_code}' not found in database",
            422,
            {"subject_code": subject_code}
        )

class GradeNotFoundError(AppException):
    def __init__(self, grade: str):
        super().__init__(
            "GRADE_NOT_FOUND",
            f"Grade '{grade}' is not valid",
            422,
            {"grade": grade}
        )

class OCRError(AppException):
    def __init__(self, message: str = "Failed to extract text from image"):
        super().__init__("OCR_ERROR", message, 422)

class ExternalServiceError(AppException):
    def __init__(self, service: str, original_error: str = ""):
        super().__init__(
            "EXTERNAL_SERVICE_ERROR",
            f"Failed to communicate with {service}",
            502,
            {"service": service, "original_error": original_error}
        )

class AllKeysExhaustedError(AppException):
    def __init__(self):
        super().__init__(
            "ALL_KEYS_EXHAUSTED",
            "All API keys have been exhausted. Please try again later.",
            503
        )

class InvalidCreditsError(AppException):
    def __init__(self, subject_code: str):
        super().__init__(
            "INVALID_CREDITS",
            f"Credits for '{subject_code}' is missing",
            422,
            {"subject_code": subject_code}
        )

class NoResultsError(AppException):
    def __init__(self):
        super().__init__(
            "NO_RESULTS",
            "No valid results could be extracted from the image",
            422
        )

# ============== EXCEPTION HANDLERS ==============

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error(f"AppException: {exc.code} - {exc.message} - {exc.details}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": {}
            }
        }
    )

def success_response(data: Any) -> Dict:
    return {
        "success": True,
        "data": data,
        "error": None
    }

# ============== DATA STORAGE ==============

grade_points_map: Dict[str, int] = {}
subject_metadata: Dict[str, Dict] = {}

def load_static_data():
    global grade_points_map, subject_metadata
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(base_path, "./static")
        
        grade_file = os.path.join(static_dir, "grade-points.jsonl")
        credits_file = os.path.join(static_dir, "merged_credits.jsonl")
        
        if not os.path.exists(grade_file):
            logger.error(f"Grade points file not found: {grade_file}")
            return
        if not os.path.exists(credits_file):
            logger.error(f"Credits file not found: {credits_file}")
            return
        
        with open(grade_file, 'r', encoding="utf-8") as in_file:
            for line_num, line in enumerate(in_file, 1):
                try:
                    data = json.loads(line.strip())
                    if 'letter_grade' in data and 'grade_points' in data:
                        grade_points_map[data['letter_grade']] = data['grade_points']
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSON at line {line_num} in grade-points.jsonl")
        
        with open(credits_file, 'r', encoding="utf-8") as in_file:
            for line_num, line in enumerate(in_file, 1):
                try:
                    data = json.loads(line.strip())
                    if data.get('credits') is not None:
                        subject_metadata[data['subject_code']] = {
                            'credits': data['credits'],
                            'name': data.get('subject_name', 'Unknown Subject')
                        }
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSON at line {line_num} in merged_credits.jsonl")
        
        logger.info(f"Loaded {len(grade_points_map)} grades and {len(subject_metadata)} subjects")
        
    except Exception as err:
        logger.exception(f"Error loading static data: {err}")

load_static_data()

# ============== HELPER FUNCTIONS ==============

def clean_llm_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()

def calculate_gpa_logic(jsonl_string: str) -> List[Dict]:
    cleaned_text = clean_llm_json_response(jsonl_string)
    lines = [line for line in cleaned_text.split("\n") if line.strip()]
    
    if not lines:
        raise OCRError("No data could be extracted from the image")
    
    final_list = []
    skipped_subjects = []
    
    for line in lines:
        try:
            student_data = json.loads(line)
            
            if "error" in student_data:
                error_msg = student_data.get("message", "Image could not be processed")
                raise OCRError(error_msg)
            
            if "student_regno" not in student_data:
                logger.warning(f"Missing student_regno in: {line[:50]}...")
                continue
            if "student_name" not in student_data:
                logger.warning(f"Missing student_name in: {line[:50]}...")
                continue
            if "results" not in student_data or not student_data["results"]:
                logger.warning(f"No results for student: {student_data.get('student_regno')}")
                continue
            
            current_dict = {
                "student_regno": student_data["student_regno"],
                "student_name": student_data["student_name"],
                "results": []
            }
            
            acq_credits = 0
            total_credits = 0
            
            for data in student_data["results"]:
                sub_code = data.get('subject_code')
                grade = data.get('grade')
                
                if not sub_code:
                    logger.warning("Empty subject code found, skipping...")
                    continue
                
                if sub_code not in subject_metadata:
                    logger.warning(f"Subject '{sub_code}' not found in metadata")
                    if 'O' in sub_code and 'O' in sub_code[-3] and sub_code[:-3] + '0' + sub_code[-2:] in subject_metadata:
                        sub_code = sub_code[:-3] + '0' + sub_code[-2:]
                    else:
                        skipped_subjects.append(sub_code)
                        continue
                    
                if not grade or grade not in grade_points_map:
                    logger.warning(f"Grade '{grade}' not found for subject '{sub_code}'")
                    continue
                
                sub_info = subject_metadata[sub_code]
                
                credits = sub_info.get("credits")
                if credits is None or credits == 0:
                    logger.warning(f"Invalid credits for subject '{sub_code}'")
                    continue
                
                results_dict = {
                    "subject_code": sub_code,
                    "subject_name": sub_info.get("name", "Unknown"),
                    "grade": grade
                }
                
                acq_credits += grade_points_map[grade] * credits
                total_credits += credits
                current_dict["results"].append(results_dict)
            
            if total_credits > 0:
                gpa = round(acq_credits / total_credits, 2)
            else:
                gpa = 0.0
            
            current_dict["gpa"] = gpa
            current_dict["current_credits"] = total_credits
            
            if current_dict["results"]:
                final_list.append(current_dict)
            else:
                logger.warning(f"No valid subjects for student: {student_data.get('student_regno')}")
                
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {line[:100]}...")
            continue
        except OCRError:
            raise
        except Exception as e:
            logger.exception(f"Error processing student data: {e}")
            continue
    
    if not final_list:
        if skipped_subjects:
            raise SubjectNotFoundError(skipped_subjects[0])
        raise NoResultsError()
    
    return final_list

# ============== OCR PROMPTS ==============

OCR_PROMPT = """
**System Role:**
You are a specialized OCR extraction engine designed to process academic result sheets. Your output must be strictly valid machine-readable code.

**Task:**
Extract student registration details and examination results from the provided image.

**Output Format Rules:**
1.  **Format:** Return the data in **JSONL (JSON Lines)** format.
2.  **Structure:** Each line must represent a **single student** and contain all their subject results.
3.  **No Markdown:** Do not use markdown blocks (like ```json). Just return the raw text lines.
4.  **Schema:** Follow this exact JSON structure for every line:
    {"student_regno": "STRING", "student_name": "STRING", "results": [{"subject_code": "STRING", "grade": "STRING"}, {"subject_code": "STRING", "grade": "STRING"}]}

**Extraction Rules:**
1.  **Distinguish Characters:** Be extremely careful with 'O' (letter) versus '0' (zero).
2.  **Index 6 Correction:** If you detect the number '1' at index 6 of any `subject_code`, you must correct it to 'I'.
3.  **Multiple Students:** If the image lists multiple students, generate one JSON line per student.
4.  **Error Handling:** If the text is too blurry, cropped, or illegible to extract data with high confidence, return exactly this JSON object on a single line:
    {"error": "IMAGE_UNCLEAR", "message": "Please upload a clearer image."}
"""

PREV_SEM_OCR_PROMPT = """
**System Role:**
You are a specialized OCR extraction engine designed to process academic marksheets. Your output must be strictly valid machine-readable code.

**Task:**
Extract student registration details, the final cumulative CGPA, and the total credits earned from the bottom of the marksheet.

**Output Format Rules:**
1.  **Format:** Return the data in **JSON** format on a single line.
2.  **No Markdown:** Do not use markdown blocks (like ```json). Just return the raw JSON object.
3.  **Schema:** Follow this exact JSON structure:
    {"student_regno": "STRING", "student_name": "STRING", "cgpa": FLOAT, "total_credits": INTEGER}
4.  **Error Handling:** If the text is too blurry, cropped, or illegible to extract data with high confidence, return exactly this JSON object:
    {"error": "IMAGE_UNCLEAR", "message": "Please upload a clearer image."}
"""

# ============== OCR WITH KEY ROTATION ==============

def do_ocr(image_bytes: bytes, prompt: str) -> str:
    """
    Perform OCR with automatic API key rotation.
    """
    if not GROQ_API_KEYS:
        raise ExternalServiceError("LLM API", "No API keys configured")
    
    last_error = None
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    for i, api_key in enumerate(GROQ_API_KEYS):
        try:
            logger.info(f"Trying API key {i + 1}/{len(GROQ_API_KEYS)}")
            
            client = Groq(api_key=api_key)
            
            response = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1,  
                max_completion_tokens=1024,
            )
            
            extracted_text = response.choices[0].message.content
            
            if not extracted_text:
                raise OCRError("No text was extracted from the image")
            
            logger.info(f"OCR successful with key {i + 1}")
            return extracted_text
            
        except OCRError:
            raise
            
        except Exception as e:
            error_str = str(e).lower()
            
            if any(keyword in error_str for keyword in ['rate', 'limit', 'quota', '429', '503', 'exhausted', 'exceeded']):
                logger.warning(f"API key {i + 1} rate limited/exhausted: {e}")
                last_error = e
                continue
            
            logger.warning(f"API key {i + 1} failed: {e}")
            last_error = e
            continue
    
    logger.error(f"All {len(GROQ_API_KEYS)} API keys exhausted")
    raise AllKeysExhaustedError()

def get_cached_or_run_ocr(image_bytes: bytes, prompt: str, prompt_type: str) -> str:
    img_hash = hashlib.sha256(image_bytes).hexdigest()
    
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT ocr_result FROM image_cache WHERE image_hash = ? AND prompt_type = ?",
            (img_hash, prompt_type)
        )
        row = cursor.fetchone()
        if row:
            logger.info(f"Cache hit for image ({prompt_type}). Skipping API call.")
            return row['ocr_result']
            
    ocr_result = do_ocr(image_bytes, prompt)
    
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO image_cache (image_hash, prompt_type, ocr_result) VALUES (?, ?, ?)",
            (img_hash, prompt_type, ocr_result)
        )
        conn.commit()
        
    return ocr_result

# ============== VALIDATION HELPERS ==============

MAX_FILE_SIZE = 5 * 1024 * 1024  
ALLOWED_TYPES = ["image/jpeg", "image/jpg", "image/png"]

def validate_upload_file(file: UploadFile):
    if not file.content_type:
        raise ValidationError("Could not determine file type")
    
    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError(
            f"Invalid file type: {file.content_type}. Allowed: PNG, JPG, JPEG",
            {"received_type": file.content_type, "allowed_types": ALLOWED_TYPES}
        )

async def validate_file_size(file: UploadFile) -> bytes:
    contents = await file.read()
    
    if len(contents) == 0:
        raise ValidationError("Uploaded file is empty")
    
    if len(contents) > MAX_FILE_SIZE:
        size_mb = len(contents) / (1024 * 1024)
        raise ValidationError(
            f"File too large: {size_mb:.2f}MB. Maximum allowed: 5MB",
            {"file_size_mb": round(size_mb, 2), "max_size_mb": 5}
        )
    
    return contents

# ============== API ENDPOINTS ==============

@app.get("/")
def root():
    return success_response({
        "status": "active",
        "message": "MGR GPA Calculator API",
        "version": "1.1.0"
    })

@app.get("/health")
def health_check():
    return success_response({
        "status": "healthy",
        "grades_loaded": len(grade_points_map),
        "subjects_loaded": len(subject_metadata),
        "api_keys_configured": len(GROQ_API_KEYS)
    })

@app.post("/uploadPreviousSem/")
async def upload_previous_sem(file: UploadFile = File(...)):
    """Uploads a previous semester marksheet to extract and store CGPA and Credits"""
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)
    
    ocr_text = get_cached_or_run_ocr(image_bytes, PREV_SEM_OCR_PROMPT, "prev_sem")
    cleaned_text = clean_llm_json_response(ocr_text)
    
    try:
        data = json.loads(cleaned_text)
        if "error" in data:
            raise OCRError(data.get("message", "Image could not be processed"))
        
        regno = data.get("student_regno")
        name = data.get("student_name", "Unknown")
        
        try:
            cgpa = float(data.get("cgpa", 0))
            credits = int(data.get("total_credits", 0))
        except (ValueError, TypeError):
            raise OCRError("Extracted CGPA or credits are not valid numbers.")
            
        if not regno or cgpa <= 0 or credits <= 0:
            raise OCRError("Could not extract required fields (regno, cgpa, total_credits) from the image.")
            
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO students (regno, name, prev_cgpa, prev_credits)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(regno) DO UPDATE SET
                    name=excluded.name,
                    prev_cgpa=excluded.prev_cgpa,
                    prev_credits=excluded.prev_credits
            ''', (regno, name, cgpa, credits))
            conn.commit()
            
        return success_response({
            "student_regno": regno,
            "student_name": name,
            "prev_cgpa": cgpa,
            "prev_credits": credits,
            "message": "Previous semester data saved successfully."
        })
        
    except json.JSONDecodeError:
        raise OCRError("Failed to parse OCR response for previous semester marksheet.")

@app.post("/calculateGpa/")
async def gpa_calculation(file: UploadFile = File(...)):
    """Calculates the current GPA and the overall New CGPA based on cached previous records."""
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)
    
    ocr_text = get_cached_or_run_ocr(image_bytes, OCR_PROMPT, "current_sem")
    results = calculate_gpa_logic(ocr_text)
    
    with get_db_connection() as conn:
        for student in results:
            regno = student["student_regno"]
            name = student["student_name"]
            current_gpa = student["gpa"]
            current_credits = student["current_credits"]
            results_json = json.dumps(student["results"])
            
            cursor = conn.execute("SELECT prev_cgpa, prev_credits FROM students WHERE regno = ?", (regno,))
            row = cursor.fetchone()
            
            if row and row["prev_credits"] is not None and row["prev_cgpa"] is not None:
                prev_cgpa = float(row["prev_cgpa"])
                prev_credits = int(row["prev_credits"])
                
                # Formula implementation
                new_cgpa = ((prev_credits * prev_cgpa) + (current_credits * current_gpa)) / (prev_credits + current_credits)
                new_cgpa = round(new_cgpa, 2)
                
                student["prev_cgpa"] = prev_cgpa
                student["prev_credits"] = prev_credits
                student["new_cgpa"] = new_cgpa
            else:
                new_cgpa = current_gpa
                student["new_cgpa"] = new_cgpa
                
            conn.execute('''
                INSERT INTO students (regno, name, current_gpa, current_credits, new_cgpa, results_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(regno) DO UPDATE SET
                    name=excluded.name,
                    current_gpa=excluded.current_gpa,
                    current_credits=excluded.current_credits,
                    new_cgpa=excluded.new_cgpa,
                    results_json=excluded.results_json
            ''', (regno, name, current_gpa, current_credits, new_cgpa, results_json))
        conn.commit()
        
    return success_response(results)

@app.get("/student/{regno}")
def get_student(regno: str):
    """Retrieve full student record and GPA calculations by register number."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM students WHERE regno = ?", (regno,))
        row = cursor.fetchone()
        
        if not row:
            raise AppException("STUDENT_NOT_FOUND", f"No data found for register number: {regno}", 404)
            
        data = dict(row)
        if data.get("results_json"):
            data["results"] = json.loads(data["results_json"])
            
        del data["results_json"]
        
        return success_response(data)

@app.get("/debug/metadata")
def debug_metadata():
    return success_response({
        "grade_points_count": len(grade_points_map),
        "subjects_count": len(subject_metadata),
        "sample_grades": dict(list(grade_points_map.items())[:5]),
        "sample_subjects": dict(list(subject_metadata.items())[:5]),
        "api_keys_count": len(GROQ_API_KEYS)
    })