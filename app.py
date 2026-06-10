# app.py
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel
import httpx
import asyncio
import base64
import os
import hashlib
from dotenv import load_dotenv
import json
import logging
from typing import Optional, Dict, Any, List, Union

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# ============== API KEYS ==============

GROQ_API_KEYS_STR = os.getenv('GROQ_API_KEYS', '')
GROQ_API_KEYS = [k.strip() for k in GROQ_API_KEYS_STR.split(',') if k.strip()]

SINGLE_GROQ_KEY = os.getenv('RESULTS_PROJ_APIKEY')
if SINGLE_GROQ_KEY and SINGLE_GROQ_KEY not in GROQ_API_KEYS:
    GROQ_API_KEYS.insert(0, SINGLE_GROQ_KEY)

logger.info(f"Loaded {len(GROQ_API_KEYS)} API keys")

# ============== TURSO HTTP CLIENT ==============
#
# The `libsql` and `libsql-client` packages both create temp files on disk,
# which crashes on Vercel (read-only filesystem, os error 30).
#
# Turso natively supports SQL over HTTP via POST /v2/pipeline — no SDK needed.
# We call it directly with httpx (already a FastAPI/Starlette dependency).
#
# FIX: All Turso calls now use httpx.AsyncClient so they don't block the
# FastAPI event loop. Sync wrappers (turso_execute / turso_batch) are
# replaced with async versions (aturso_execute / aturso_batch).
# init_db() still uses the sync client because it runs at startup, outside
# of any async context.

TURSO_URL        = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN",  "")


def _turso_http_url() -> str:
    """Convert the Turso database URL to an HTTPS pipeline endpoint."""
    url = TURSO_URL.strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    url = url.rstrip("/")
    return url + "/v2/pipeline"


def _typed_arg(value: Any) -> Dict:
    """
    Wrap a Python value into a Turso typed-arg dict.

    Turso HTTP API spec for null:
      CORRECT:   {"type": "null"}            — no "value" key
      INCORRECT: {"type": "null", "value": null}  — JSON null is rejected (HTTP 400)
    All other types must carry "value" as a STRING, never a bare number/bool.
    """
    if value is None:
        return {"type": "null"}                          # FIX: omit "value" key entirely
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float",   "value": str(value)}
    return {"type": "text", "value": str(value)}


def _build_pipeline_payload(statements: List[Dict]) -> Dict:
    """Build the pipeline request body from a list of {sql, args} dicts."""
    requests = []
    for s in statements:
        # Strip leading/trailing whitespace from SQL to avoid parser edge-cases
        sql = s["sql"].strip()
        stmt: Dict[str, Any] = {"sql": sql}
        args = s.get("args")
        if args:                                         # only attach args when non-empty
            stmt["args"] = [_typed_arg(a) for a in args]
        requests.append({"type": "execute", "stmt": stmt})
    requests.append({"type": "close"})
    return {"requests": requests}


def _raise_for_status_with_body(resp: httpx.Response) -> None:
    """
    Like resp.raise_for_status() but logs the response body first so Turso's
    actual error message (e.g. "invalid type for argument") is visible in logs.
    """
    if resp.is_error:
        logger.error(
            "Turso HTTP %s — body: %s",
            resp.status_code,
            resp.text[:500],           # cap at 500 chars to avoid log spam
        )
        resp.raise_for_status()        # still raises httpx.HTTPStatusError


def _extract_results(body: Dict) -> List[Dict]:
    """
    Pull the result dicts out of a pipeline response body.
    Application-level errors inside the JSON (type == "error") are logged;
    we raise a plain RuntimeError here so callers that need ExternalServiceError
    can catch and re-raise — this keeps the function usable before the
    exception classes are defined.
    """
    results = []
    for item in body.get("results", []):
        if item.get("type") == "ok" and item["response"].get("type") == "execute":
            results.append(item["response"]["result"])
        elif item.get("type") == "error":
            msg = item.get("error", {}).get("message", "Unknown DB error")
            logger.error("Turso pipeline error: %s", msg)
            raise RuntimeError(f"Turso: {msg}")         # FIX: don't ref ExternalServiceError here
    return results


# ── Sync versions (startup / non-async contexts only) ──────────────────────

