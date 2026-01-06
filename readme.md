## Prompts and model used
Model used : `gemini-3-flash-preview`

### prompt used to extract subject name, code and its credits from regulations pdf 

```
Extract the subject name,code and it's credits and return it in a structured jsonl form. 
Like { subject_name:'STRING', subject_code:'STRING', credits:INT}
- Then create a multiple jsonl records as response as specified.
- if the uploaded image is not clear enough to perform the task at hand correctly , return a error json , prompting them to upload a clearer image.
- Be mindful of the difference between 'O' and '0' while extractning.
```

### prompt used to extract subject code and grade from the user uploaded images

```
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
```