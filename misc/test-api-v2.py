from google import genai
from google.genai import types
import os 
from dotenv import load_dotenv
import json
from pydantic import BaseModel, Field
from typing import List

class results_format(BaseModel):
    subject_code : str = Field(description="Subject code")
    grade:str =Field(description="acquired grade")

class extraction(BaseModel):
    subject_regno:str= Field("register number of the student")
    subject_name: str = Field("name of the student")
    result: List[results_format]

load_dotenv()
GEMINI_API_KEY=os.getenv('RESULTS_PROJ_APIKEY')

with open('./test-results.jpeg', 'rb') as file:
    image_bytes= file.read()

client=genai.Client(api_key=GEMINI_API_KEY)
response = client.models.generate_content(model="gemini-3-flash-preview", 
                                          contents=[
                                              types.Part.from_bytes(data=image_bytes,
                                                                    mime_type="image/jpeg")
                                                                    ,
"""
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
],
config={
    "response_mime_type":"application/json",
    "response_json_schema": extraction.model_json_schema()
}
)
print(response.text)

print('-'*50)
verify_ = extraction.model_validate_json(response.text)
print(verify_)