def turso_execute_sync(sql: str, args: Optional[List] = None) -> Dict:
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise RuntimeError("Turso credentials missing")
    payload = _build_pipeline_payload([{"sql": sql, "args": args or []}])
    try:
        resp = httpx.post(
            _turso_http_url(),
            headers={"Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
                     "Content-Type": "application/json"},
            json=payload, timeout=10.0,
        )
        _raise_for_status_with_body(resp)               # FIX: log body before raising
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Turso HTTP error: {e}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Turso request error: {e}") from e
    results = _extract_results(resp.json())
    return results[0] if results else {}


def turso_batch_sync(statements: List[Dict]) -> List[Dict]:
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise RuntimeError("Turso credentials missing")
    payload = _build_pipeline_payload(statements)
    try:
        resp = httpx.post(
            _turso_http_url(),
            headers={"Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
                     "Content-Type": "application/json"},
            json=payload, timeout=15.0,
        )
        _raise_for_status_with_body(resp)               # FIX: log body before raising
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Turso HTTP error: {e}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Turso request error: {e}") from e
    return _extract_results(resp.json())


# ── Async versions (used inside FastAPI route handlers) ────────────────────

async def aturso_execute(sql: str, args: Optional[List] = None) -> Dict:
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise ExternalServiceError("Database", "Turso credentials missing")
    payload = _build_pipeline_payload([{"sql": sql, "args": args or []}])
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _turso_http_url(),
                headers={"Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            _raise_for_status_with_body(resp)           # FIX: log body before raising
    except httpx.HTTPStatusError as e:
        raise ExternalServiceError("Database", str(e)) from e
    except httpx.RequestError as e:
        raise ExternalServiceError("Database", str(e)) from e
    try:
        results = _extract_results(resp.json())
    except RuntimeError as e:
        raise ExternalServiceError("Database", str(e)) from e
    return results[0] if results else {}


async def aturso_batch(statements: List[Dict]) -> List[Dict]:
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        raise ExternalServiceError("Database", "Turso credentials missing")
    payload = _build_pipeline_payload(statements)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _turso_http_url(),
                headers={"Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            _raise_for_status_with_body(resp)           # FIX: log body before raising
    except httpx.HTTPStatusError as e:
        raise ExternalServiceError("Database", str(e)) from e
    except httpx.RequestError as e:
        raise ExternalServiceError("Database", str(e)) from e
    try:
        return _extract_results(resp.json())
    except RuntimeError as e:
        raise ExternalServiceError("Database", str(e)) from e


def _rows_as_dicts(result: Dict) -> List[Dict]:
    """Convert a Turso result dict into a list of Python dicts."""
    cols = [c["name"] for c in result.get("cols", [])]
    return [dict(zip(cols, [cell.get("value") for cell in row]))
            for row in result.get("rows", [])]


def _first_row(result: Dict) -> Optional[Dict]:
    rows = _rows_as_dicts(result)
    return rows[0] if rows else None


def init_db():
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        logger.warning("Skipping DB init: Turso credentials missing.")
        return
    try:
        turso_batch_sync([
            {"sql": """
                CREATE TABLE IF NOT EXISTS students (
                    regno           TEXT PRIMARY KEY,
                    name            TEXT,
                    prev_cgpa       REAL,
                    prev_credits    INTEGER,
                    current_gpa     REAL,
                    current_credits INTEGER,
                    new_cgpa        REAL,
                    results_json    TEXT
                )
            """},
            {"sql": """
                CREATE TABLE IF NOT EXISTS image_cache (
                    image_hash  TEXT,
                    prompt_type TEXT,
                    ocr_result  TEXT,
                    PRIMARY KEY (image_hash, prompt_type)
                )
            """},
        ])
        logger.info("Turso DB initialised via HTTP pipeline.")
    except Exception as e:
        logger.error(f"Failed to initialise Turso database: {e}")

# ============== FASTAPI APP ==============

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False
)

# ============== CUSTOM EXCEPTIONS ==============

class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500,
                 details: Optional[Dict[str, Any]] = None):
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
        super().__init__("SUBJECT_NOT_FOUND",
                         f"Subject '{subject_code}' not found in database",
                         422, {"subject_code": subject_code})

