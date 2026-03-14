import google.generativeai as genai

genai.configure(api_key="API KEY HERE")

model = genai.GenerativeModel("gemini-2.5-flash")

response = model.generate_content("Explain transformers in simple terms. in 30 words")

print(response.text)