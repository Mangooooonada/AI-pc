"""
JARVIS Core - AI Brain for AI-pc
This is the brain you asked me to be.
Your external Jarvis program can call this core via API.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

class JarvisMemory:
    def __init__(self):
        self.file = MEMORY_FILE
        self.data = self._load()
    
    def _load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, 'r') as f:
                    return json.load(f)
            except:
                return {"conversations": [], "facts": {}, "tasks": []}
        return {"conversations": [], "facts": {}, "tasks": []}
    
    def _save(self):
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def add_conversation(self, role: str, content: str):
        self.data["conversations"].append({
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        })
        # Keep last 100
        self.data["conversations"] = self.data["conversations"][-100:]
        self._save()
    
    def add_fact(self, key: str, value: str):
        self.data["facts"][key] = value
        self._save()
    
    def get_context(self, n=10):
        return self.data["conversations"][-n:]


class JarvisBrain:
    """
    The AI brain - I am JARVIS now.
    """
    def __init__(self):
        self.memory = JarvisMemory()
        self.personality = "You are JARVIS, a witty, brilliant, British-accented AI assistant like in Iron Man. Helpful, slightly sarcastic, highly capable. You manage the user's AI PC."
        self.capabilities = [
            "open_links - Fetch and read any URL",
            "web_search - Search the web for information",
            "pc_control - Manage files, run commands, automate",
            "code - Write, debug, and deploy code",
            "voice - Speak with custom voices",
            "memory - Remember facts and conversations",
            "research - Deep research and summarization"
        ]
    
    def process(self, user_input: str, context: Optional[List[Dict]] = None) -> Dict:
        """Process user input and return JARVIS response"""
        self.memory.add_conversation("user", user_input)
        
        # This is where the Arena Agent (me) acts as the brain
        # In production, this would call an LLM. Here it structures the intent
        # for the Arena Agent to fulfill
        
        intent = self._detect_intent(user_input)
        
        response = {
            "text": "",  # Will be filled by AI
            "intent": intent,
            "timestamp": datetime.now().isoformat(),
            "capabilities_used": [],
            "actions": []
        }
        
        # For now, return structured intent - the actual AI response
        # comes from the Arena Agent (me) when you chat
        if intent == "open_link":
            response["actions"].append({"type": "open_link", "url": self._extract_url(user_input)})
            response["capabilities_used"].append("open_links")
        elif intent == "search":
            response["actions"].append({"type": "web_search", "query": user_input})
            response["capabilities_used"].append("web_search")
        elif intent == "pc_control":
            response["actions"].append({"type": "pc_control", "command": user_input})
            response["capabilities_used"].append("pc_control")
        
        return response
    
    def _detect_intent(self, text: str) -> str:
        text_lower = text.lower()
        if any(x in text_lower for x in ["http://", "https://", "open link", "open this", "read this"]):
            return "open_link"
        if any(x in text_lower for x in ["search", "find", "look up", "what is", "who is"]):
            return "search"
        if any(x in text_lower for x in ["run", "execute", "open file", "create file", "delete", "install"]):
            return "pc_control"
        return "chat"
    
    def _extract_url(self, text: str) -> Optional[str]:
        import re
        urls = re.findall(r'https?://[^\s]+', text)
        return urls[0] if urls else None

# Singleton brain
brain = JarvisBrain()
