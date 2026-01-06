from google import genai
from google.genai import types
import os 
from dotenv import load_dotenv
import json

load_dotenv()
GEMINI_API_KEY=os.getenv('RESULTS_PROJ_APIKEY')

input_files=os.listdir('./input_')
for in_file in input_files:
    cleaned_filename = in_file.split(".")[0]
    with open(f"./input_/{in_file}", 'rb') as file:
        image_bytes= file.read()

    client=genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(model="gemini-3-flash-preview", 
                                            contents=[
                                                types.Part.from_bytes(data=image_bytes,
                                                                        mime_type="image/jpeg")
                                                                        ,
    """Extract the subject name,code and it's credits and return it in a structured jsonl form. 
    Like 
    {
    subject_name:''
    subject_code:''
    credits:
    }
    . Then create a multiple jsonl records as response as specified.
    if the uploaded image is not clear enough to perform the task at hand correctly , return a error json , prompting them to upload a clearer image.
    Be mindful of the difference between 'O' and '0' while extractning.
    """])
    print(response.text)
    lines=response.text.split("\n")

    if lines[0]=="```jsonl" and lines[-1] == "```":
        lines.remove(lines[0])
        lines.remove(lines[-1])
    with open(f"./output_/{cleaned_filename}_res.jsonl",'w', encoding="utf-8") as file_out:
        for line in lines:
            record = json.loads(line)
            file_out.write(json.dumps(record)+"\n")