class OCRError(AppException):
    def __init__(self, message: str = "Failed to extract text from image"):
        super().__init__("OCR_ERROR", message, 422)

class ExternalServiceError(AppException):
    def __init__(self, service: str, original_error: str = ""):
        super().__init__("EXTERNAL_SERVICE_ERROR",
                         f"Failed to communicate with {service}",
                         502, {"service": service, "original_error": original_error})

class AllKeysExhaustedError(AppException):
    def __init__(self):
        super().__init__("ALL_KEYS_EXHAUSTED",
                         "All API keys have been exhausted. Please try again later.", 503)

class NoResultsError(AppException):
    def __init__(self):
        super().__init__("NO_RESULTS",
                         "No valid results could be extracted from the image", 422)

# ============== EXCEPTION HANDLERS ==============

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error(f"AppException: {exc.code} - {exc.message}")
    return JSONResponse(status_code=exc.status_code, content={
        "success": False, "data": None,
        "error": {"code": exc.code, "message": exc.message, "details": exc.details}
    })

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(status_code=500, content={
        "success": False, "data": None,
        "error": {"code": "INTERNAL_ERROR",
                  "message": "An unexpected error occurred.", "details": {}}
    })

def success_response(data: Any) -> Dict:
    return {"success": True, "data": data, "error": None}

# ============== STATIC DATA ==============

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
                    logger.warning(f"Bad JSON at line {i} in grade-points.jsonl")

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
                    logger.warning(f"Bad JSON at line {i} in merged_credits.jsonl")

        logger.info(f"Loaded {len(grade_points_map)} grades and {len(subject_metadata)} subjects")
    except Exception as e:
        logger.exception(f"Error loading static data: {e}")

load_static_data()
init_db()

# ============== HELPERS ==============

def clean_llm_json_response(text: str) -> str:
    """
    Strip markdown code fences that some models wrap around their output.
    Handles both triple-backtick blocks (```json ... ``` or ``` ... ```)
    and single-backtick wrapping on individual lines.
    """
    text = text.strip()
    # Remove outer triple-backtick block if present
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # FIX: also clean per-line inline backtick fences that some models emit
    # e.g. "```json\n{...}\n```" split across lines after the outer strip above
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            continue  # skip fence-only lines
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def calculate_gpa_logic(jsonl_string: str) -> List[Dict]:
    lines = [l for l in clean_llm_json_response(jsonl_string).split("\n") if l.strip()]
    if not lines:
        raise OCRError("No data could be extracted from the image")

    final_list       = []
    skipped_subjects = []

    for line in lines:
        try:
            student_data = json.loads(line)

            if "error" in student_data:
                raise OCRError(student_data.get("message", "Image could not be processed"))

            if not student_data.get("student_regno"):
                logger.warning(f"Missing student_regno: {line[:50]}..."); continue
            if not student_data.get("student_name"):
                logger.warning(f"Missing student_name: {line[:50]}..."); continue
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
                    continue

                if sub_code not in subject_metadata:
                    # FIX: the OCR prompt says index 6 (0-based) may contain '1'
                    # that should be 'I'. The original code replaced the wrong
                    # character and used the wrong condition.  Correct fix:
                    # check position 6 for digit '1' and replace with letter 'I'.
                    corrected = sub_code
                    if len(sub_code) > 6 and sub_code[6] == '1':
                        corrected = sub_code[:6] + 'I' + sub_code[7:]
                    if corrected != sub_code and corrected in subject_metadata:
                        sub_code = corrected
                        logger.info(f"Corrected subject code: {data.get('subject_code')} -> {sub_code}")
                    else:
                        skipped_subjects.append(sub_code)
                        continue

                if not grade or grade not in grade_points_map:
                    continue

                sub_info = subject_metadata[sub_code]
                credits  = sub_info.get("credits")
                if not credits:
                    continue

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

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {line[:100]}..."); continue
        except OCRError:
            raise
        except Exception as e:
            logger.exception(f"Error processing student: {e}"); continue

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

