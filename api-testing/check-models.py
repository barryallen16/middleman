from google import genai
from dotenv import load_dotenv
import os
load_dotenv()
GEMINI_API_KEY = os.getenv("RESULTS_PROJ_APIKEY")
print(GEMINI_API_KEY)
client = genai.Client(api_key=GEMINI_API_KEY)

print("List of models that support generateContent:\n")
for m in client.models.list():
    for action in m.supported_actions:
        if action == "generateContent":
            print(m.name)

print("List of models that support embedContent:\n")
for m in client.models.list():
    for action in m.supported_actions:
        if action == "embedContent":
            print(m.name)