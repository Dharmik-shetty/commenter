import time
import requests
import json
import random
import os
#import spacy
import logging
import re
import nltk
from collections import defaultdict
from nltk.stem import PorterStemmer
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    StaleElementReferenceException,
)
import undetected_chromedriver as uc  
import os
import threading
global_history_lock = threading.Lock()
HISTORY_FILE = "commented_urls.txt"
_history_cache = None
_history_file_mtime = 0

def get_history_set():
    global _history_cache, _history_file_mtime
    with global_history_lock:
        if not os.path.exists(HISTORY_FILE):
             return set()
        try:
            mtime = os.path.getmtime(HISTORY_FILE)
            if _history_cache is None or mtime > _history_file_mtime:
                 with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                     _history_cache = set(line.strip() for line in f)
                 _history_file_mtime = mtime
            return _history_cache
        except Exception:
            return set()

def is_url_in_history(url):
    try:
        return url in get_history_set()
    except Exception:
        return False

def add_url_to_history(url):
    global _history_cache
    try:
        with global_history_lock:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(url + "\n")
            if _history_cache is not None:
                _history_cache.add(url)
    except Exception:
        pass

YOUR_SITE_URL = "AIBrainL.ink"
YOUR_APP_NAME = "Reddit Scraper with AI Comments"

PERSONAS = {
    "teenager": "Respond as a texting teenager with lots of spelling mistakes, grammatical errors, run-on sentences, capitalization issues, and punctuation problems.",
    "normal": "Respond as a normal person on Reddit, with occasional spelling mistakes, grammatical errors, or run-on sentences.",
    "educated": "Respond as an educated person with very rare spelling mistakes.",
    "bot": "Respond with perfect spelling, grammar, and punctuation, like a bot would.",
}

