# app.py
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel
import base64
import os
import libsql          # NEW: replaces libsql_client (pip install libsql)
import hashlib
from dotenv import load_dotenv
import json
import logging
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

# ============== DATABASE CONFIGURATION (TURSO via new libsql) ==============
#
# The old `libsql_client` package used WebSockets (wss://) which Turso
# deprecated on June 10 2025 when they migrated to AWS.
#
# The new `libsql` package (pip install libsql) implements DB-API 2.0 and
# communicates over HTTP, which is what Turso now requires.
#
# Usage pattern mirrors Python's built-in sqlite3:
#   conn = libsql.connect(database=":memory:", sync_url=URL, auth_token=TOKEN)
#   conn.execute("SELECT ...")        → cursor with .fetchall() / .fetchone()
#   conn.commit()
#   conn.close()
#
# For Turso the `database` argument is ignored for remote-only connections;
# pass ":memory:" as a placeholder.

TURSO_URL        = os.getenv("TURSO_DATABASE_URL")   # e.g. libsql://xxx.turso.io
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def get_db() -> libsql.Connection:
    """
    Open and return a new Turso connection.
    Each call creates a fresh connection — close it when done.
    """
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise ExternalServiceError("Database", "TURSO_DATABASE_URL or TURSO_AUTH_TOKEN missing")
    return libsql.connect(":memory:", sync_url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)


def _fetchall_as_dicts(cursor: libsql.Cursor) -> List[Dict]:
    """Convert cursor rows to a list of dicts using cursor.description."""
    cols = [d[0] for d in cursor.description] if cursor.description else []
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _fetchone_as_dict(cursor: libsql.Cursor) -> Optional[Dict]:
    """Convert a single cursor row to a dict, or None."""
    cols = [d[0] for d in cursor.description] if cursor.description else []
    row  = cursor.fetchone()
    return dict(zip(cols, row)) if row else None


