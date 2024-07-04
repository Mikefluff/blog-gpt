import os
from fastapi import FastAPI, HTTPException, Depends
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from pydantic import BaseModel
from contextlib import asynccontextmanager
import shutil
from uuid import uuid4


app = FastAPI()

session_file_path = 'session_name'

class PhoneNumber(BaseModel):
    phone: str
    app_id: int
    app_hash: str

class OTPVerification(BaseModel):
    phone: str
    code: str
    phone_code_hash: str

class StoryRequest(BaseModel):
    peer: str
    file_path: str
    spoiler: bool = True
    ttl_seconds: int = 42

class TelegramClientManager:
    def __init__(self):
        self.client = None
        self.app_id = None
        self.app_hash = None

    async def get_client(self):
        if not self.client:
            raise HTTPException(status_code=400, detail="Client not initialized")
        return self.client

    async def initialize_client(self, app_id: int, app_hash: str):
        if self.client:
            await self.client.disconnect()
        self.app_id = app_id
        self.app_hash = app_hash
        self.client = TelegramClient(session_file_path, app_id, app_hash)
        await self.client.connect()

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()

client_manager = TelegramClientManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client_manager.disconnect()

app = FastAPI(lifespan=lifespan)

async def get_client():
    return await client_manager.get_client()

# Create an uploads directory if it doesn't exist
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount the uploads directory
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.post("/upload_image")
async def upload_image(file: UploadFile = File(...)):
    try:
        # Generate a unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # Save the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate the URI
        file_uri = f"/uploads/{unique_filename}"
        
        return {"file_uri": file_uri, "message": "Image uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_otp")
async def generate_otp(phone_number: PhoneNumber):
    try:
        await client_manager.initialize_client(phone_number.app_id, phone_number.app_hash)
        client = await get_client()
        result = await client.send_code_request(phone_number.phone, force_sms=True)
        return {"phone_code_hash": result.phone_code_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/verify_otp")
async def verify_otp(otp_verification: OTPVerification):
    try:
        client = await get_client()
        await client.sign_in(
            otp_verification.phone,
            code=otp_verification.code,
            phone_code_hash=otp_verification.phone_code_hash,
        )
        user = await client.get_me()
        return {"message": f"Authenticated as {user.first_name}"}
    except SessionPasswordNeededError:
        raise HTTPException(status_code=401, detail="Two-step verification is enabled. Please provide the password.")
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=401, detail="Invalid code provided.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_story")
async def send_story(story_request: StoryRequest, client: TelegramClient = Depends(get_client)):
    try:
        if not await client.is_user_authorized():
            raise HTTPException(status_code=401, detail="Unauthorized. Please authenticate first.")
        result = await client(functions.stories.SendStoryRequest(
            peer=story_request.peer,
            media=types.InputMediaUploadedPhoto(
                file=await client.upload_file(story_request.file_path),
                spoiler=story_request.spoiler,
                ttl_seconds=story_request.ttl_seconds
            ),
            privacy_rules=[types.InputPrivacyValueAllowContacts()]
        ))
        return {"message": "Story sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