SORT_TYPES = ["hot", "new", "top", "rising"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Load the English model (do this at the beginning of your script)
#nlp = spacy.load("en_core_web_md")
nltk.download('punkt_tab', quiet=True)

# def semantic_similarity(keywords, title, threshold=0.5, sleep_time=1):
#     if nlp is None:
#         custom_print("spaCy model not loaded. Skipping semantic similarity check.")
#         return False

#     try:
        
#         title_doc = nlp(title)
#         for keyword in keywords:
#             try:
#                 time.sleep(sleep_time / 3)
#                 keyword_doc = nlp(keyword)
#                 time.sleep(sleep_time / 3)
#                 similarity = title_doc.similarity(keyword_doc)
#                 time.sleep(sleep_time / 3)
#                 custom_print(f"Similarity between '{keyword}' and '{title}': {similarity}")
#                 logger.info(f"Similarity between '{keyword}' and '{title}': {similarity}")
                
#                 if similarity >= threshold:
#                     return True
#             except ValueError as e:
#                 custom_print(f"Error processing keyword '{keyword}': {str(e)}")
#                 logger.info(f"Error processing keyword '{keyword}': {str(e)}")
#                 continue
#     except Exception as e:
#         custom_print(f"Error in semantic_similarity function: {str(e)}")
#         logger.info(f"Error in semantic_similarity function: {str(e)}")
#         return False

#     return False

# Initialize the Porter Stemmer
ps = PorterStemmer()

def preprocess_text(text):
    # Convert to lowercase
    text = text.lower()
    # Remove apostrophes
    text = text.replace("'", "")
    # Remove non-alphanumeric characters and replace with space
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    # Tokenize the text
    tokens = nltk.word_tokenize(text)
    # Stem the tokens
    stemmed_tokens = [ps.stem(token) for token in tokens]
    return ' '.join(stemmed_tokens)

def tokenize_processed_text(text):
    return [token for token in preprocess_text(text).split() if token]

def normalize_keywords(keywords):
    if isinstance(keywords, str):
        return [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]
    if isinstance(keywords, list):
        return [str(kw).strip().lower() for kw in keywords if str(kw).strip()]
    return []

def simple_semantic_similarity_score(keywords, title):
    try:
        processed_title = preprocess_text(title)
        title_tokens = set(tokenize_processed_text(title))

        if not title_tokens:
            return 0.0

        best_score = 0.0
        for keyword in normalize_keywords(keywords):
            processed_keyword = preprocess_text(keyword)
            keyword_tokens = set(tokenize_processed_text(keyword))

            if not keyword_tokens:
                continue

            # Phrase hit gives a strong score, token overlap gives partial score.
            phrase_hit_score = 1.0 if processed_keyword and processed_keyword in processed_title else 0.0
            overlap_score = len(keyword_tokens & title_tokens) / len(keyword_tokens)
            score = max(phrase_hit_score, overlap_score)

            if score > best_score:
                best_score = score

        return best_score

    except Exception as e:
        custom_print(f"Error in simple_semantic_similarity_score function: {str(e)}")
        return 0.0

def get_relevance_score(keywords, title, similarity_method, tensorflow_sleep_time=1.0):
    if similarity_method == "TensorFlow (semantic_similarity)":
        # TensorFlow model support was removed; fall back to robust keyword semantic scoring.
        custom_print("TensorFlow semantic mode selected; using fallback semantic keyword score.")
    return simple_semantic_similarity_score(keywords, title)

def evenly_distribute_results(results, max_comments, subreddit_order):
    if max_comments <= 0 or len(results) <= max_comments:
        return results

    grouped = defaultdict(list)
    for item in results:
        grouped[item.get("subreddit", "")].append(item)

    ordered_subreddits = [sub for sub in subreddit_order if sub in grouped]
    for sub in grouped.keys():
        if sub not in ordered_subreddits:
            ordered_subreddits.append(sub)

    if not ordered_subreddits:
        return results[:max_comments]

    selected = []
    indices = {sub: 0 for sub in ordered_subreddits}

    # Round-robin allocation provides even subreddit coverage and maximum diversification.
    while len(selected) < max_comments:
        added_in_round = False
        for sub in ordered_subreddits:
            idx = indices[sub]
            if idx < len(grouped[sub]):
                selected.append(grouped[sub][idx])
                indices[sub] += 1
                added_in_round = True
                if len(selected) >= max_comments:
                    break
        if not added_in_round:
            break

    return selected

    

custom_print_function = print

def set_print_function(func):
    global custom_print_function
    custom_print_function = func

def custom_print(*args, **kwargs):
    global custom_print_function
    custom_print_function(*args, **kwargs)

def create_header_extension(headers):
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Custom Header Modifier",
        "permissions": [
            "webRequest",
            "webRequestBlocking",
            "<all_urls>"
        ],
        "background": {
            "scripts": ["background.js"],
            "persistent": true
        }
    }
    """
    
    background_js = """
    var headers = %s;
    chrome.webRequest.onBeforeSendHeaders.addListener(
        function(details) {
            for (var header of headers) {
                var name = header.split(': ')[0];
                var value = header.split(': ')[1];
                var found = false;
                for (var i = 0; i < details.requestHeaders.length; ++i) {
                    if (details.requestHeaders[i].name.toLowerCase() === name.toLowerCase()) {
                        details.requestHeaders[i].value = value;
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    details.requestHeaders.push({name: name, value: value});
                }
            }
            return {requestHeaders: details.requestHeaders};
        },
        {urls: ["<all_urls>"]},
        ["blocking", "requestHeaders"]
    );
    """ % json.dumps(headers)

    extension_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "header_extension")
    os.makedirs(extension_dir, exist_ok=True)
    
    with open(os.path.join(extension_dir, "manifest.json"), "w") as f:
        f.write(manifest_json)
    
    with open(os.path.join(extension_dir, "background.js"), "w") as f:
        f.write(background_js)
    
    return extension_dir

def create_js_override_script(js_attributes):
    script = """
    (function() {
        var overrides = %s;
        
        function applyOverrides() {
            for (var key in overrides) {
                try {
                    var parts = key.split('.');
                    var obj = window;
                    for (var i = 0; i < parts.length - 1; i++) {
                        if (!(parts[i] in obj)) obj[parts[i]] = {};
                        obj = obj[parts[i]];
                    }
                    var propName = parts[parts.length - 1];
                    var propValue = overrides[key];

                    // Special handling for certain properties
                    if (key === 'navigator.userAgent') {
                        Object.defineProperty(navigator, 'userAgent', {get: function() { return propValue; }});
                    } else if (key === 'navigator.languages') {
                        Object.defineProperty(navigator, 'languages', {get: function() { return JSON.parse(propValue); }});
                    } else if (key.startsWith('navigator.') || key.startsWith('screen.')) {
                        // For navigator and screen properties, use Object.defineProperty
                        Object.defineProperty(obj, propName, {
                            get: function() { return propValue; },
                            configurable: true
                        });
                    } else {
                        // For other properties, try direct assignment
                        obj[propName] = propValue;
                    }
                } catch (e) {
                    console.error('Failed to set ' + key + ': ' + e.message);
                }
            }
        }

        applyOverrides();
        
        // Reapply overrides when a new document is loaded in any frame
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'IFRAME') {
                            node.addEventListener('load', function() {
                                try {
                                    applyOverrides.call(node.contentWindow);
                                } catch (e) {
                                    console.error('Failed to apply overrides to iframe:', e);
                                }
                            });
                        }
                    });
                }
            });
        });
        
        observer.observe(document, { childList: true, subtree: true });
    })();
    """ % json.dumps(dict(attr.split(': ', 1) for attr in js_attributes))
    return script

def verify_fingerprint_persistence(driver, fingerprint_settings):
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get("about:blank")
    
    # Check JavaScript attributes
    for attr in fingerprint_settings.get("js_attributes", []):
        name, expected_value = attr.split(': ', 1)
        actual_value = driver.execute_script(f"return {name};")
        if str(actual_value) != expected_value:
            custom_print(f"Warning: JavaScript attribute {name} does not match. Expected {expected_value}, got {actual_value}")
    
    # Check headers (this is tricky and might require visiting a test page)
    custom_print("Remember to manually verify header persistence by visiting a fingerprinting test site in a new tab")
    
    driver.close()
    driver.switch_to.window(driver.window_handles[0])

def wait_for_element(driver, by, value, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except TimeoutException:
        custom_print(f"Timeout waiting for element: {value}")
        return None

def extract_comments(driver, url, max_comments, scroll_retries, button_retries):
    custom_print(f"Extracting comments from: {url}")
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(url)
    custom_print("Navigated to post page")

    comments = []
    try:
        custom_print("Waiting for comments to load...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "shreddit-comment"))
        )
        custom_print("Comments loaded successfully")

        last_comment_count = 0
        consecutive_same_count = 0

        while len(comments) < max_comments and consecutive_same_count < scroll_retries:
            # Try to click the "View more comments" button if it exists
            for _ in range(button_retries):
                try:
                    load_more_button = WebDriverWait(driver, 1).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'View more comments')]"))
                    )
                    driver.execute_script("arguments[0].click();", load_more_button)
                    custom_print("Clicked 'View more comments' button")
                    
                    break
                except TimeoutException:
                    custom_print("No 'View more comments' button found or not clickable")
            
            comment_elements = driver.find_elements(By.CSS_SELECTOR, "shreddit-comment")
            
            for element in comment_elements[len(comments):]:
                try:
                    comment_text = element.find_element(By.CSS_SELECTOR, "div[slot='comment'] p").text.strip()
                    author = element.get_attribute("author")
                    depth = int(element.get_attribute("depth"))
                    parent_id = element.get_attribute("parentid")
                    aria_label = element.get_attribute("arialabel")
                    time_element = element.find_element(By.CSS_SELECTOR, "faceplate-timeago time")
                    time_ago = time_element.text.strip()

                    if "thread level" in aria_label:
                        comment_info = f"Comment thread level {depth}: Reply from {author}"
                    else:
                        comment_info = f"Comment from {author}"

                    comments.append({
                        "text": comment_text,
                        "author": author,
                        "depth": depth,
                        "parent_id": parent_id,
                        "comment_info": comment_info,
                        "time_ago": time_ago
                    })

                    custom_print(f"Extracted comment {len(comments)}: {comment_info} - {time_ago}")
                    custom_print(f"Comment text: {comment_text}")

                    if len(comments) >= max_comments:
                        break

                except NoSuchElementException:
                    custom_print(f"Skipping comment due to missing elements")
                except Exception as e:
                    custom_print(f"Error extracting comment: {str(e)}")

            if len(comments) == last_comment_count:
                consecutive_same_count += 1
            else:
                consecutive_same_count = 0

            last_comment_count = len(comments)

            if len(comments) < max_comments and consecutive_same_count < scroll_retries:
                custom_print("Scrolling down to load more comments...")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Wait for new comments to load

        if len(comments) < max_comments:
            custom_print(f"Could only find {len(comments)} comments. There may not be {max_comments} comments available.")
        else:
            custom_print(f"Successfully extracted {len(comments)} comments.")

    except TimeoutException:
        custom_print("Timeout waiting for comments to load. Proceeding with available comments.")
    except Exception as e:
        custom_print(f"An error occurred while extracting comments: {str(e)}")
    finally:
        custom_print("Closing comment extraction window")
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

    return comments

def generate_ai_comment(title, persona, ai_response_length=0, gemini_api_key=None, custom_model=None, custom_prompt=None, product_keywords=None):
    custom_print("Generating AI comment...")

    # Validate API key
    if not gemini_api_key or not gemini_api_key.strip():
        custom_print("Error: Gemini API key is missing.")
        return None

    length_instruction = f"Generate a response that is approximately {ai_response_length} words long. " if ai_response_length > 0 else ""

    if custom_prompt and custom_prompt.strip():
        # Remove any {website} formatter since we dropped it
        # Safely formatting by only doing what's needed
        try:
            prompt = custom_prompt.format(
                title=title,
                length=length_instruction,
                product=product_keywords or ""
            )
        except KeyError:
            # Fallback if there are unused variables in their prompt like {website}
            prompt = custom_prompt.replace("{title}", title).replace("{length}", length_instruction).replace("{product}", product_keywords or "").replace("{website}", "")
    else:
        prompt = f"{PERSONAS.get(persona, '')} {length_instruction}Based on the following Reddit post text/title, generate an appropriate and insightful comment response. "
        if product_keywords:
            prompt += f"Incorporate information about these keywords: {product_keywords}. "
        prompt += f"\n\nPost: {title}\n"

    prompt += "\nGenerated comment:"

    try:
        api_key = gemini_api_key.strip()
        model_name = custom_model.strip() if (custom_model and custom_model.strip()) else "gemini-1.5-flash"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        # Parse Gemini Response
        response_data = response.json()
        if "candidates" in response_data and len(response_data["candidates"]) > 0:
            ai_comment = response_data["candidates"][0]["content"]["parts"][0]["text"]
            custom_print("AI comment generated successfully via Gemini API")
            custom_print(f"Generated comment: {ai_comment}")
            return ai_comment
        else:
            custom_print(f"Unexpected empty response structure: {response_data}")
            return None

    except requests.exceptions.RequestException as e:
        custom_print(f"Error making request to Gemini API: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            custom_print(f"Response status code: {e.response.status_code}")
            custom_print(f"Response content: {e.response.text}")
        return None
    except Exception as e:
        custom_print(f"Unexpected error generating AI comment: {str(e)}")
        return None


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
                start_idx = text_response.find('[')
                end_idx = text_response.rfind(']')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = text_response[start_idx : end_idx + 1]
                else:
                    # 3. Last resort: use the whole text
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


def post_comment(driver, ai_comment, post_url):
    
    custom_print(f"Attempting to post comment to URL: {post_url}")
    
    if not post_url:
        custom_print("Error: post_url is None or empty")
        return False

    try:
        # Extract post ID from URL
        post_id = post_url.split("/")[-3]
        custom_print(f"Extracted postid: {post_id}")

        # Get CSRF token from cookie
        csrf_token = driver.get_cookie("csrf_token")
        if not csrf_token:
            custom_print("Error: CSRF token not found in cookies")
            return False
        csrf_token = csrf_token["value"]
        
        # Prepare headers matching the browser request
        headers = {
            "accept": "text/vnd.reddit.partial+html, application/json",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "Referer": post_url,
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }

        # Prepare the comment content in the exact format Reddit expects
        comment_content = {
            "document": [{
                "e": "par",
                "c": [{
                    "e": "text",
                    "t": ai_comment,
                    "f": [[0, 0, len(ai_comment)]]
                }]
            }]
        }

        # Prepare the form data
        form_data = {
            "content": json.dumps(comment_content),
            "mode": "richText",
            "richTextMedia": "[]",
            "csrf_token": csrf_token
        }

        # Get all cookies from the driver
        cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}

        # Make the POST request
        response = requests.post(
            f"https://www.reddit.com/svc/shreddit/t3_{post_id}/create-comment",
            headers=headers,
            cookies=cookies,
            data=form_data
        )

        # Check response
        if response.status_code == 200:
            custom_print("Comment posted successfully")
            return True
        else:
            custom_print(f"Failed to post comment. Status code: {response.status_code}")
            custom_print(f"Response content: {response.text}")
            return False

    except Exception as e:
        custom_print(f"Error in post_comment: {str(e)}")
        return False
    
#def post_comment(driver, ai_comment, post_url):
    custom_print(f"Attempting to post the AI-generated comment to URL: {post_url}")
    
    if not post_url:
        custom_print("Error: post_url is None or empty")
        return False

    try:
        # Extract post ID from URL
        post_id = post_url.split("/")[-3]
        custom_print(f"Extracted postid: {post_id}")

        # Get CSRF token from cookie
        csrf_token = driver.get_cookie("csrf_token")
        if not csrf_token:
            custom_print("Error: CSRF token not found in cookies")
            return False
        csrf_token = csrf_token["value"]
        custom_print(f"CSRF Token: {csrf_token}")

        # Prepare the comment data
        comment_data = {
            "content": json.dumps(
                {
                    "document": [
                        {
                            "e": "par",
                            "c": [
                                {
                                    "e": "text",
                                    "t": ai_comment,
                                    "f": [[0, 0, len(ai_comment)]],
                                }
                            ],
                        }
                    ]
                }
            ),
            "mode": "richText",
            "richTextMedia": json.dumps([]),
            "csrf_token": csrf_token,
        }

        # Set up the request headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # Get all cookies from the driver
        cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
        
        custom_print("Comment data and headers prepared successfully")
        
        # For testing purposes, we'll just return True here
        # Make the POST request
        response = requests.post(
            f"https://www.reddit.com/svc/shreddit/t3_{post_id}/create-comment",
            headers=headers,
            cookies=cookies,
            data=comment_data,
        )

        custom_print(f"Response status: {response.status_code}")
        if response.status_code == 200:
         return True
        else:
         return False
        # In a real scenario, you would make the POST request here
        custom_print("Comment would be posted here in a real scenario")
        return True

    except Exception as e:
        custom_print(f"Error in post_comment: {str(e)}")
        return False



def find_chrome_executable():
    """Finds the Chrome executable path on Windows."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None