# FIX: do_ocr runs blocking Groq SDK calls in a thread pool so it doesn't
# stall the async event loop.
def _do_ocr_sync(image_bytes: bytes, prompt: str) -> str:
    """Blocking OCR — run via asyncio.to_thread from async callers."""
    if not GROQ_API_KEYS:
        raise ExternalServiceError("LLM API", "No API keys configured")

    b64 = base64.b64encode(image_bytes).decode('utf-8')

    for i, api_key in enumerate(GROQ_API_KEYS):
        try:
            logger.info(f"Trying API key {i + 1}/{len(GROQ_API_KEYS)}")
            response = Groq(api_key=api_key).chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": [
                    {"type": "text",      "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}],
                temperature=0.1,
                max_completion_tokens=1024,
            )
            text = response.choices[0].message.content
            if not text:
                raise OCRError("No text was extracted from the image")
            logger.info(f"OCR successful with key {i + 1}")
            return text
        except OCRError:
            raise
        except Exception as e:
            err = str(e).lower()
            lvl = "rate limited" if any(k in err for k in ['rate', 'limit', 'quota', '429', '503']) else "failed"
            logger.warning(f"API key {i + 1} {lvl}: {e}")
            continue

    raise AllKeysExhaustedError()


async def do_ocr(image_bytes: bytes, prompt: str) -> str:
    return await asyncio.to_thread(_do_ocr_sync, image_bytes, prompt)


async def get_cached_or_run_ocr(image_bytes: bytes, prompt: str, prompt_type: str) -> str:
    img_hash = hashlib.sha256(image_bytes).hexdigest()

    # ── cache read ──────────────────────────────────────────────────────────
    try:
        result = await aturso_execute(
            "SELECT ocr_result FROM image_cache WHERE image_hash = ? AND prompt_type = ?",
            [img_hash, prompt_type]
        )
        row = _first_row(result)
        if row:
            logger.info(f"Cache hit ({prompt_type}). Skipping API call.")
            return row["ocr_result"]
    except ExternalServiceError:
        raise
    except Exception as e:
        logger.warning(f"Cache read error: {e}")

    # ── OCR ─────────────────────────────────────────────────────────────────
    ocr_result = await do_ocr(image_bytes, prompt)

    # ── cache write ─────────────────────────────────────────────────────────
    try:
        await aturso_execute(
            "INSERT OR REPLACE INTO image_cache (image_hash, prompt_type, ocr_result) VALUES (?, ?, ?)",
            [img_hash, prompt_type, ocr_result]
        )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")

    return ocr_result

# ============== VALIDATION ==============

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
    if not contents:
        raise ValidationError("Uploaded file is empty")
    if len(contents) > MAX_FILE_SIZE:
        mb = len(contents) / (1024 * 1024)
        raise ValidationError(f"File too large: {mb:.2f}MB. Maximum: 5MB",
                               {"file_size_mb": round(mb, 2), "max_size_mb": 5})
    return contents

# ============== ENDPOINTS ==============

@app.get("/")
def root():
    return success_response({"status": "active", "message": "MGR GPA Calculator API", "version": "1.3.1"})

@app.get("/health")
def health_check():
    return success_response({
        "status":              "healthy",
        "grades_loaded":       len(grade_points_map),
        "subjects_loaded":     len(subject_metadata),
        "api_keys_configured": len(GROQ_API_KEYS)
    })


class ManualPrevData(BaseModel):
    regno:   str
    cgpa:    float
    credits: int

@app.post("/manualPreviousData/")
async def manual_previous_data(data: ManualPrevData):
    """Save previous semester data directly without uploading an image."""
    if data.cgpa <= 0 or data.credits <= 0:
        raise ValidationError("CGPA and Credits must be greater than zero.")

    await aturso_execute(
        """
        INSERT INTO students (regno, prev_cgpa, prev_credits)
        VALUES (?, ?, ?)
        ON CONFLICT(regno) DO UPDATE SET
            prev_cgpa    = excluded.prev_cgpa,
            prev_credits = excluded.prev_credits
        """,
        [data.regno, data.cgpa, data.credits]
    )
    return success_response({
        "student_regno": data.regno,
        "prev_cgpa":     data.cgpa,
        "prev_credits":  data.credits,
        "message":       "Manual data saved successfully."
    })


