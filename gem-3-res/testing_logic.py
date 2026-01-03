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
    print(cleaned_filename)
    print(f"{cleaned_filename}_res.jsonl")