def login_and_scrape_reddit(
    username,
    password,
    subreddits,
    sort_type,
    max_articles,
    max_comments,
    min_wait_time,
    max_wait_time,
    custom_headers,
    ai_response_length,
    proxy_settings,
    fingerprint_settings,
    do_not_post,
    gemini_api_key,
    scroll_retries,
    button_retries,
    persona,
    custom_model,
    ai_batch_size,
    ai_wait_time,
    custom_prompt,
    product_keywords,
    similarity_threshold,
    similarity_method,
    tensorflow_sleep_time,
    per_subreddit_max_posts_to_check,
    existing_driver=None,
    resume_state=None,
    update_state_callback=None,
    headless=False
):
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--start-maximized")
    
    #chrome_options = Options()
    #chrome_options.add_argument("--start-maximized")

    #service = Service(ChromeDriverManager().install())
    #driver = webdriver.Chrome(service=service, options=chrome_options)
    if existing_driver:
        driver = existing_driver
        custom_print("Using existing WebDriver session")
        
    else:
        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--start-maximized")
        
        # Apply proxy settings
        if proxy_settings.get("enabled", False):
            proxy_string = f"{proxy_settings['type'].lower()}://{proxy_settings['host']}:{proxy_settings['port']}"
            options.add_argument(f'--proxy-server={proxy_string}')
            if proxy_settings.get("username") and proxy_settings.get("password"):
                options.add_argument(f"--proxy-auth={proxy_settings['username']}:{proxy_settings['password']}")

        # Attempt to find Chrome binary explicitly to avoid "Binary Location Must be a String" error
        chrome_path = find_chrome_executable()
        if chrome_path:
            options.binary_location = chrome_path
            custom_print(f"Explicitly set Chrome binary location: {chrome_path}")

        # Explicitly specify Chrome version to match the installed version
        try:
            driver = uc.Chrome(
                options=options
                # version_main=133  # Set to match your Chrome version 133.0.6943.142
            )
        except TypeError as e:
            if "Binary Location Must be a String" in str(e):
                 custom_print("Caught 'Binary Location Must be a String' error. Retrying with finding binary again or checking installation.")
                 # If we haven't found it yet, this might be why
                 if not chrome_path:
                      custom_print("Could not locate Chrome binary automatically. Please install Google Chrome.")
            raise e
        custom_print("New WebDriver session initialized")

        # Apply JavaScript attributes using CDP
        if fingerprint_settings.get("enabled", False):
            js_attributes = fingerprint_settings.get("js_attributes", [])
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": create_js_override_script(js_attributes)
            })
            
            # Verify persistence
            verify_fingerprint_persistence(driver, fingerprint_settings)
        custom_print("Navigating to Reddit login page...")
        driver.get("https://www.reddit.com/login")
              
        custom_print("Waiting for username field...")
        #username_field = wait_for_element(driver, By.ID, "login-username")
        username_field = WebDriverWait(driver, 999).until(
                EC.presence_of_element_located((By.ID, "login-username"))
            )
        custom_print("Waiting for password field...")
        #password_field = wait_for_element(driver, By.ID, "login-password")
        password_field = WebDriverWait(driver, 999).until(
                EC.presence_of_element_located((By.ID, "login-password"))
            )
        if username_field and password_field:
            custom_print("Entering username and password...")
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            custom_print("Logging in.. Waiting for articles to load...")

    custom_print("WebDriver initialized successfully")

    all_collected_info = []

    try:
        custom_print(f"username:{username}                      \n subreddits:{subreddits}                     \n sort-type:{sort_type}                     \n max_articles:{max_articles}                     \n max_comments:{max_comments}                     \n min_wait_time:{min_wait_time}                     \n max_wait_time:{max_wait_time}                     \n Ai response length:{ai_response_length}                     \n proxy settings:{proxy_settings}                     \n gemini api key:{gemini_api_key} \n fingerprint settings: {fingerprint_settings}  \n comment scroll retries: {scroll_retries} \n comment button retries: {button_retries}                     \n persona:{persona}                     \n custom model:{custom_model}                     \n product keywords:{product_keywords}                     \n similarity method:{similarity_method}                     \n similarity threshold:{similarity_threshold}                     \n tensorflow sleep time:{tensorflow_sleep_time}")                    
        
        try:
            wait_for_element(driver, By.CSS_SELECTOR, "shreddit-post")
            custom_print("Logged in. Articles loaded successfully")
        except TimeoutException:
            custom_print("Timeout waiting for login.")
            custom_print("Closing WebDriver...")
            driver.quit()
            return [], None

        normalized_keywords = normalize_keywords(product_keywords)
        threshold = float(similarity_threshold or 0.0)
        per_subreddit_limit = int(per_subreddit_max_posts_to_check or max_articles or 100)
        if per_subreddit_limit <= 0:
            per_subreddit_limit = int(max_articles or 100)

        base_scan_limit = int(max_articles or per_subreddit_limit or 100)
        if base_scan_limit <= 0:
            base_scan_limit = per_subreddit_limit

        subreddit_seen_urls = {subreddit: set() for subreddit in subreddits}
        
        # Load seen URLs from resume state if available
        if resume_state and "seen_urls" in resume_state:
            cached_seen = resume_state["seen_urls"]
            for sub, urls in cached_seen.items():
                if sub in subreddit_seen_urls:
                    subreddit_seen_urls[sub] = set(urls)

        def scrape_subreddit_once(subreddit_name, posts_to_check):
            custom_print(f"\nStarting to scrape subreddit: r/{subreddit_name} (checking up to {posts_to_check} posts this pass)")
            subreddit_url = f"https://www.reddit.com/r/{subreddit_name}/{sort_type}/"
            driver.get(subreddit_url)
            custom_print("Waiting for page to load...")

            try:
                # Wait up to 15 seconds to see if articles load
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "article"))
                )
                custom_print("Articles loaded.")
            except TimeoutException:
                custom_print(f"Timeout loading articles for r/{subreddit_name}. This subreddit might be banned, private, restricted, or empty. Skipping...")
                return [], 0

            collected_info = []
            relevant_posts_queue = []
            checked_posts = 0
            new_urls_processed = 0
            no_new_posts_count = 0

            while checked_posts < posts_to_check:
                posts = driver.find_elements(By.TAG_NAME, "article")
                custom_print(f"Found {len(posts)} visible posts in r/{subreddit_name}")

                new_posts_processed = False
                for post in posts:
                    if checked_posts >= posts_to_check:
                        break

                    try:
                        shreddit_post = post.find_element(By.TAG_NAME, "shreddit-post")
                        permalink = shreddit_post.get_attribute("permalink")
                        if not permalink:
                            continue
                        url = "https://www.reddit.com" + permalink

                        if url in subreddit_seen_urls[subreddit_name]:
                            continue
                            
                        # Prevent duplicate comments across multiple accounts
                        if is_url_in_history(url):
                            custom_print(f"Skipping post {url} - already processed by an account in the past.")
                            subreddit_seen_urls[subreddit_name].add(url)
                            continue

                        checked_posts += 1
                        new_urls_processed += 1
                        new_posts_processed = True
                        subreddit_seen_urls[subreddit_name].add(url)
                        
                        # Update state callback
                        if update_state_callback:
                             # Convert sets to lists for JSON serialization
                             seen_dict_serializable = {k: list(v) for k,v in subreddit_seen_urls.items()}
                             update_state_callback({
                                 "seen_urls": seen_dict_serializable,
                                 "last_activity": time.time(),
                                 "current_subreddit": subreddit_name
                             })

                        title = post.get_attribute("aria-label") or ""
                        try:
                            body_elements = shreddit_post.find_elements(By.CSS_SELECTOR, "div[slot='text-body'], div[id^='post-rtjson-content'], div.feed-card-text-preview, p")
                            body_text_parts = [b.text.strip() for b in body_elements if b.text.strip()]
                            if body_text_parts:
                                title = title + "\n" + "\n".join(body_text_parts)
                        except Exception:
                            pass

                        relevance_score = get_relevance_score(
                            normalized_keywords,
                            title,
                            similarity_method,
                            tensorflow_sleep_time,
                        )
                        is_relevant = relevance_score >= threshold
                        custom_print(
                            f"Post {checked_posts}/{posts_to_check} relevance={relevance_score:.3f} (threshold={threshold:.3f}) - {url}"
                        )

                        if is_relevant:
                            add_url_to_history(url)
                            comments = []
                            if max_comments > 0:
                                comments_to_extract = min(max_comments, 10)
                                custom_print(f"Extracting up to {comments_to_extract} comments...")
                                comments = extract_comments(driver, url, comments_to_extract, scroll_retries, button_retries)

                            relevant_posts_queue.append({
                                "subreddit": subreddit_name,
                                "title": title,
                                "url": url,
                                "comments": comments,
                                "relevance_score": round(relevance_score, 4),
                            })

                            if len(relevant_posts_queue) >= ai_batch_size:
                                titles_to_process = [p['title'] for p in relevant_posts_queue]
                                batch_comments = generate_ai_comments_batch(
                                    titles_to_process, persona, ai_response_length, gemini_api_key, custom_model, custom_prompt, normalized_keywords
                                )
                                for p, ai_c in zip(relevant_posts_queue, batch_comments):
                                    if ai_c:
                                        p['ai_comment'] = ai_c
                                        collected_info.append(p)
                                relevant_posts_queue.clear()
                                if ai_wait_time > 0:
                                    custom_print(f"Waiting {ai_wait_time} seconds before next AI request...")
                                    time.sleep(ai_wait_time)

                        else:
                            custom_print("Post skipped due to low relevance score.")

                    except StaleElementReferenceException:
                        custom_print(f"Stale element while processing r/{subreddit_name}; skipping one post.")
                    except NoSuchElementException as e:
                        custom_print(f"Missing element in r/{subreddit_name}: {str(e)}")
                    except Exception as e:
                        custom_print(f"Unexpected error processing post in r/{subreddit_name}: {str(e)}")

                if checked_posts >= posts_to_check:
                    break

                if not new_posts_processed:
                    no_new_posts_count += 1
                    if no_new_posts_count >= scroll_retries:
                        custom_print(f"No new posts discovered in r/{subreddit_name} after {scroll_retries} attempts.")
                        break
                else:
                    no_new_posts_count = 0

                last_height = driver.execute_script("return document.body.scrollHeight")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    no_new_posts_count += 1
                    if no_new_posts_count >= scroll_retries:
                        custom_print(f"Reached scroll limit in r/{subreddit_name}; moving on.")
                        break

            if relevant_posts_queue:
                titles_to_process = [p['title'] for p in relevant_posts_queue]
                batch_comments = generate_ai_comments_batch(
                    titles_to_process, persona, ai_response_length, gemini_api_key, custom_model, custom_prompt, normalized_keywords
                )
                for p, ai_c in zip(relevant_posts_queue, batch_comments):
                    if ai_c:
                        p['ai_comment'] = ai_c
                        collected_info.append(p)
                relevant_posts_queue.clear()
                if ai_wait_time > 0:
                    custom_print(f"Waiting {ai_wait_time} seconds before continuing...")
                    time.sleep(ai_wait_time)

            custom_print(f"Scraping pass complete for r/{subreddit_name}. Checked {checked_posts} posts, found {len(collected_info)} relevant posts.")
            return collected_info, new_urls_processed

        total_target = int(max_comments or 0)
        if total_target < 0:
            total_target = 0

        # Pass 1: respect per-subreddit post-check cap.
        resume_index = resume_state.get("current_subreddit_index", 0) if resume_state else 0
        
        for idx, subreddit in enumerate(subreddits):
            if idx < resume_index:
                custom_print(f"Skipping already scraped subreddit: r/{subreddit}")
                continue
            
            if update_state_callback:
                 update_state_callback({"current_subreddit_index": idx})

            collected_info, _ = scrape_subreddit_once(subreddit, per_subreddit_limit)
            all_collected_info.extend(collected_info)

        # Fallback passes: if max comments target is not met, scan more posts efficiently.
        if total_target > 0 and len(all_collected_info) < total_target:
            custom_print(
                f"Initial scan found {len(all_collected_info)} relevant posts, below target {total_target}. Running fallback extra scans."
            )
            extra_passes = 0
            max_extra_passes = 3
            fallback_scan_limit = max(base_scan_limit, per_subreddit_limit)

            while len(all_collected_info) < total_target and extra_passes < max_extra_passes:
                extra_passes += 1
                round_new_urls = 0
                round_new_relevant = 0
                custom_print(f"Starting fallback pass {extra_passes}/{max_extra_passes}...")

                for subreddit in subreddits:
                    collected_info, new_urls = scrape_subreddit_once(subreddit, fallback_scan_limit)
                    round_new_urls += new_urls
                    round_new_relevant += len(collected_info)
                    all_collected_info.extend(collected_info)

                    if len(all_collected_info) >= total_target:
                        break

                if round_new_urls == 0 or round_new_relevant == 0:
                    custom_print("Fallback pass produced no useful new matches; stopping extra scans.")
                    break

        # Final selection is diversified evenly across subreddits.
        if total_target > 0:
            pre_distribution_count = len(all_collected_info)
            all_collected_info = evenly_distribute_results(all_collected_info, total_target, subreddits)
            custom_print(
                f"Diversified selection complete. {len(all_collected_info)} posts selected from {pre_distribution_count} relevant matches."
            )

            if len(all_collected_info) < total_target:
                custom_print(
                    f"Could only prepare {len(all_collected_info)} comments out of target {total_target}; not enough relevant posts available."
                )

        if not do_not_post:
            custom_print("Auto-posting is enabled (do_not_post is False). Proceeding to post comments...")
            for info in all_collected_info:
                if info.get('ai_comment') and info.get('url'):
                    try:
                        wait_time = random.uniform(min_wait_time, max_wait_time)
                        custom_print(f"Waiting {wait_time:.1f} seconds before posting to {info['url']}...")
                        time.sleep(wait_time)
                        
                        success = post_comment(driver, info['ai_comment'], info['url'])
                        info['post_successful'] = success
                    except Exception as e:
                        custom_print(f"Failed to auto-post: {str(e)}")
                        info['post_successful'] = False
        else:
            custom_print("do_not_post is True. Skipping auto-posting. Comments are ready for manual review.")

    except Exception as e:
        custom_print(f"An unexpected error occurred: {str(e)}")
    finally:
        custom_print("Scraping process completed.")

    custom_print(f"Scraping completed for all subreddits. Total relevant posts processed: {len(all_collected_info)}")
    return all_collected_info, driver

if __name__ == "__main__":
    # This block can be used for testing the script directly
    pass
