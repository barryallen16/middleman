from google import genai
from google.genai import types
import os 
from dotenv import load_dotenv
import json
from fastapi import FastAPI, UploadFile, File
import shutil

load_dotenv()
GEMINI_API_KEY=os.getenv('RESULTS_PROJ_APIKEY')

app = FastAPI()

@app.get("/")
def root():
    return {"hello":"world"}

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...)):
    with open(f"saved_{file.filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    with open(f'saved_{file.filename}', 'rb') as file:
        image_bytes= file.read()

    client=genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model="gemini-2.5-flash", 
                                            contents=[
                                                types.Part.from_bytes(data=image_bytes,
                                                                        mime_type="image/jpeg")
                                                                        ,
    """Extract the subject code and it's grade and return it in a structured jsonl form. 
    Like 
    {
    student_regno: '' ,
    student_name: '',
    results: {
    subject_code:''
    grade:''}
    }
    If there is multiple students results visible. Then create a multiple jsonl records as response as specified.
    if the uploaded image is not clear enough to perform the task at hand correctly , return a error json , prompting them to upload a clearer image.
    """])
    print(response.text)
    lines = response.text.split("\n")
    if lines[0]=="```jsonl" and lines[-1] == "```":
        lines.remove(lines[0])
        lines.remove(lines[-1])
        new_result= [json.loads(line) for line in lines]
        print(new_result)
        return {
            "new_response":new_result
        }
    else:
        return{
            "response" : "error processing the image, retry again."
        }

@app.get("/test")
def test_return_jsonl():
    test_dict={
        "gemini-response": "```jsonl\n{\"student_regno\": \"221191101013\", \"student_name\": \"ALHAMEEM S\", \"results\": [{\"subject_code\": \"EBCC22107\", \"grade\": \"B\"}, {\"subject_code\": \"EBCS22009\", \"grade\": \"C\"}, {\"subject_code\": \"EBCS22010\", \"grade\": \"C\"}, {\"subject_code\": \"EBCS22E11\", \"grade\": \"F\"}, {\"subject_code\": \"EBCS22L07\", \"grade\": \"S\"}, {\"subject_code\": \"EBCS22L08\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22ET6\", \"grade\": \"B\"}, {\"subject_code\": \"EBDS22103\", \"grade\": \"B\"}, {\"subject_code\": \"EBDS22104\", \"grade\": \"B\"}, {\"subject_code\": \"EBEE22OE6\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22006\", \"grade\": \"B\"}, {\"subject_code\": \"EBCS22007\", \"grade\": \"C\"}]}\n{\"student_regno\": \"221191101047\", \"student_name\": \"ESHAA\", \"results\": [{\"subject_code\": \"EBCC22107\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22009\", \"grade\": \"C\"}, {\"subject_code\": \"EBCS22010\", \"grade\": \"C\"}, {\"subject_code\": \"EBCS22E11\", \"grade\": \"F\"}, {\"subject_code\": \"EBCS22L07\", \"grade\": \"S\"}, {\"subject_code\": \"EBCS22L08\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22ET6\", \"grade\": \"B\"}, {\"subject_code\": \"EBDS22103\", \"grade\": \"A\"}, {\"subject_code\": \"EBDS22104\", \"grade\": \"S\"}, {\"subject_code\": \"EBEE22OE8\", \"grade\": \"B\"}, {\"subject_code\": \"EBBT22OE1\", \"grade\": \"A\"}]}\n{\"student_regno\": \"221191101064\", \"student_name\": \"JAYADITHYA R\", \"results\": [{\"subject_code\": \"EBCC22107\", \"grade\": \"S\"}, {\"subject_code\": \"EBCS22009\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22010\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22E11\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22L07\", \"grade\": \"H\"}, {\"subject_code\": \"EBCS22L08\", \"grade\": \"H\"}, {\"subject_code\": \"EBDS22ET6\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22103\", \"grade\": \"H\"}, {\"subject_code\": \"EBDS22104\", \"grade\": \"H\"}, {\"subject_code\": \"EBEC22OE2\", \"grade\": \"S\"}]}\n{\"student_regno\": \"221191101088\", \"student_name\": \"MD TAQIYY FAIZ M\", \"results\": [{\"subject_code\": \"EBCC22107\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22009\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22010\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22E11\", \"grade\": \"B\"}, {\"subject_code\": \"EBCS22L07\", \"grade\": \"H\"}, {\"subject_code\": \"EBCS22L08\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22ET6\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22103\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22104\", \"grade\": \"S\"}, {\"subject_code\": \"EBME22OE7\", \"grade\": \"S\"}, {\"subject_code\": \"EBCS22006\", \"grade\": \"B\"}, {\"subject_code\": \"EBCT22OE5\", \"grade\": \"A\"}]}\n{\"student_regno\": \"221191101129\", \"student_name\": \"SASI KUMAR M\", \"results\": [{\"subject_code\": \"EBCC22107\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22009\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22010\", \"grade\": \"A\"}, {\"subject_code\": \"EBCS22E11\", \"grade\": \"B\"}, {\"subject_code\": \"EBCS22L07\", \"grade\": \"H\"}, {\"subject_code\": \"EBCS22L08\", \"grade\": \"H\"}, {\"subject_code\": \"EBDS22ET6\", \"grade\": \"S\"}, {\"subject_code\": \"EBDS22103\", \"grade\": \"H\"}, {\"subject_code\": \"EBDS22104\", \"grade\": \"S\"}, {\"subject_code\": \"EBEE22OE6\", \"grade\": \"S\"}]}\n```"
    }
    lines=test_dict["gemini-response"].split("\n")
    if lines[0]=="```jsonl" and lines[-1] == "```":
        lines.remove(lines[0])
        lines.remove(lines[-1])
        new_result= [json.loads(line) for line in lines]
        print(new_result)
        return {
            "new_response":new_result
        }
    else:
        return{
            "response" : "error processing the image, retry again."
        }