def init_db():
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        logger.warning("Skipping DB init: Turso credentials missing.")
        return

    try:
        conn = get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                regno           TEXT PRIMARY KEY,
                name            TEXT,
                prev_cgpa       REAL,
                prev_credits    INTEGER,
                current_gpa     REAL,
                current_credits INTEGER,
                new_cgpa        REAL,
                results_json    TEXT
            );
            CREATE TABLE IF NOT EXISTS image_cache (
                image_hash  TEXT,
                prompt_type TEXT,
                ocr_result  TEXT,
                PRIMARY KEY (image_hash, prompt_type)
            );
        """)
        conn.commit()
        conn.close()
        logger.info("Turso database initialised successfully.")
    except Exception as e:
        logger.error(f"Failed to initialise Turso database: {e}")

# ============== CUSTOM EXCEPTIONS ==============

class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        self.details     = details or {}
        super().__init__(self.message)

class ValidationError(AppException):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__("VALIDATION_ERROR", message, 400, details)

class SubjectNotFoundError(AppException):
    def __init__(self, subject_code: str):
        super().__init__(
            "SUBJECT_NOT_FOUND",
            f"Subject '{subject_code}' not found in database",
            422, {"subject_code": subject_code}
        )

class GradeNotFoundError(AppException):
    def __init__(self, grade: str):
        super().__init__(
            "GRADE_NOT_FOUND",
            f"Grade '{grade}' is not valid",
            422, {"grade": grade}
        )

class OCRError(AppException):
    def __init__(self, message: str = "Failed to extract text from image"):
        super().__init__("OCR_ERROR", message, 422)

class ExternalServiceError(AppException):
    def __init__(self, service: str, original_error: str = ""):
        super().__init__(
            "EXTERNAL_SERVICE_ERROR",
            f"Failed to communicate with {service}",
            502, {"service": service, "original_error": original_error}
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
            422, {"subject_code": subject_code}
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
            "data":    None,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details}
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data":    None,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": {}}
        }
    )

def success_response(data: Any) -> Dict:
    return {"success": True, "data": data, "error": None}

# ============== DATA STORAGE ==============

grade_points_map: Dict[str, int] = {}
subject_metadata: Dict[str, Dict] = {}

def load_static_data():
    global grade_points_map, subject_metadata
    try:
        base_path  = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(base_path, "./static")

        grade_file   = os.path.join(static_dir, "grade-points.jsonl")
        credits_file = os.path.join(static_dir, "merged_credits.jsonl")

        if not os.path.exists(grade_file):
            logger.error(f"Grade points file not found: {grade_file}"); return
        if not os.path.exists(credits_file):
            logger.error(f"Credits file not found: {credits_file}"); return

        with open(grade_file, 'r', encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                try:
                    d = json.loads(line.strip())
                    if 'letter_grade' in d and 'grade_points' in d:
                        grade_points_map[d['letter_grade']] = d['grade_points']
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSON at line {i} in grade-points.jsonl")

        with open(credits_file, 'r', encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                try:
                    d = json.loads(line.strip())
                    if d.get('credits') is not None:
                        subject_metadata[d['subject_code']] = {
                            'credits': d['credits'],
                            'name':    d.get('subject_name', 'Unknown Subject')
                        }
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSON at line {i} in merged_credits.jsonl")

        logger.info(f"Loaded {len(grade_points_map)} grades and {len(subject_metadata)} subjects")
    except Exception as err:
        logger.exception(f"Error loading static data: {err}")

load_static_data()
init_db()

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
    lines = [l for l in cleaned_text.split("\n") if l.strip()]

    if not lines:
        raise OCRError("No data could be extracted from the image")

    final_list       = []
    skipped_subjects = []

    for line in lines:
        try:
            student_data = json.loads(line)

            if "error" in student_data:
                raise OCRError(student_data.get("message", "Image could not be processed"))

            if "student_regno" not in student_data:
                logger.warning(f"Missing student_regno in: {line[:50]}..."); continue
            if "student_name" not in student_data:
                logger.warning(f"Missing student_name in: {line[:50]}..."); continue
            if not student_data.get("results"):
                logger.warning(f"No results for: {student_data.get('student_regno')}"); continue

            current_dict = {
                "student_regno": student_data["student_regno"],
                "student_name":  student_data["student_name"],
                "results":       []
            }

            acq_credits = total_credits = 0

            for data in student_data["results"]:
                sub_code = data.get('subject_code')
                grade    = data.get('grade')

                if not sub_code:
                    logger.warning("Empty subject code found, skipping..."); continue

                if sub_code not in subject_metadata:
                    logger.warning(f"Subject '{sub_code}' not found in metadata")
                    corrected = sub_code[:-3] + '0' + sub_code[-2:]
                    if 'O' in sub_code[-3:] and corrected in subject_metadata:
                        sub_code = corrected
                    else:
                        skipped_subjects.append(sub_code); continue

                if not grade or grade not in grade_points_map:
                    logger.warning(f"Grade '{grade}' not found for subject '{sub_code}'"); continue

                sub_info = subject_metadata[sub_code]
                credits  = sub_info.get("credits")
                if not credits:
                    logger.warning(f"Invalid credits for subject '{sub_code}'"); continue

                acq_credits   += grade_points_map[grade] * credits
                total_credits += credits
                current_dict["results"].append({
                    "subject_code": sub_code,
                    "subject_name": sub_info.get("name", "Unknown"),
                    "grade":        grade
                })

            current_dict["gpa"]             = round(acq_credits / total_credits, 2) if total_credits else 0.0
            current_dict["current_credits"] = total_credits

            if current_dict["results"]:
                final_list.append(current_dict)
            else:
                logger.warning(f"No valid subjects for: {student_data.get('student_regno')}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {line[:100]}..."); continue
        except OCRError:
            raise
        except Exception as e:
            logger.exception(f"Error processing student data: {e}"); continue

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
    {"student_regno": "STRING", "student_name": "STRING", "results": [{"subject_code": "STRING", "grade": "STRING"}]}

**Extraction Rules:**
1.  **Distinguish Characters:** Be extremely careful with 'O' (letter) versus '0' (zero).
2.  **Index 6 Correction:** If you detect the number '1' at index 6 of any `subject_code`, correct it to 'I'.
3.  **Multiple Students:** If the image lists multiple students, generate one JSON line per student.
4.  **Error Handling:** If the text is too blurry or illegible, return exactly:
    {"error": "IMAGE_UNCLEAR", "message": "Please upload a clearer image."}
"""

