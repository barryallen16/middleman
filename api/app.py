from fastapi import FastAPI, UploadFile, File
import shutil
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

@app.get("/")
def root():
    return {"hello":"world"}

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...)):
    with open(f"saved_{file.filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
        return {"filename": file.filename,
                "saved":f"saved_{file.filename}"}
    
@app.get("/test/")
def returning_test():
    return {'student_regno': '221191101064', 'student_name': 'JAYADITHYA R', 'results': [{'subject_code': 'EBCC22I07', 'subject_name': 'SOFT SKILL II -QUALITATIVE AND QUANTITATIVE SKILLS', 'grade': 'S'}, {'subject_code': 'EBCS22009', 'subject_name': 'OBJECT ORIENTED SOFTWARE ENGINEERING', 'grade': 'A'}, {'subject_code': 'EBCS22010', 'subject_name': 'WEB DESIGN USING PHP & MYSQL', 'grade': 'A'}, {'subject_code': 'EBCS22E11', 'subject_name': 'CRYPTOGRAPHY AND NETWORK SECURITY', 'grade': 'A'}, {'subject_code': 'EBCS22L07', 'subject_name': 'OBJECT ORIENTED SOFTWARE ENGINEERING LAB', 'grade': 'H'}, {'subject_code': 'EBCS22L08', 'subject_name': 'WEB DESIGN USING PHP& MYSQL LAB', 'grade': 'H'}, {'subject_code': 'EBDS22ET6', 'subject_name': 'GENERATIVE AI', 'grade': 'S'}, {'subject_code': 'EBDS22I03', 'subject_name': 'TECHNICAL SKILL III', 'grade': 'H'}, {'subject_code': 'EBDS22I04', 'subject_name': 'MINI PROJECT/INTERNSHIP', 'grade': 'H'}, {'subject_code': 'EBEC22OE2', 'subject_name': 'Cellular Mobile communication', 'grade': 'S'}], 'gpa': 8.75}