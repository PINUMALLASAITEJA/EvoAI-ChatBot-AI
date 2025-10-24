import os
import re
import torch
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from transformers import AutoModelForCausalLM, AutoTokenizer
from serpapi import GoogleSearch
from groq import Groq

# Secret identity map
identity_responses = {
    "what is your name": "I'm EVO-AI, your virtual assistant.",
    "who are you": "I'm EVO-AI, an intelligent chatbot built to assist you.",
    "who made you": "I was created by B-tech students of Ace Engineering College, Ghatkesar.",
    "tell me about yourself": "I'm EVO-AI, your smart conversational partner powered by AI technologies."
}

# Load API keys
load_dotenv(dotenv_path="config/.env")
SERP_API_KEY = os.getenv("SERP_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
GROK_API_KEY = os.getenv("GROQ_API_KEY")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["EVO_AI_DB"]
collection = db["chat_history"]

# Torch model setup
use_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def load_model():
    model_name = "EleutherAI/gpt-neo-125M"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name).to(use_device)
    return tokenizer, model

tokenizer, model = load_model()

# Clean outputs
def clean_truncated(text):
    if "..." in text:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return " ".join(s for s in sentences if not s.endswith("..."))
    return text.strip()

# Google fallback
def search_google(query):
    params = {"q": query, "hl": "en", "gl": "us", "api_key": SERP_API_KEY}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        if "organic_results" in results and results["organic_results"]:
            return clean_truncated(results["organic_results"][0].get("snippet", ""))
    except:
        pass
    return "Sorry, I couldn't find anything on Google."

# Groq logic
def ask_grok(prompt):
    try:
        client = Groq(api_key=GROK_API_KEY)
        response = client.chat.completions.create(
            model="gemma-7b-it",
            messages=[{"role": "user", "content": prompt}]
        )
        return clean_truncated(response.choices[0].message.content)
    except Exception:
        return None

# GPT-Neo fallback
def generate_gpt_neo_response(user_input):
    try:
        input_ids = tokenizer.encode(user_input, return_tensors="pt").to(use_device)
        with torch.no_grad():
            output = model.generate(
                input_ids,
                max_new_tokens=300,
                do_sample=True,
                temperature=0.9,
                top_k=50,
                top_p=0.95,
                pad_token_id=tokenizer.eos_token_id
            )
        decoded = tokenizer.decode(output[0], skip_special_tokens=True)
        reply = decoded[len(user_input):].strip() if decoded.startswith(user_input) else decoded.strip()
        return reply if reply else None
    except:
        return None

# MongoDB history logging
def save_conversation(user_id, user_input, bot_response):
    collection.insert_one({
        "user_id": user_id,
        "user_input": user_input,
        "bot_response": bot_response
    })

def get_previous_messages(user_id, limit=5):
    conversations = collection.find({"user_id": user_id}).sort("_id", -1).limit(limit)
    lines = []
    seen = set()
    for c in conversations:
        line = f"You: {c['user_input']}\nEVO-AI: {c['bot_response']}"
        if line not in seen:
            lines.append(line)
            seen.add(line)
    return "\n".join(reversed(lines))

def get_default_greeting(user_id="default"):
    if not collection.find_one({"user_id": user_id}):
        greeting = "Hi, How can I assist you today?"
        save_conversation(user_id, "User entered chat", greeting)
        return greeting
    return None

# Final decision-making brain
def get_chat_response(user_input, user_id="default"):
    user_input_clean = user_input.lower().strip()

    # 🔒 Secret ID responses
    for key in identity_responses:
        if key in user_input_clean:
            response = identity_responses[key]
            save_conversation(user_id, user_input, response)
            return response

    # 🧠 Try Groq
    grok_response = ask_grok(user_input)
    if grok_response:
        save_conversation(user_id, user_input, grok_response)
        return grok_response

    # 🔎 Try SERP
    google_response = search_google(user_input)
    if google_response and "sorry" not in google_response.lower():
        save_conversation(user_id, user_input, google_response)
        return google_response

    # 🧠 Try GPT-Neo
    history = get_previous_messages(user_id)
    prompt = f"{history}\nYou: {user_input}\nEVO-AI:"
    gpt_neo_response = generate_gpt_neo_response(prompt)
    if gpt_neo_response:
        save_conversation(user_id, user_input, gpt_neo_response)
        return gpt_neo_response

    # ❌ Final fallback
    fallback_response = "❌ Sorry, I couldn’t find an accurate answer right now."
    save_conversation(user_id, user_input, fallback_response)
    return fallback_response
