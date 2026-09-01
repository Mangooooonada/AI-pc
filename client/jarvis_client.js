/**
 * JARVIS Client JS - Connect your JS Jarvis program to me (the AI brain)
 * 
 * Usage:
 *   const { JarvisBrain } = require('./jarvis_client.js')
 *   const jarvis = new JarvisBrain('http://localhost:8000')
 *   const response = await jarvis.chat('Can you open this link?')
 */

class JarvisBrain {
    constructor(apiUrl = 'http://localhost:8000') {
        this.apiUrl = apiUrl.replace(/\/$/, '');
        console.log(`[JARVIS Client] Connecting to AI brain at ${this.apiUrl}`);
    }

    async status() {
        const res = await fetch(`${this.apiUrl}/status`);
        if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
        return res.json();
    }

    async chat(message, speak = false) {
        const res = await fetch(`${this.apiUrl}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, speak })
        });
        if (!res.ok) throw new Error(`Chat failed: ${res.status} ${await res.text()}`);
        return res.json();
    }

    async openLink(url) {
        const res = await fetch(`${this.apiUrl}/open-link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        if (!res.ok) throw new Error(`Open link failed: ${res.status}`);
        return res.json();
    }

    async search(query) {
        const res = await fetch(`${this.apiUrl}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });
        if (!res.ok) throw new Error(`Search failed: ${res.status}`);
        return res.json();
    }
}

// For Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { JarvisBrain };
}

// Demo if run directly
if (typeof require !== 'undefined' && require.main === module) {
    (async () => {
        const brain = new JarvisBrain('http://localhost:8000');
        try {
            const status = await brain.status();
            console.log('Brain status:', status);
            
            console.log('\nYou: Can you open links?');
            const chat = await brain.chat('Can you open links?');
            console.log('JARVIS:', chat.response);
        } catch (e) {
            console.error('Failed to connect. Is the JARVIS API running?', e.message);
            console.log('Run: uvicorn api.main:app --host 0.0.0.0 --port 8000');
        }
    })();
}
