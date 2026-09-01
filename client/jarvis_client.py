"""
JARVIS Client - Connect your existing Jarvis program to me (the AI brain)

Use this in your already-running Jarvis program to make me its AI.

Example:
    from jarvis_client import JarvisBrain
    
    jarvis = JarvisBrain(api_url="http://localhost:8000")
    response = jarvis.chat("Can you open this link? https://example.com")
    print(response)
"""

import requests
import json
from typing import Optional

class JarvisBrain:
    """
    Client to connect your Jarvis program to the JARVIS AI brain (me)
    """
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        print(f"[JARVIS Client] Connecting to AI brain at {self.api_url}")
        
        # Test connection
        try:
            status = self.status()
            print(f"[JARVIS Client] Connected! Brain status: {status['status']} - {status['name']} is {status['message']}")
        except Exception as e:
            print(f"[JARVIS Client] Warning: Could not connect to brain at {self.api_url}: {e}")
            print(f"[JARVIS Client] Make sure the JARVIS API server is running: uvicorn api.main:app --host 0.0.0.0 --port 8000")
    
    def status(self):
        """Check if JARVIS brain is online"""
        resp = requests.get(f"{self.api_url}/status", timeout=5)
        resp.raise_for_status()
        return resp.json()
    
    def chat(self, message: str, speak: bool = False) -> dict:
        """
        Talk to me - I am the AI brain
        Your Jarvis program calls this to get AI responses
        """
        resp = requests.post(
            f"{self.api_url}/chat",
            json={"message": message, "speak": speak},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return data
    
    def open_link(self, url: str) -> dict:
        """Ask me to open a link - Yes I can open links"""
        resp = requests.post(
            f"{self.api_url}/open-link",
            json={"url": url},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    
    def search(self, query: str) -> dict:
        """Ask me to search the web"""
        resp = requests.post(
            f"{self.api_url}/search",
            json={"query": query},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    
    def remember(self, key: str, value: str):
        """Tell me to remember something"""
        resp = requests.post(
            f"{self.api_url}/memory/fact?key={key}&value={value}",
            timeout=5
        )
        return resp.json()

# Example usage for your existing Jarvis program
if __name__ == "__main__":
    # Connect to the brain
    # If you're running in Arena preview, use the preview URL
    # If local, use http://localhost:8000
    
    brain = JarvisBrain(api_url="http://localhost:8000")
    
    print("\n=== JARVIS AI Brain Demo ===")
    print("Your external Jarvis program is now using me as its AI\n")
    
    # Test 1: Chat
    print("You: Can you open links?")
    response = brain.chat("Can you open links?")
    print(f"JARVIS: {response['response']}\n")
    
    # Test 2: Open link
    print("You: Open https://example.com")
    try:
        link_data = brain.open_link("https://example.com")
        print(f"JARVIS: Opened link, status {link_data['status_code']}, length {link_data['length']} chars")
        print(f"Preview: {link_data['preview'][:200]}...\n")
    except Exception as e:
        print(f"Failed: {e}\n")
    
    # Test 3: Chat with context
    print("You: Who are you?")
    response = brain.chat("Who are you?")
    print(f"JARVIS: {response['response']}\n")
    
    print("=== Ready to integrate into your Jarvis program ===")
    print("Just import JarvisBrain and call .chat() - I am the AI")
