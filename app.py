# app.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import os 
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

# Load multiple Gemini API keys from environment (comma-separated)
# Format in .env: GEMINI_API_KEYS=key1,key2,key3
GEMINI_API_KEYS_STR = os.getenv('GEMINI_API_KEYS', '')
GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',') if key.strip()]

# Fallback: Also check for single key (backward compatibility)
SINGLE_GEMINI_KEY = os.getenv('RESULTS_PROJ_APIKEY')
if SINGLE_GEMINI_KEY and SINGLE_GEMINI_KEY not in GEMINI_API_KEYS:
    GEMINI_API_KEYS.insert(0, SINGLE_GEMINI_KEY)

logger.info(f"Loaded {len(GEMINI_API_KEYS)} Gemini API keys")

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

# ============== RESPONSE HELPERS ==============

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

# ============== OCR PROMPT ==============

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
2.  **Index 6 Correction:**  If you detect the number '1' at index 6 of any `subject_code, you must correct it to 'I'.
3.  **Multiple Students:** If the image lists multiple students, generate one JSON line per student.
4.  **Error Handling:** If the text is too blurry, cropped, or illegible to extract data with high confidence, return exactly this JSON object on a single line:
    {"error": "IMAGE_UNCLEAR", "message": "Please upload a clearer image."}
"""

# ============== GEMINI OCR WITH KEY ROTATION ==============

def do_ocr(image_bytes: bytes) -> str:
    """
    Perform OCR using Gemini API with automatic key rotation.
    If one key fails (rate limit, quota exceeded), try the next one.
    """
    if not GEMINI_API_KEYS:
        raise ExternalServiceError("Gemini AI", "No API keys configured")
    
    last_error = None
    
    for i, api_key in enumerate(GEMINI_API_KEYS):
        try:
            logger.info(f"Trying Gemini API key {i + 1}/{len(GEMINI_API_KEYS)}")
            
            # Create client with current key
            client = genai.Client(api_key=api_key)
            
            # Make the API call
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    OCR_PROMPT
                ]
            )
            
            if not response.text:
                raise OCRError("No text was extracted from the image")
            
            logger.info(f"Gemini OCR successful with key {i + 1}")
            logger.info(f"OCR Response: {response.text[:200]}...")
            return response.text
            
        except OCRError:
            # OCR errors (like unclear image) should not trigger key rotation
            raise
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if it's a rate limit or quota error (should try next key)
            if any(keyword in error_str for keyword in ['rate', 'limit', 'quota', '429', '503', 'exhausted', 'exceeded']):
                logger.warning(f"Gemini API key {i + 1} rate limited/exhausted: {e}")
                last_error = e
                continue
            
            # For other errors, also try next key
            logger.warning(f"Gemini API key {i + 1} failed: {e}")
            last_error = e
            continue
    
    # All keys exhausted
    logger.error(f"All {len(GEMINI_API_KEYS)} Gemini API keys exhausted")
    raise AllKeysExhaustedError()

# ============== VALIDATION HELPERS ==============

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_TYPES = ["image/jpeg", "image/jpg", "image/png"]

def validate_upload_file(file: UploadFile):
    """Validate the uploaded file"""
    if not file.content_type:
        raise ValidationError("Could not determine file type")
    
    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError(
            f"Invalid file type: {file.content_type}. Allowed: PNG, JPG, JPEG",
            {"received_type": file.content_type, "allowed_types": ALLOWED_TYPES}
        )

async def validate_file_size(file: UploadFile) -> bytes:
    """Read and validate file size"""
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
        "version": "1.0.0"
    })

@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return success_response({
        "status": "healthy",
        "grades_loaded": len(grade_points_map),
        "subjects_loaded": len(subject_metadata),
        "api_keys_configured": len(GEMINI_API_KEYS)
    })

@app.post("/calculateGpa/")
async def gpa_calculation(file: UploadFile = File(...)):
    # Step 1: Validate file type
    validate_upload_file(file)
    
    # Step 2: Read and validate file size
    image_bytes = await validate_file_size(file)
    
    # Step 3: Perform OCR (with automatic key rotation)
    ocr_text = do_ocr(image_bytes)
    
    # Step 4: Calculate GPA
    results = calculate_gpa_logic(ocr_text)
    
    # Step 5: Return success response
    return success_response(results)

@app.get("/return/")
def return_jsonlist():
    """Test endpoint with sample data"""
    string_ = """{"student_regno": "REGNO-A", "student_name": "STUDENT-A", "results": [{"subject_code": "EBCC22I07", "grade": "B"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "B"}, {"subject_code": "EBDS22I04", "grade": "B"}, {"subject_code": "EBEE22OE6", "grade": "A"}, {"subject_code": "EBCS22006", "grade": "B"}, {"subject_code": "EBCS22007", "grade": "C"}]}
{"student_regno": "REGNO-B", "student_name": "STUDENT-B", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "A"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBEE22OE8", "grade": "B"}, {"subject_code": "EBBT22OE1", "grade": "A"}]}"""
    
    results = calculate_gpa_logic(string_)
    return success_response(results)

@app.get("/debug/metadata")
def debug_metadata():
    """Debug endpoint - remove in production"""
    return success_response({
        "grade_points_count": len(grade_points_map),
        "subjects_count": len(subject_metadata),
        "sample_grades": dict(list(grade_points_map.items())[:5]),
        "sample_subjects": dict(list(subject_metadata.items())[:5]),
        "api_keys_count": len(GEMINI_API_KEYS)
    })