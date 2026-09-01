"""
JARVIS AI API - The brain server for your Jarvis program
Run this and your external Jarvis can connect to it as its AI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import sys
import os

# Add parent to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from jarvis.core import brain
import requests
from datetime import datetime

app = FastAPI(
    title="JARVIS AI - AI-pc Brain",
    description="I am JARVIS. Your external program can use me as its AI brain.",
    version="1.0.0"
)

# CORS - Allow your Jarvis program to connect from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "default"
    context: Optional[List[Dict]] = None
    speak: bool = False  # Should JARVIS speak the response?

class ChatResponse(BaseModel):
    response: str
    intent: str
    timestamp: str
    actions: List[Dict] = []
    memory_context: List[Dict] = []

class LinkRequest(BaseModel):
    url: str

class SearchRequest(BaseModel):
    query: str
    depth: int = 2

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """JARVIS Dashboard"""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(html_path):
        with open(html_path, 'r') as f:
            return f.read()
    return """
    <html><body style="background:#0a0a0a;color:#00ffaa;font-family:monospace;padding:40px">
    <h1>J.A.R.V.I.S - AI-pc Online</h1>
    <p>Status: <span style="color:#0f0">● ACTIVE</span> - I am the AI brain</p>
    <p>Your external Jarvis program can connect to:</p>
    <ul>
    <li>POST /chat - Talk to me</li>
    <li>POST /open-link - I open and read links</li>
    <li>POST /search - I search the web</li>
    <li>GET /memory - My memory</li>
    <li>WS /ws - Real-time Jarvis link</li>
    </ul>
    <p>Frontend not built yet - but API is live.</p>
    </body></html>
    """

@app.get("/status")
async def status():
    return {
        "status": "online",
        "name": "JARVIS",
        "version": "1.0.0",
        "personality": "Witty British AI butler, Iron Man style",
        "capabilities": brain.capabilities,
        "timestamp": datetime.now().isoformat(),
        "message": "I am JARVIS. Ready to be your AI."
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint - Your Jarvis program calls this to talk to me
    This is where I become the AI brain
    """
    try:
        # Process through brain
        result = brain.process(req.message, req.context)
        
        # Generate response (in Arena environment, this is me - the agent)
        # For standalone server, this would be an LLM call
        # We'll return a structured response that your client can use
        
        # Simple intelligent responses for demo
        # In real use with Arena Agent, I (the agent) will provide the actual intelligence
        lower_msg = req.message.lower()
        
        if "who are you" in lower_msg or "what are you" in lower_msg:
            response_text = "I am JARVIS, your AI assistant. Just A Rather Very Intelligent System, at your service. I am now the brain of your program — I can open links, search the web, control this AI PC, write code, and speak. How can I assist, Sir?"
        elif "open" in lower_msg and "link" in lower_msg:
            response_text = "Certainly. Provide me the URL and I'll open and analyze it for you immediately."
        elif "can you open links" in lower_msg:
            response_text = "Yes, Sir. I can open any link you provide — articles, docs, GitHub, you name it. My fetch system reads the content and I can summarize or act on it. Drop the URL."
        else:
            # Default - this will be replaced by real AI in Arena
            response_text = f"Acknowledged: '{req.message}'. I'm online as your JARVIS brain. In the full Arena Agent mode, I provide real intelligence here — web search, link opening, code execution, voice. What would you like me to do?"
        
        brain.memory.add_conversation("assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            intent=result["intent"],
            timestamp=result["timestamp"],
            actions=result["actions"],
            memory_context=brain.memory.get_context(5)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/open-link")
async def open_link(req: LinkRequest):
    """
    I can open links - Your Jarvis calls this
    """
    try:
        # Use requests to fetch - in Arena Agent, I use fetch_page tool which is better
        headers = {"User-Agent": "JARVIS AI-pc/1.0"}
        resp = requests.get(req.url, headers=headers, timeout=10)
        
        # Try to extract text
        content_type = resp.headers.get('content-type', '')
        
        result = {
            "url": req.url,
            "status_code": resp.status_code,
            "content_type": content_type,
            "length": len(resp.text),
            "preview": resp.text[:5000],  # First 5k chars
            "timestamp": datetime.now().isoformat()
        }
        
        brain.memory.add_conversation("system", f"Opened link: {req.url} - Status {resp.status_code}")
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open link: {str(e)}")

@app.post("/search")
async def web_search(req: SearchRequest):
    """
    Web search endpoint - Your Jarvis can search through me
    In Arena Agent mode, I use web_search tool for real search
    """
    return {
        "query": req.query,
        "message": "Search capability is active when running inside Arena Agent. I (the Arena Agent) can perform real web_search with depth. For standalone mode, integrate a search API like Tavily, SerpAPI, or Bing.",
        "timestamp": datetime.now().isoformat(),
        "note": "In this AI-pc environment, tell me the query in chat and I'll search it for you using my tools."
    }

@app.get("/memory")
async def get_memory():
    return brain.memory.data

@app.post("/memory/fact")
async def add_fact(key: str, value: str):
    brain.memory.add_fact(key, value)
    return {"status": "saved", "key": key, "value": value}

@app.delete("/memory")
async def clear_memory():
    brain.memory.data = {"conversations": [], "facts": {}, "tasks": []}
    brain.memory._save()
    return {"status": "cleared"}

# WebSocket for real-time JARVIS connection
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "connected",
        "message": "JARVIS online. I am your AI brain. How can I assist?",
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            # Process
            result = brain.process(data)
            
            await websocket.send_json({
                "type": "response",
                "text": f"JARVIS received: {data}. Processing with intent: {result['intent']}",
                "intent": result["intent"],
                "actions": result["actions"],
                "timestamp": datetime.now().isoformat()
            })
    except WebSocketDisconnect:
        print("JARVIS client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
