import os
import requests
import json


class AIGenerator:
    def __init__(self, model="gpt-3.5-turbo"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = model
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate_response(self, prompt):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }

        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()

            result = response.json()
            return result["choices"][0]["message"]["content"].strip()

        except requests.RequestException as e:
            return f"Error: {str(e)}"
        except KeyError as e:
            return f"Error parsing response: {str(e)}"