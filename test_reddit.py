from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)
driver.get("https://www.reddit.com/r/OculusQuest/")
time.sleep(5)
try:
    posts = driver.find_elements(By.TAG_NAME, "article")
    for post in posts[:3]:
        shreddit = post.find_element(By.TAG_NAME, "shreddit-post")
        title = post.get_attribute("aria-label") or ""
        body_parts = []
        try:
            body_elements = shreddit.find_elements(By.CSS_SELECTOR, "div[slot='text-body'], div[id^='post-rtjson-content'], div.feed-card-text-preview, p")
            body_parts = [b.text.strip() for b in body_elements if b.text.strip()]
        except Exception as e:
            pass
        print("TITLE:", title)
        print("BODY:", "".join(body_parts))
        print("---")
except Exception as e:
    print(e)
driver.quit()