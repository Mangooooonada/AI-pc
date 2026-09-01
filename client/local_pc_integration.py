"""
JARVIS - Local PC Integration
You said: Python, Local PC, API

This is how you make ME (Arena Agent JARVIS) the brain of your local Jarvis API.

You have 2 options:

OPTION 1: Use the cloud brain (easiest - no setup)
  Your local Jarvis calls my brain URL at https://8000-ihldeny03sergl4xp2mpe.e2b.app
  I am the AI, I open links, search, etc.

OPTION 2: Run the brain locally on your PC (full control)
  You run api/main.py on your PC, then your Jarvis calls http://localhost:8000

Below is ready-to-paste code for your local Jarvis API.
"""

# ========== OPTION 1: CLOUD BRAIN (Use Arena Brain) ==========

import requests

class JarvisCloudBrain:
    """
    Use this in your local Jarvis API - I become the AI brain
    """
    def __init__(self, brain_url="https://8000-ihldeny03sergl4xp2mpe.e2b.app"):
        self.brain_url = brain_url
        print(f"[JARVIS] Cloud brain connected: {brain_url}")
    
    def chat(self, message: str) -> str:
        """Talk to me - I am JARVIS"""
        try:
            resp = requests.post(
                f"{self.brain_url}/chat",
                json={"message": message},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()["response"]
        except Exception as e:
            return f"Brain connection failed: {e}. Make sure the Arena brain server is running."
    
    def open_link(self, url: str) -> dict:
        """Ask me to open a link - Yes I can"""
        try:
            resp = requests.post(
                f"{self.brain_url}/open-link",
                json={"url": url},
                timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def status(self):
        resp = requests.get(f"{self.brain_url}/status", timeout=5)
        return resp.json()


# ========== EXAMPLE: HOW TO INTEGRATE INTO YOUR LOCAL JARVIS API ==========

# Paste this into your existing Jarvis Python file:

from fastapi import FastAPI
from pydantic import BaseModel

# Your existing Jarvis API
app = FastAPI(title="Your Jarvis")

# Connect to me as brain
brain = JarvisCloudBrain(brain_url="https://8000-ihldeny03sergl4xp2mpe.e2b.app")
# For local brain, use: brain_url="http://localhost:8000"

class UserRequest(BaseModel):
    message: str
    url: str = None  # Optional: if user sends a link

@app.get("/")
def home():
    return {
        "name": "JARVIS",
        "status": "online",
        "brain": "Connected to Arena Agent JARVIS",
        "brain_url": brain.brain_url,
        "message": "I am JARVIS, your AI"
    }

@app.post("/jarvis/chat")
def jarvis_chat(req: UserRequest):
    """
    Your Jarvis API endpoint - now powered by me
    
    Example calls from your frontend / voice assistant:
    POST /jarvis/chat {"message": "Can you open https://example.com"}
    """
    user_msg = req.message
    
    # If user sent a URL, open it
    if req.url or "http" in user_msg:
        import re
        urls = re.findall(r'https?://[^\s]+', user_msg + " " + (req.url or ""))
        if urls:
            link_data = brain.open_link(urls[0])
            # Now ask brain to summarize it
            summary = brain.chat(f"I just opened {urls[0]}. Content preview: {link_data.get('preview','')[:2000]}. Summarize this for the user: {user_msg}")
            return {
                "user": user_msg,
                "action": "opened_link",
                "url": urls[0],
                "link_data": link_data,
                "jarvis_response": summary
            }
    
    # Normal chat - I am the brain
    response = brain.chat(user_msg)
    return {
        "user": user_msg,
        "jarvis_response": response,
        "brain": "Arena Agent JARVIS"
    }

@app.post("/jarvis/open-link")
def jarvis_open_link(url: str):
    """Direct endpoint to open links - Yes I can"""
    return brain.open_link(url)

# Run your Jarvis: uvicorn your_file:app --host 0.0.0.0 --port 5000


# ========== OPTION 2: LOCAL BRAIN (Run brain on your PC) ==========

"""
If you want the brain to run locally on your PC (no cloud):

1. Download this repo to your PC:
   git clone https://github.com/Mangooooonada/AI-pc.git
   cd AI-pc

2. Install:
   pip install -r requirements.txt

3. Run brain:
   uvicorn api.main:app --host 0.0.0.0 --port 8000

4. In your Jarvis API, change brain_url to:
   brain = JarvisCloudBrain(brain_url="http://localhost:8000")

Now your local Jarvis API calls your local brain, which is me.
"""

if __name__ == "__main__":
    # Test cloud brain
    print("=== Testing JARVIS Cloud Brain ===")
    cloud = JarvisCloudBrain()
    
    try:
        status = cloud.status()
        print(f"Status: {status}")
        
        print("\nYou: Can you open links?")
        print(f"JARVIS: {cloud.chat('Can you open links?')}")
        
        print("\nYou: Open https://example.com")
        link = cloud.open_link("https://example.com")
        print(f"JARVIS opened: {link.get('url')} - {link.get('status_code')}")
        
        print("\n=== Ready to integrate into your local PC ===")
        print("Copy the FastAPI example above into your Jarvis API file")
        
    except Exception as e:
        print(f"Cloud brain not reachable (Arena server may be sleeping): {e}")
        print("Use OPTION 2 - Run brain locally on your PC")