@app.get("/system")
def test_cal():
    test_dict = [
        {
            "student_regno": "221191101013",
            "student_name": "ALHAMEEM S",
            "results": [
                {
                    "subject_code": "EBCC22107",
                    "grade": "B"
                },
                {
                    "subject_code": "EBCS22009",
                    "grade": "C"
                },
                {
                    "subject_code": "EBCS22010",
                    "grade": "C"
                },
                {
                    "subject_code": "EBCS22E11",
                    "grade": "F"
                },
                {
                    "subject_code": "EBCS22L07",
                    "grade": "S"
                },
                {
                    "subject_code": "EBCS22L08",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22ET6",
                    "grade": "B"
                },
                {
                    "subject_code": "EBDS22103",
                    "grade": "B"
                },
                {
                    "subject_code": "EBDS22104",
                    "grade": "B"
                },
                {
                    "subject_code": "EBEE22OE6",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22006",
                    "grade": "B"
                },
                {
                    "subject_code": "EBCS22007",
                    "grade": "C"
                }
            ]
        },
        {
            "student_regno": "221191101047",
            "student_name": "ESHAA",
            "results": [
                {
                    "subject_code": "EBCC22107",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22009",
                    "grade": "C"
                },
                {
                    "subject_code": "EBCS22010",
                    "grade": "C"
                },
                {
                    "subject_code": "EBCS22E11",
                    "grade": "F"
                },
                {
                    "subject_code": "EBCS22L07",
                    "grade": "S"
                },
                {
                    "subject_code": "EBCS22L08",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22ET6",
                    "grade": "B"
                },
                {
                    "subject_code": "EBDS22103",
                    "grade": "A"
                },
                {
                    "subject_code": "EBDS22104",
                    "grade": "S"
                },
                {
                    "subject_code": "EBEE22OE8",
                    "grade": "B"
                },
                {
                    "subject_code": "EBBT22OE1",
                    "grade": "A"
                }
            ]
        },
        {
            "student_regno": "221191101064",
            "student_name": "JAYADITHYA R",
            "results": [
                {
                    "subject_code": "EBCC22107",
                    "grade": "S"
                },
                {
                    "subject_code": "EBCS22009",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22010",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22E11",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22L07",
                    "grade": "H"
                },
                {
                    "subject_code": "EBCS22L08",
                    "grade": "H"
                },
                {
                    "subject_code": "EBDS22ET6",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22103",
                    "grade": "H"
                },
                {
                    "subject_code": "EBDS22104",
                    "grade": "H"
                },
                {
                    "subject_code": "EBEC22OE2",
                    "grade": "S"
                }
            ]
        },
        {
            "student_regno": "221191101088",
            "student_name": "MD TAQIYY FAIZ M",
            "results": [
                {
                    "subject_code": "EBCC22107",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22009",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22010",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22E11",
                    "grade": "B"
                },
                {
                    "subject_code": "EBCS22L07",
                    "grade": "H"
                },
                {
                    "subject_code": "EBCS22L08",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22ET6",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22103",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22104",
                    "grade": "S"
                },
                {
                    "subject_code": "EBME22OE7",
                    "grade": "S"
                },
                {
                    "subject_code": "EBCS22006",
                    "grade": "B"
                },
                {
                    "subject_code": "EBCT22OE5",
                    "grade": "A"
                }
            ]
        },
        {
            "student_regno": "221191101129",
            "student_name": "SASI KUMAR M",
            "results": [
                {
                    "subject_code": "EBCC22107",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22009",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22010",
                    "grade": "A"
                },
                {
                    "subject_code": "EBCS22E11",
                    "grade": "B"
                },
                {
                    "subject_code": "EBCS22L07",
                    "grade": "H"
                },
                {
                    "subject_code": "EBCS22L08",
                    "grade": "H"
                },
                {
                    "subject_code": "EBDS22ET6",
                    "grade": "S"
                },
                {
                    "subject_code": "EBDS22103",
                    "grade": "H"
                },
                {
                    "subject_code": "EBDS22104",
                    "grade": "S"
                },
                {
                    "subject_code": "EBEE22OE6",
                    "grade": "S"
                }
            ]
        }
    ]

    filename="./static/grade-points.jsonl"
    grade_points={}
    with open(filename, 'r', encoding="utf-8") as in_file:
        for line in in_file:
            data=json.loads(line)
            grade_points[data['letter_grade']]=data['grade_points']

    filename="./static/all-sub-v2.jsonl"
    credits={}
    with open(filename, 'r', encoding="utf-8") as in_file:
        for line in in_file:
            data=json.loads(line)
            credits[data['subject_code']] = data['credits']

    acq_credits=0
    total_credits=0

    for line in test_dict:
            data= json.loads(line)

            acq_credits+=grade_points[data['grade']] * credits[data['subject_code']]
            total_credits+=credits[data['subject_code']]
    gpa = acq_credits / total_credits
    print(f"Gpa is {gpa:.2f}")
    new_dict ={}
    return {

    }