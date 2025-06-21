# app.py

import toml
import os
import requests
import json
import re
from flask import Flask, render_template, jsonify, request, Response, stream_with_context

# --- Flask App Initialization ---
app = Flask(__name__, template_folder='templates')

# --- Configuration Loading ---
def load_config():
    """Loads configuration from pyproject.toml."""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'pyproject.toml')
        with open(config_path, 'r') as f:
            config_data = toml.load(f)
            return config_data.get('tool', {}).get('app', {}).get('settings', {})
    except FileNotFoundError:
        print("Error: pyproject.toml not found.")
        return {}
    except Exception as e:
        print(f"An error occurred while loading config: {e}")
        return {}

config = load_config()

# Load settings from the config file, with defaults
API_ENDPOINT = config.get('api_endpoint', 'http://localhost:1234/v1/chat/completions')
MODEL_NAME = config.get('model_name', '')
WEATHER_MCP_URL = config.get('weather_mcp_url', 'http://localhost:8002/mcp/')
NEWS_MCP_URL = config.get('news_mcp_url', 'http://localhost:8003/mcp/')
# --- FIX: Update the default URL to remove the /mcp path ---
FETCH_MCP_URL = config.get('fetch_mcp_url', 'http://localhost:8000/')
X_POST_MCP_URL = config.get('x_post_mcp_url', 'http://localhost:8004/mcp/')
PC_MCP_URL = config.get('pc_mcp_url', 'http://localhost:8005/mcp/')
PC_SECRET = config.get('pc_secret', "ChangeThisNow")

def extract_user_and_keywords_with_llm(user_question):
    """
    Uses the LLM to extract the X username and important keywords from the user's question.
    Returns (username, [keywords]).
    """
    prompt = (
        "Given the user's question about X/Twitter, extract the username (just the handle, without the @) "
        "and up to 5 keywords or phrases that are important for searching tweets. "
        "If no username is found, output 'unknown' for the username.\n"
        "ALWAYS return your answer as JSON in this exact format:\n"
        '{"username": "USERNAME", "keywords": ["keyword1", "keyword2"]}\n'
        "Examples:\n"
        'Q: What did @elonmusk post about Starlink and Mars?\n'
        'A: {"username": "elonmusk", "keywords": ["Starlink", "Mars"]}\n'
        'Q: Show me what Professor Mohammad Marandi said about sanctions.\n'
        'A: {"username": "s_m_marandi", "keywords": ["sanctions"]}\n'
        'Q: What is being said about AI? (no username)\n'
        'A: {"username": "unknown", "keywords": ["AI"]}\n'
        "\nNow, here is the user question:\n"
        f"{user_question}\n"
        "Your answer:"
    )
    messages = [{"role": "user", "content": prompt}]
    llm_payload = {"model": MODEL_NAME or None, "messages": messages}
    resp = requests.post(API_ENDPOINT, json=llm_payload)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    import json
    try:
        # Look for the first JSON object in the LLM output
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_str = content[first_brace:last_brace + 1]
            parsed = json.loads(json_str)
            username = parsed.get("username", "unknown")
            keywords = parsed.get("keywords", [])
        else:
            username = "unknown"
            keywords = [user_question]
    except Exception as e:
        # fallback: just use the whole question as the keywords
        username = "unknown"
        keywords = [user_question]
    return username, keywords


# --- The Chat Logic Route ---