PREV_SEM_OCR_PROMPT = """
**System Role:**
You are a specialized OCR extraction engine designed to process academic marksheets. Your output must be strictly valid machine-readable code.

**Task:**
Extract the student's register number, name, final cumulative CGPA, and total credits earned from the marksheet.

**Output Format Rules:**
1.  **Format:** Return a single JSON object on one line.
2.  **No Markdown:** Just return the raw JSON object.
3.  **Schema:** Follow this exact JSON structure:
    {"student_regno": "STRING", "student_name": "STRING", "cgpa": FLOAT, "total_credits": INTEGER}
4.  **Error Handling:** If the image is unclear, return:
    {"error": "IMAGE_UNCLEAR", "message": "Please upload a clearer image."}
"""

# ============== OCR WITH KEY ROTATION ==============

def do_ocr(image_bytes: bytes, prompt: str) -> str:
    if not GROQ_API_KEYS:
        raise ExternalServiceError("LLM API", "No API keys configured")

    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    for i, api_key in enumerate(GROQ_API_KEYS):
        try:
            logger.info(f"Trying API key {i + 1}/{len(GROQ_API_KEYS)}")
            client   = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
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
            err = str(e).lower()
            if any(k in err for k in ['rate', 'limit', 'quota', '429', '503', 'exhausted', 'exceeded']):
                logger.warning(f"API key {i + 1} rate limited: {e}")
            else:
                logger.warning(f"API key {i + 1} failed: {e}")
            continue

    raise AllKeysExhaustedError()


def get_cached_or_run_ocr(image_bytes: bytes, prompt: str, prompt_type: str) -> str:
    img_hash = hashlib.sha256(image_bytes).hexdigest()

    # ── cache read ──────────────────────────────────────────────────────────
    try:
        conn   = get_db()
        cursor = conn.execute(
            "SELECT ocr_result FROM image_cache WHERE image_hash = ? AND prompt_type = ?",
            [img_hash, prompt_type]
        )
        row = _fetchone_as_dict(cursor)
        conn.close()
        if row:
            logger.info(f"Cache hit for image ({prompt_type}). Skipping API call.")
            return row["ocr_result"]
    except ExternalServiceError:
        raise
    except Exception as e:
        logger.warning(f"DB cache read error: {e}")

    # ── actual OCR ──────────────────────────────────────────────────────────
    ocr_result = do_ocr(image_bytes, prompt)

    # ── cache write ─────────────────────────────────────────────────────────
    try:
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO image_cache (image_hash, prompt_type, ocr_result) VALUES (?, ?, ?)",
            [img_hash, prompt_type, ocr_result]
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"DB cache write error: {e}")

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
    return success_response({"status": "active", "message": "MGR GPA Calculator API", "version": "1.2.0"})

@app.get("/health")
def health_check():
    return success_response({
        "status":              "healthy",
        "grades_loaded":       len(grade_points_map),
        "subjects_loaded":     len(subject_metadata),
        "api_keys_configured": len(GROQ_API_KEYS)
    })

# ── Pydantic model for manual insertion ────────────────────────────────────

class ManualPrevData(BaseModel):
    regno:   str
    cgpa:    float
    credits: int

@app.post("/manualPreviousData/")
def manual_previous_data(data: ManualPrevData):
    """Save previous semester data directly without an image."""
    if data.cgpa <= 0 or data.credits <= 0:
        raise ValidationError("CGPA and Credits must be greater than zero.")

    conn = get_db()
    conn.execute(
        """
        INSERT INTO students (regno, prev_cgpa, prev_credits)
        VALUES (?, ?, ?)
        ON CONFLICT(regno) DO UPDATE SET
            prev_cgpa    = excluded.prev_cgpa,
            prev_credits = excluded.prev_credits
        """,
        [data.regno, data.cgpa, data.credits]
    )
    conn.commit()
    conn.close()

    return success_response({
        "student_regno": data.regno,
        "prev_cgpa":     data.cgpa,
        "prev_credits":  data.credits,
        "message":       "Manual data saved successfully."
    })

