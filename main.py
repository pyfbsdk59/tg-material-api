from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.sessions import StringSession
import hashlib
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
TARGET_GROUP_ID = int(os.environ.get("TARGET_GROUP_ID", 0))

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@app.on_event("startup")
async def startup_event():
    await client.connect()

# ⬆️ 教材上傳端點
@app.post("/upload/")
async def upload_recording(
    file: UploadFile = File(...), 
    topic_id: int = Form(...),
    caption: str = Form(None)
):
    if not client.is_connected():
        await client.connect()

    temp_file_path = f"/tmp/{file.filename}"
    
    try:
        # 教材類仍需暫存以供上傳，同時計算 Hash 備用
        sha256_hash = hashlib.sha256()
        with open(temp_file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                sha256_hash.update(chunk)
        
        file_hash = sha256_hash.hexdigest()
        final_caption = caption if caption else f"📂 教材檔案：{file.filename}"

        message = await client.send_file(
            TARGET_GROUP_ID,
            file=temp_file_path,
            reply_to=topic_id,
            caption=final_caption,
            force_document=True
        )

        chat_id_str = str(TARGET_GROUP_ID).replace("-100", "")
        tg_link = f"https://t.me/c/{chat_id_str}/{message.id}"

        return {
            "success": True,
            "filename": file.filename,
            "telegram_link": tg_link,
            "file_hash": file_hash,
            "message_id": message.id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# ⬇️ 教材串流下載端點
@app.get("/download/{message_id}")
async def download_file(message_id: int):
    if not client.is_connected():
        await client.connect()

    message = await client.get_messages(TARGET_GROUP_ID, ids=message_id)
    if not message or not message.file:
        raise HTTPException(status_code=404, detail="找不到該檔案")

    async def file_streamer():
        async for chunk in client.iter_download(message.media, chunk_size=1024 * 1024):
            yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{message.file.name or "telegram_material"}"'
    }
    
    return StreamingResponse(
        file_streamer(), 
        media_type="application/octet-stream", 
        headers=headers
    )