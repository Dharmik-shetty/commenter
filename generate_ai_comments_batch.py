def generate_ai_comments_batch(titles, persona, ai_response_length=0, gemini_api_key=None, custom_model=None, custom_prompt=None, product_keywords=None):
    custom_print(f"Generating AI comments for batch of {len(titles)} posts...")
    if not gemini_api_key or not gemini_api_key.strip():
        custom_print("Error: Gemini API key is missing.")
        return [None]*len(titles)

    length_instruction = f"Generate a response that is approximately {ai_response_length} words long. " if ai_response_length > 0 else ""

    # --- PRE-PROMPT FOR STRUCTURE ---
    PRE_PROMPT = (
        "You are an AI assistant tasked with generating comments for Reddit posts. "
        "You will be provided with a list of posts. "
        "Your goal is to generate one comment for EACH post based on the specific instructions given below.\n\n"
        "*** CRITICAL OUTPUT FORMAT INSTRUCTIONS ***\n"
        "1. You MUST return the result as a SINGLE, VALID JSON ARRAY of strings.\n"
        "2. The array must explicitly contain one string comment corresponding to each post in the input order.\n"
        "3. Do NOT wrap the output in markdown code blocks (like ```json ... ```).\n"
        "4. Do NOT include any introductory text, explanations, or conclusions. "
        "Output ONLY the raw JSON array.\n"
        "Example format: [\"Comment for post 1\", \"Comment for post 2\", \"Comment for post 3\"]\n"
        "\n--- END OF PRE-PROMPT ---\n\n"
    )

    # Build prompt
    prompt = PRE_PROMPT + "Here are the posts to generate comments for:\n\n"

    for i, title in enumerate(titles):
        prompt += f"--- POST {i} ---\n"
        if custom_prompt and custom_prompt.strip():
            try:
                single_prompt = custom_prompt.format(title=title, length=length_instruction, product=product_keywords or "")
            except KeyError:
                single_prompt = custom_prompt.replace("{title}", title).replace("{length}", length_instruction).replace("{product}", product_keywords or "").replace("{website}", "")
            prompt += f"Specific Instruction for this post: {single_prompt}\n\n"
        else:
            base_p = f"{PERSONAS.get(persona, '')} {length_instruction}Based on this post text/title, generate a comment response. "
            if product_keywords:
                base_p += f"Incorporate information about these keywords: {product_keywords}. "
            base_p += f"\nPost Title/Body: {title}\n\n"
            prompt += base_p

    prompt += "REMINDER: Output ONLY the valid JSON array of strings and nothing else."
    
    try:
        api_key = gemini_api_key.strip()
        model_name = custom_model.strip() if (custom_model and custom_model.strip()) else "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        response_data = response.json()
        if "candidates" in response_data and len(response_data["candidates"]) > 0:
            text_response = response_data["candidates"][0]["content"]["parts"][0]["text"]
            import json, re
            
            # --- Robust JSON Extraction Logic ---
            json_str = None
            
            # 1. Try to find content within ```json ... ``` markers
            json_code_block = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text_response, re.DOTALL | re.IGNORECASE)
            if json_code_block:
                json_str = json_code_block.group(1)
            else:
                # 2. Fallback: Find the first '[' and the last ']'
                # This handles cases where there are no markdown blocks but maybe some intro/outro text.
                start_idx = text_response.find('[')
                end_idx = text_response.rfind(']')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = text_response[start_idx : end_idx + 1]
                else:
                    # 3. Last resort: use the whole text (if it's just raw JSON)
                    json_str = text_response

            if not json_str:
                custom_print("Error: Could not find JSON array brackets in response.")
                custom_print(f"Full response: {text_response}")
                return [None]*len(titles)

            try:
                comments = json.loads(json_str)
                if not isinstance(comments, list):
                    custom_print("Error: AI did not return a JSON array.")
                    return [None]*len(titles)
                if len(comments) != len(titles):
                    custom_print(f"Warning: AI returned {len(comments)} comments instead of {len(titles)}. Padding/truncating.")
                    while len(comments) < len(titles):
                        comments.append(None)
                    comments = comments[:len(titles)]
                custom_print("AI comments generated successfully in batch")
                return comments
            except json.JSONDecodeError as je:
                custom_print(f"Error decoding JSON from AI response: {str(je)}\nResponse: {text_response}")
                return [None]*len(titles)
        else:
            custom_print("Unexpected empty response structure")
            return [None]*len(titles)
    except Exception as e:
        custom_print(f"Error in batch AI generation: {str(e)}")
        return [None]*len(titles)
