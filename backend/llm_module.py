# Perplexity Sonar streaming API
import requests
import json
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

async def stream_llm_response(prompt):
    payload = {
        "model": "sonar-pro",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(PERPLEXITY_URL, headers=headers, json=payload, stream=True)
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])
                content = data['choices'][0]['delta'].get('content', '')
                await asyncio.sleep(0.01)
                yield content
