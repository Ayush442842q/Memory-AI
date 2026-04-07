"""
Provider abstraction — add any LLM backend by implementing the BaseProvider interface.
"""
import os
import json
import urllib.request
import urllib.error


class BaseProvider:
    def chat(self, model: str, messages: list, api_key: str = "") -> str:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def chat(self, model, messages, api_key=""):
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY or pass it in the request.")
        payload = json.dumps({"model": model, "messages": messages}).encode()
        req = urllib.request.Request(
            self.BASE_URL,
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(BaseProvider):
    BASE_URL = "https://api.anthropic.com/v1/messages"

    def chat(self, model, messages, api_key=""):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY or pass it in the request.")
        system_msgs = [m for m in messages if m["role"] == "system"]
        chat_msgs   = [m for m in messages if m["role"] != "system"]
        body = {"model": model, "max_tokens": 2048, "messages": chat_msgs}
        if system_msgs:
            body["system"] = system_msgs[0]["content"]
        payload = json.dumps(body).encode()
        req = urllib.request.Request(
            self.BASE_URL,
            data=payload,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        return data["content"][0]["text"]


class GeminiProvider(BaseProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def chat(self, model, messages, api_key=""):
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("Gemini API key required. Set GEMINI_API_KEY or pass it in the request.")
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        payload = json.dumps({"contents": contents}).encode()
        url = self.BASE_URL.format(model=model) + f"?key={key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]


class OllamaProvider(BaseProvider):
    BASE_URL = "http://localhost:11434/api/chat"

    def chat(self, model, messages, api_key=""):
        payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
        req = urllib.request.Request(
            self.BASE_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
            return data["message"]["content"]
        except urllib.error.URLError:
            raise ValueError("Ollama not running. Start it with: ollama serve")


PROVIDERS = {
    "openai":    OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "gemini":    GeminiProvider(),
    "ollama":    OllamaProvider(),
}

def get_provider(name: str) -> BaseProvider:
    p = PROVIDERS.get(name)
    if not p:
        raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}")
    return p
