from fastapi import FastAPI, UploadFile, File, HTTPException
import shutil
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import os 
from dotenv import load_dotenv
import pandas as pd 
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# files used 
# 1.grade-points.jsonl
# 2. merged_credits.jsonl


load_dotenv()
GEMINI_API_KEY=os.getenv('RESULTS_PROJ_APIKEY')

client=genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

grade_points_map = {}
subject_metadata = {}

def load_static_data():
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.jsoin(base_path, "../static")
        with open(os.path.join(static_dir, "grade-points.jsonl"), 'r', encoding="utf-8") as in_file:
            for line in in_file:
                data=json.loads(line)
                grade_points_map[data['letter_grade']]=data['grade_points']
        with open(os.path.join(static_dir,"merged_credits.jsonl"), 'r', encoding="utf-8") as in_file:
            for line in in_file:
                data=json.loads(line)
                subject_metadata[data['subject_code']] = {'credits':data['credits'], 'name': data['subject_name']}
        logger.info("static data loaded successfully")
    except Exception as err:
        logger.error("error while loading static data: ", err)
    
load_static_data()

def clean_llm_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text= text[:-3]        
    return text.strip()

def calculate_gpa_logic(jsonl_string:str):
    cleaned_text=clean_llm_json_response(jsonl_string)
    lines = [line for line in cleaned_text.split("\n") if line.strip()]

    final_list=[]

    for line in lines:
            try:     
                line = json.loads(line)
                current_dict={}
                acq_credits=0
                total_credits=0
                all_data= line
                results_data = all_data["results"]
                current_dict["student_regno"] = line["student_regno"]
                current_dict["student_name"] = line["student_name"]
                current_dict["results"] = []
                for data in results_data:     
                        results_dict={}
                        results_dict["subject_code"] = data['subject_code']
                        result= df.loc[df['subject_code'] == data['subject_code'], 'subject_name']
                        results_dict["subject_name"] = result.values[0]
                        results_dict["grade"] = data['grade']
                        acq_credits+=grade_points[data['grade']] * credits[data['subject_code']]
                        total_credits+=credits[data['subject_code']]
                        current_dict["results"].append(results_dict)
            except KeyError as err:
                print('error:', err)
            gpa = acq_credits / total_credits
            gpa = round(gpa, 2)
            current_dict["gpa"]= gpa
            final_list.append(current_dict)
    # print(current_dict)
    return final_list

def doOCr(image_bytes : bytes):

    prompt ="""
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
    try:
            
        response = client.models.generate_content(model="gemini-2.5-flash", 
                                                contents=[
                                                    types.Part.from_bytes(data=image_bytes,
                                                                            mime_type="image/jpeg")
                                                                            ,prompt])
        return response.text
    except Exception as e:
        logger.error(f"Gemini API error : {e}")
        raise HTTPException(status_code=500, detail= "Error communicating with Gemini API service")

@app.get("/")
def root():
    return {"status":"active", "message": "MGR GPA calculator API"}

@app.get("/test/")
def returning_test():
    return {'student_regno': '221191101064', 'student_name': 'JAYADITHYA R', 'results': [{'subject_code': 'EBCC22I07', 'subject_name': 'SOFT SKILL II -QUALITATIVE AND QUANTITATIVE SKILLS', 'grade': 'S'}, {'subject_code': 'EBCS22009', 'subject_name': 'OBJECT ORIENTED SOFTWARE ENGINEERING', 'grade': 'A'}, {'subject_code': 'EBCS22010', 'subject_name': 'WEB DESIGN USING PHP & MYSQL', 'grade': 'A'}, {'subject_code': 'EBCS22E11', 'subject_name': 'CRYPTOGRAPHY AND NETWORK SECURITY', 'grade': 'A'}, {'subject_code': 'EBCS22L07', 'subject_name': 'OBJECT ORIENTED SOFTWARE ENGINEERING LAB', 'grade': 'H'}, {'subject_code': 'EBCS22L08', 'subject_name': 'WEB DESIGN USING PHP& MYSQL LAB', 'grade': 'H'}, {'subject_code': 'EBDS22ET6', 'subject_name': 'GENERATIVE AI', 'grade': 'S'}, {'subject_code': 'EBDS22I03', 'subject_name': 'TECHNICAL SKILL III', 'grade': 'H'}, {'subject_code': 'EBDS22I04', 'subject_name': 'MINI PROJECT/INTERNSHIP', 'grade': 'H'}, {'subject_code': 'EBEC22OE2', 'subject_name': 'Cellular Mobile communication', 'grade': 'S'}], 'gpa': 8.75}

@app.post("/calculateGpa/")
async def gpa_calculation(file: UploadFile = File(...)):
    saved_filename=f"saved_{file.filename}"
    with open(saved_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return calculateGpa(doOCr(saved_filename))

    
@app.get("/return/")
def return_jsonlist():
    string_ ="""{"student_regno": "221191101013", "student_name": "ALHAMEEM S", "results": [{"subject_code": "EBCC22I07", "grade": "B"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "B"}, {"subject_code": "EBDS22I04", "grade": "B"}, {"subject_code": "EBEE22OE6", "grade": "A"}, {"subject_code": "EBCS22006", "grade": "B"}, {"subject_code": "EBCS22007", "grade": "C"}]}
{"student_regno": "221191101047", "student_name": "ESHAA", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "C"}, {"subject_code": "EBCS22010", "grade": "C"}, {"subject_code": "EBCS22E11", "grade": "F"}, {"subject_code": "EBCS22L07", "grade": "S"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "B"}, {"subject_code": "EBDS22I03", "grade": "A"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBEE22OE8", "grade": "B"}, {"subject_code": "EBBT22OE1", "grade": "A"}]}
{"student_regno": "221191101064", "student_name": "JAYADITHYA R", "results": [{"subject_code": "EBCC22I07", "grade": "S"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "A"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "H"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "H"}, {"subject_code": "EBDS22I04", "grade": "H"}, {"subject_code": "EBEC22OE2", "grade": "S"}]}
{"student_regno": "221191101088", "student_name": "MD TAQIYY FAIZ M", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "B"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "S"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "S"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBME22OE7", "grade": "S"}, {"subject_code": "EBCS22006", "grade": "B"}, {"subject_code": "EBCT22OE5", "grade": "A"}]}
{"student_regno": "221191101129", "student_name": "SASI KUMAR M", "results": [{"subject_code": "EBCC22I07", "grade": "A"}, {"subject_code": "EBCS22009", "grade": "A"}, {"subject_code": "EBCS22010", "grade": "A"}, {"subject_code": "EBCS22E11", "grade": "B"}, {"subject_code": "EBCS22L07", "grade": "H"}, {"subject_code": "EBCS22L08", "grade": "H"}, {"subject_code": "EBDS22ET6", "grade": "S"}, {"subject_code": "EBDS22I03", "grade": "H"}, {"subject_code": "EBDS22I04", "grade": "S"}, {"subject_code": "EBEE22OE6", "grade": "S"}]}"""
    return calculateGpa(string_)