@app.post("/uploadPreviousSem/")
async def upload_previous_sem(file: UploadFile = File(...)):
    """Upload a previous-semester marksheet to extract and store CGPA and total credits."""
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)

    ocr_text     = get_cached_or_run_ocr(image_bytes, PREV_SEM_OCR_PROMPT, "prev_sem")
    cleaned_text = clean_llm_json_response(ocr_text)

    try:
        data = json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise OCRError("Failed to parse OCR response for previous semester marksheet.")

    if "error" in data:
        raise OCRError(data.get("message", "Image could not be processed"))

    regno = data.get("student_regno")
    name  = data.get("student_name", "Unknown")

    try:
        cgpa    = float(data.get("cgpa",          0))
        credits = int(  data.get("total_credits", 0))
    except (ValueError, TypeError):
        raise OCRError("Extracted CGPA or credits are not valid numbers.")

    if not regno or cgpa <= 0 or credits <= 0:
        raise OCRError("Could not extract required fields (regno, cgpa, total_credits) from the image.")

    conn = get_db()
    conn.execute(
        """
        INSERT INTO students (regno, name, prev_cgpa, prev_credits)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(regno) DO UPDATE SET
            name         = excluded.name,
            prev_cgpa    = excluded.prev_cgpa,
            prev_credits = excluded.prev_credits
        """,
        [regno, name, cgpa, credits]
    )
    conn.commit()
    conn.close()

    return success_response({
        "student_regno": regno,
        "student_name":  name,
        "prev_cgpa":     cgpa,
        "prev_credits":  credits,
        "message":       "Previous semester data saved successfully."
    })

@app.post("/calculateGpa/")
async def gpa_calculation(file: UploadFile = File(...)):
    """Calculate current GPA and, if prior data exists, the new cumulative CGPA."""
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)

    ocr_text = get_cached_or_run_ocr(image_bytes, OCR_PROMPT, "current_sem")
    results  = calculate_gpa_logic(ocr_text)

    try:
        conn = get_db()
        for student in results:
            regno           = student["student_regno"]
            name            = student["student_name"]
            current_gpa     = student["gpa"]
            current_credits = student["current_credits"]
            results_json    = json.dumps(student["results"])

            cursor = conn.execute(
                "SELECT prev_cgpa, prev_credits FROM students WHERE regno = ?", [regno]
            )
            row = _fetchone_as_dict(cursor)

            if row and row.get("prev_credits") and row.get("prev_cgpa"):
                prev_cgpa    = float(row["prev_cgpa"])
                prev_credits = int(  row["prev_credits"])
                new_cgpa     = round(
                    ((prev_credits * prev_cgpa) + (current_credits * current_gpa))
                    / (prev_credits + current_credits),
                    2
                )
                student["prev_cgpa"]    = prev_cgpa
                student["prev_credits"] = prev_credits
                student["new_cgpa"]     = new_cgpa
            else:
                new_cgpa            = current_gpa
                student["new_cgpa"] = new_cgpa

            conn.execute(
                """
                INSERT INTO students (regno, name, current_gpa, current_credits, new_cgpa, results_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(regno) DO UPDATE SET
                    name            = excluded.name,
                    current_gpa     = excluded.current_gpa,
                    current_credits = excluded.current_credits,
                    new_cgpa        = excluded.new_cgpa,
                    results_json    = excluded.results_json
                """,
                [regno, name, current_gpa, current_credits, new_cgpa, results_json]
            )

        conn.commit()
        conn.close()

    except ExternalServiceError:
        pass  # DB down — still return the computed GPA to the caller
    except Exception as e:
        logger.error(f"Error updating DB in calculateGpa: {e}")

    return success_response(results)

@app.get("/student/{regno}")
def get_student(regno: str):
    """Retrieve the full student record and GPA calculations by register number."""
    conn   = get_db()
    cursor = conn.execute("SELECT * FROM students WHERE regno = ?", [regno])
    data   = _fetchone_as_dict(cursor)
    conn.close()

    if not data:
        raise AppException(
            "STUDENT_NOT_FOUND",
            f"No data found for register number: {regno}",
            404
        )

    if data.get("results_json"):
        data["results"] = json.loads(data["results_json"])
    data.pop("results_json", None)

    return success_response(data)