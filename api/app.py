from fastapi import FastAPI, UploadFile, File
import shutil
app = FastAPI()
@app.get("/")
def root():
    return {"hello":"world"}

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...)):
    with open(f"saved_{file.filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
        return {"filename": file.filename,
                "saved":f"saved_{file.filename}"}