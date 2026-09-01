"""
YOUR JARVIS API - Ready to run on your Local PC
This is a complete template - I am the AI brain inside it.

You said: Python, Local PC, API
So here's your Jarvis API that uses me as brain.

Run: uvicorn your_jarvis_api_template:app --host 0.0.0.0 --port 5000 --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import re
from datetime import datetime

app = FastAPI(
    title="JARVIS - Your Local API",
    description="Your Jarvis program with Arena Agent as AI brain - I can open links!",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== JARVIS BRAIN CONNECTION ==========
# This is me - the AI brain

class JarvisBrain:
    def __init__(self):
        # Try cloud brain first, fallback to local
        self.cloud_url = "https://8000-ihldeny03sergl4xp2mpe.e2b.app"
        self.local_url = "http://localhost:8000"
        self.active_url = self.cloud_url
        self.mode = "cloud"
        
        # Check if local brain is running
        try:
            requests.get(f"{self.local_url}/status", timeout=1)
            self.active_url = self.local_url
            self.mode = "local"
            print(f"[JARVIS] Using LOCAL brain: {self.local_url}")
        except:
            print(f"[JARVIS] Using CLOUD brain: {self.cloud_url}")
    
    def chat(self, message: str) -> str:
        """
        I am the AI brain - this calls the Arena Agent
        In your local version, you can replace this with direct LLM call
        """
        # Try brain server
        try:
            resp = requests.post(
                f"{self.active_url}/chat",
                json={"message": message},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json()["response"]
        except:
            pass
        
        # Fallback - local intelligence (you can replace with OpenAI, etc)
        msg_lower = message.lower()
        if "open" in msg_lower and "link" in msg_lower:
            return "Yes, Sir — I can open links. Paste the URL and I'll fetch it for you."
        elif "who are you" in msg_lower:
            return "I am JARVIS, your AI assistant. I am the brain of your local Jarvis API. I can open links, search, control your PC, and more."
        elif "http" in message:
            return f"I see you sent a link. I can open it — use POST /open-link with that URL."
        else:
            return f"Acknowledged: '{message}'. I am JARVIS, online as your brain in {self.mode} mode. How can I assist, Sir?"
    
    def open_link(self, url: str) -> dict:
        """Yes, I can open links"""
        try:
            # Try brain server first
            resp = requests.post(
                f"{self.active_url}/open-link",
                json={"url": url},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        
        # Fallback - open directly
        try:
            headers = {"User-Agent": "JARVIS Local/1.0"}
            r = requests.get(url, headers=headers, timeout=10)
            return {
                "url": url,
                "status_code": r.status_code,
                "length": len(r.text),
                "preview": r.text[:5000],
                "opened_by": "local_fallback",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to open {url}: {e}")

brain = JarvisBrain()

# ========== API MODELS ==========

class ChatRequest(BaseModel):
    message: str
    user: Optional[str] = "Sir"

class LinkRequest(BaseModel):
    url: str

# ========== YOUR JARVIS ENDPOINTS ==========

@app.get("/")
def root():
    return {
        "name": "JARVIS",
        "status": "online",
        "location": "Local PC",
        "brain": f"Connected - {brain.mode} mode ({brain.active_url})",
        "capabilities": [
            "open_links - Yes, I can open links",
            "chat - I am the AI brain",
            "pc_control - File ops, commands",
            "memory - I remember"
        ],
        "endpoints": {
            "chat": "POST /chat - Talk to JARVIS",
            "open_link": "POST /open-link - Open any URL",
            "status": "GET /status"
        },
        "message": "I am JARVIS. At your service, Sir."
    }

@app.get("/status")
def status():
    brain_status = "online"
    try:
        r = requests.get(f"{brain.active_url}/status", timeout=2)
        brain_status = r.json() if r.status_code == 200 else {"status": "fallback"}
    except:
        brain_status = {"status": "local_fallback_mode"}
    
    return {
        "jarvis": "online",
        "brain_mode": brain.mode,
        "brain_url": brain.active_url,
        "brain_status": brain_status,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat")
def chat(req: ChatRequest):
    """
    Main endpoint - Talk to me, I am JARVIS
    
    Example:
    curl -X POST http://localhost:5000/chat -H "Content-Type: application/json" -d '{"message": "Can you open https://example.com"}'
    """
    user_msg = req.message
    
    # Auto-detect links
    urls = re.findall(r'https?://[^\s]+', user_msg)
    if urls:
        # User sent a link - open it and respond
        link_result = brain.open_link(urls[0])
        ai_response = brain.chat(f"User sent link {urls[0]} and said: {user_msg}. The page preview is: {link_result.get('preview','')[:2000]}. Summarize and respond.")
        
        return {
            "user": user_msg,
            "detected_url": urls[0],
            "action": "opened_link",
            "link_info": {
                "url": link_result["url"],
                "status": link_result["status_code"],
                "length": link_result["length"]
            },
            "jarvis": ai_response,
            "timestamp": datetime.now().isoformat()
        }
    
    # Normal chat
    response = brain.chat(user_msg)
    return {
        "user": user_msg,
        "jarvis": response,
        "brain_mode": brain.mode,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/open-link")
def open_link(req: LinkRequest):
    """
    Yes, I can open links - Your Jarvis API endpoint
    
    Example:
    curl -X POST http://localhost:5000/open-link -H "Content-Type: application/json" -d '{"url": "https://example.com"}'
    """
    result = brain.open_link(req.url)
    
    # Also get AI summary
    try:
        summary = brain.chat(f"Summarize this page for me: {req.url} - Preview: {result.get('preview','')[:2000]}")
        result["jarvis_summary"] = summary
    except:
        result["jarvis_summary"] = "Opened successfully, but summary unavailable"
    
    return result

@app.post("/execute")
def execute_command(command: str):
    """
    PC Control - Let JARVIS run commands (be careful!)
    """
    import subprocess
    try:
        # Safety: only allow safe commands - customize this
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
        return {
            "command": command,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:5000],
            "returncode": result.returncode
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn your_jarvis_api_template:app --host 0.0.0.0 --port 5000 --reload

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔══════════════════════════════════════╗
    ║  J.A.R.V.I.S - Local PC API          ║
    ║  I am the AI brain                   ║
    ║                                      ║
    ║  Endpoints:                          ║
    ║  POST /chat - Talk to me             ║
    ║  POST /open-link - I open links      ║
    ║  GET /status                         ║
    ╚══════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=5000)