@app.route('/chat', methods=['POST'])
def chat_handler():
    """
    Handles all chat logic, acting as a middleware between the frontend
    and the various backend services (LLM, Weather, News, Fetch).
    """
    try:
        data = request.get_json()
        conversation_history = data.get('messages', [])

        if not conversation_history:
            return jsonify({"error": "No messages provided"}), 400

        user_message = conversation_history[-1]['content']
        user_message = user_message.replace(u'\u00A0', ' ')

        words = user_message.split()
        clean_words = [word for word in words if not word.startswith('/')]
        clean_message = ' '.join(clean_words)

        tool_to_call = None

        if '/use_weather' in user_message:
            tool_to_call = { "name": "get_weather", "params": {"location": clean_message}, "url": WEATHER_MCP_URL, "context_prompt": "Answer the user's question conversationally based on this weather data:" }

        elif '/use_news' in user_message:
            import re
            params = {}
            limit_match = re.search(r'\b(\d+)\b', clean_message)
            if limit_match: params['limit'] = int(limit_match.group(1))
            known_sources = ["bbc", "reuters", "associated_press", "nyt_world", "techcrunch", "prestv", "stand4muslim"]
            found_source = next((src for src in known_sources if src.lower() in clean_message.lower()), "all")
            params['source'] = found_source
            tool_to_call = { "name": "get_latest_news", "params": params, "url": NEWS_MCP_URL, "context_prompt": "You are an intelligent news analyst agent. Your goal is to provide a precise and relevant answer to the user's question by analyzing the raw data provided below, which has been fetched from live news feeds." }
        
        elif '/use_fetch' in user_message:
            found_url = None
            for word in clean_message.split():
                if word.lower().startswith('http://') or word.lower().startswith('https://'):
                    found_url = word
                    break
            
            if not found_url:
                return jsonify({"error": "The Fetch tool was enabled, but a valid URL (starting with http:// or https://) could not be found in your prompt."}), 400
            
            tool_to_call = {
                "name": "fetch",
                "params": {"url": found_url},
                "url": FETCH_MCP_URL,
                "context_prompt": "You are a web content analyst. Your goal is to provide a precise and relevant summary of the raw text content provided below, which has been fetched from a web page."
            }
        elif '/use_xpost' in user_message:
            # NEW: Use LLM to extract username and keywords from user message!
            try:
                username, keywords = extract_user_and_keywords_with_llm(clean_message)
                import re
                if username == "unknown":
                    match = re.search(r'@([a-zA-Z0-9_]{1,15})', user_message)
                    if match:
                        username = match.group(1)

            except Exception as e:
                return jsonify({"error": f"Failed to extract username/keywords: {e}"}), 500

            # If no username was found, you can (optionally) fallback to a default, or ask the user for more info.
            if username == "unknown":
                return jsonify({"error": "No Twitter/X username found in your question. Please specify a user."}), 400

            query_string = ", ".join(keywords) if keywords else clean_message

            tool_to_call = {
                "name": "search_user_tweets",
                "params": {
                    "username": username,
                    "query": query_string
                },
                "url": X_POST_MCP_URL,
                "context_prompt": (
                    f"Here are recent X posts from @{username} about the user's topic. "
                    "If relevant, quote or summarize what was said. If none found, say so clearly."
                )
            }
        
        elif '/use_pc' in user_message:
            # --- simple routing logic ---
            cmd_map = {
                'disk': 'disk',
                'list': 'list',
                'date': 'date'
            }
            chosen = 'system_info'   # default tool
            args   = {}

            for key, val in cmd_map.items():
                if key in clean_message.lower():
                    chosen = 'run_command'
                    args   = {"name": val, "secret": PC_SECRET}
                    break

            if chosen == 'system_info':
                tool_to_call = {
                    "name": "system_info",
                    "params": {},
                    "url":  PC_MCP_URL,
                    "context_prompt":
                        "Below is live system information from the user's PC. "
                        "Answer the user's question or describe the stats."
                }
            else:
                tool_to_call = {
                    "name": "run_command",
                    "params": args,
                    "url":  PC_MCP_URL,
                    "context_prompt":
                        "Below is the result of a command run on the user's PC. "
                        "Explain or summarise it for the user."
                }

        if not tool_to_call:
            llm_payload = { "model": MODEL_NAME or None, "messages": conversation_history, "stream": True }
            llm_req = requests.post(API_ENDPOINT, json=llm_payload, stream=True)
            return Response(stream_with_context(llm_req.iter_content(chunk_size=1024)), content_type=llm_req.headers['Content-Type'])

        # --- Generic Tool Calling Logic ---
        # --- FIX: Added detailed debugging prints ---
        try:
            print("\n--- TOOL CALL DEBUG START ---")
            print(f"Attempting to call tool: {tool_to_call['name']}")
            print(f"Target URL: {tool_to_call['url']}")
            
            tool_payload = { "jsonrpc": "2.0", "method": "tools/call", "params": {"name": tool_to_call['name'], "arguments": tool_to_call['params']}, "id": f"req-{int(os.urandom(4).hex(), 16)}" }
            print(f"Payload being sent: {json.dumps(tool_payload, indent=2)}")
            
            headers = { 'Accept': 'application/json, text/event-stream' }
            tool_response = requests.post(tool_to_call['url'], json=tool_payload, headers=headers)
            
            print(f"Tool server responded with status: {tool_response.status_code}")
            tool_response.raise_for_status()
            
            response_text = tool_response.text
            data_line = next((line for line in response_text.split('\n') if line.startswith('data:')), None)
            if not data_line: raise ValueError(f"Invalid response from {tool_to_call['name']} server")

            tool_json = json.loads(data_line.lstrip('data: '))
            tool_data = tool_json.get("result", {}).get("content", [{}])[0].get("text", f"Could not retrieve data from {tool_to_call['name']}.")
            print("--- TOOL CALL DEBUG END ---\n")

        except requests.exceptions.RequestException as e:
            # This block will now catch connection errors, HTTP errors, etc.
            print(f"\n--- TOOL CALL FAILED ---")
            print(f"Error calling tool '{tool_to_call['name']}': {e}")
            if e.response:
                print(f"Response Status Code: {e.response.status_code}")
                print(f"Response Body: {e.response.text}")
            print("--- TOOL CALL FAILED END ---\n")
            tool_data = f"I was unable to fetch the information from the {tool_to_call['name']} service."
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            tool_data = f"An unexpected error occurred while trying to use the {tool_to_call['name']} service."

        # --- Agentic Reasoning Prompt ---
        llm_prompt = (
            f"{tool_to_call['context_prompt']}\n\n"
            f"=== RAW DATA START ===\n{tool_data}\n=== RAW DATA END ===\n\n"
            f"Based *only* on the raw data above, analyze it and provide a concise, direct answer to the following user question:\n"
            f"User's Question: \"{clean_message}\"\n\n"
            f"Your Answer:"
        )
        
        final_messages = [{"role": "user", "content": llm_prompt}]
        llm_payload = { "model": MODEL_NAME or None, "messages": final_messages, "stream": True }
        llm_req = requests.post(API_ENDPOINT, json=llm_payload, stream=True)
        return Response(stream_with_context(llm_req.iter_content(chunk_size=1024)), content_type=llm_req.headers['Content-Type'])

    except Exception as e:
        print(f"An error occurred in /chat: {e}")
        return jsonify({"error": str(e)}), 500


# --- Existing Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def get_config():
    return jsonify({
        'apiEndpoint': API_ENDPOINT, 'modelName': MODEL_NAME,
        'weatherMcpUrl': WEATHER_MCP_URL, 'newsMcpUrl': NEWS_MCP_URL,
        'fetchMcpUrl': FETCH_MCP_URL
    })

# --- Main Execution Block ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)