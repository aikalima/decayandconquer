import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.modules.health import get_ping_response

logging.basicConfig(filename='server.log', level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
async def ping():
    logging.info("ping received")
    return get_ping_response()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