@app.post("/uploadPreviousSem/")
async def upload_previous_sem(file: UploadFile = File(...)):
    """Upload a previous-semester marksheet to extract and persist CGPA + credits."""
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)

    ocr_text = await get_cached_or_run_ocr(image_bytes, PREV_SEM_OCR_PROMPT, "prev_sem")

    try:
        data = json.loads(clean_llm_json_response(ocr_text))
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

    await aturso_execute(
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
    return success_response({
        "student_regno": regno,
        "student_name":  name,
        "prev_cgpa":     cgpa,
        "prev_credits":  credits,
        "message":       "Previous semester data saved successfully."
    })


@app.post("/calculateGpa/")
async def gpa_calculation(file: UploadFile = File(...)):
    """
    Calculate current-semester GPA.
    If previous-semester data exists for a student, also computes their new CGPA:
        new_cgpa = (prev_credits × prev_cgpa + current_credits × current_gpa)
                   ────────────────────────────────────────────────────────
                               prev_credits + current_credits
    """
    validate_upload_file(file)
    image_bytes = await validate_file_size(file)

    ocr_text = await get_cached_or_run_ocr(image_bytes, OCR_PROMPT, "current_sem")
    results  = calculate_gpa_logic(ocr_text)

    # FIX: prev_map is always initialised so the DB-save block below never
    # hits a NameError even if the fetch fails.
    prev_map: Dict[str, Any] = {}

    try:
        regnos       = [s["student_regno"] for s in results]
        placeholders = ", ".join("?" * len(regnos))
        prev_result  = await aturso_execute(
            f"SELECT regno, prev_cgpa, prev_credits FROM students WHERE regno IN ({placeholders})",
            regnos
        )
        prev_map = {row["regno"]: row for row in _rows_as_dicts(prev_result)}
    except ExternalServiceError:
        # DB is down — still compute GPA, just skip CGPA calculation
        logger.warning("DB unavailable; skipping prev-data lookup.")
    except Exception as e:
        logger.error(f"DB fetch error in calculateGpa: {e}")

    db_statements = []
    for student in results:
        regno           = student["student_regno"]
        current_gpa     = student["gpa"]
        current_credits = student["current_credits"]

        row = prev_map.get(regno)
        if row and row.get("prev_credits") and row.get("prev_cgpa"):
            prev_cgpa    = float(row["prev_cgpa"])
            prev_credits = int(  row["prev_credits"])
            new_cgpa     = round(
                (prev_credits * prev_cgpa + current_credits * current_gpa)
                / (prev_credits + current_credits), 2
            )
            student["prev_cgpa"]    = prev_cgpa
            student["prev_credits"] = prev_credits
            student["new_cgpa"]     = new_cgpa
        else:
            new_cgpa            = current_gpa
            student["new_cgpa"] = new_cgpa

        db_statements.append({
            "sql": """
                INSERT INTO students (regno, name, current_gpa, current_credits, new_cgpa, results_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(regno) DO UPDATE SET
                    name            = excluded.name,
                    current_gpa     = excluded.current_gpa,
                    current_credits = excluded.current_credits,
                    new_cgpa        = excluded.new_cgpa,
                    results_json    = excluded.results_json
            """,
            "args": [
                regno,
                student["student_name"],
                current_gpa,
                current_credits,
                new_cgpa,
                json.dumps(student["results"]),
            ]
        })

    if db_statements:
        try:
            await aturso_batch(db_statements)
        except ExternalServiceError:
            pass  # DB down — GPA results were already computed, return them anyway
        except Exception as e:
            logger.error(f"DB write error in calculateGpa: {e}")

    return success_response(results)


@app.get("/student/{regno}")
async def get_student(regno: str):
    """Retrieve a student's full record by register number."""
    result = await aturso_execute(
        "SELECT * FROM students WHERE regno = ?", [regno]
    )
    data = _first_row(result)

    if not data:
        raise AppException("STUDENT_NOT_FOUND",
                           f"No data found for register number: {regno}", 404)

    if data.get("results_json"):
        try:
            data["results"] = json.loads(data["results_json"])
        except json.JSONDecodeError:
            data["results"] = []
    else:
        data["results"] = []
    data.pop("results_json", None)

    return success_response(data)