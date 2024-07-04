from fastapi import FastAPI, HTTPException
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from pydantic import BaseModel

app = FastAPI()

session_file_path = 'session_name'

client = ''

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

@app.post("/generate_otp")
async def generate_otp(phone_number: PhoneNumber):
    try:
        client = TelegramClient(session_file_path, phone_number.app_id, phone_number.app_hash)
        await client.connect()
        result = await client.send_code_request(phone_number.phone, force_sms=True)
        phone_hash = result.phone_code_hash
        await client.disconnect()
        return {"phone_code_hash": phone_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/verify_otp")
async def verify_otp(otp_verification: OTPVerification):
    try:
        await client.sign_in(
            otp_verification.phone,
            code=otp_verification.code,
            phone_code_hash=otp_verification.phone_code_hash,
        )
        user = await client.get_me()
        await client.disconnect()
        return {"message": f"Authenticated as {user.first_name}"}
    except SessionPasswordNeededError:
        raise HTTPException(status_code=401, detail="Two-step verification is enabled. Please provide the password.")
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=401, detail="Invalid code provided.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_story")
async def send_story(story_request: StoryRequest):
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
        await client.disconnect()
        return {"message": "Story sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
