"""
Base bot class with shared browser automation logic.
All platform bots inherit from this.
"""

import logging
import random
import time
import hashlib
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Realistic desktop user agents (updated regularly)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# Common screen resolutions to randomize viewport
SCREEN_RESOLUTIONS = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (1600, 900), (1280, 800), (1280, 1024),
    (1680, 1050), (1920, 1200), (2560, 1440),
]

# Common timezones
TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Phoenix", "America/Detroit",
    "America/Indiana/Indianapolis", "America/Boise",
    "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Australia/Sydney", "Asia/Tokyo", "Asia/Kolkata",
]


def _get_consistent_value(seed: str, choices: list):
    """Pick a deterministic value from choices based on a seed string.
    This ensures the same account always gets the same fingerprint."""
    idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(choices)
    return choices[idx]


class BaseBot:
    """
    Abstract base class for platform bots.
    Handles browser lifecycle, human-like delays, and common utilities.
    """

    PLATFORM = 'base'

    def __init__(self, account: dict, headless: bool = True):
        """
        Args:
            account: Dict with username, password, proxy, user_agent keys
            headless: Run browser in headless mode
        """
        self.account = account
        self.username = account.get('username', '')
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.is_logged_in = False
        self._comments_made = 0

    def launch_browser(self):
        """Launch Playwright browser with proxy, unique fingerprint, and stealth measures."""
        from playwright.sync_api import sync_playwright

        # --- Enforce proxy requirement ---
        proxy = self.account.get('proxy')
        if not proxy:
            logger.warning(
                f"[{self.PLATFORM}] No proxy set for {self.username}! "
                f"Running without a proxy risks detection and IP bans."
            )

        # --- Generate consistent fingerprint per account ---
        seed = f"{self.PLATFORM}_{self.username}"
        ua = self.account.get('user_agent') or _get_consistent_value(seed, USER_AGENTS)
        resolution = _get_consistent_value(seed + "_res", SCREEN_RESOLUTIONS)
        timezone_id = _get_consistent_value(seed + "_tz", TIMEZONES)
        color_depth = _get_consistent_value(seed + "_cd", [24, 32])
        device_memory = _get_consistent_value(seed + "_dm", [4, 8, 16])
        hardware_concurrency = _get_consistent_value(seed + "_hc", [4, 8, 12, 16])

        self._playwright = sync_playwright().start()

        launch_args = {
            'headless': self.headless,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-infobars',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--metrics-recording-only',
                '--mute-audio',
                '--no-first-run',
                f'--window-size={resolution[0]},{resolution[1]}',
            ]
        }

        if proxy:
            # Parse proxy - supports http://user:pass@host:port or host:port
            proxy_config = {'server': proxy}
            if '@' in proxy:
                # Extract credentials from proxy URL
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(proxy)
                    if parsed.username and parsed.password:
                        proxy_config = {
                            'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                            'username': parsed.username,
                            'password': parsed.password,
                        }
                except Exception:
                    proxy_config = {'server': proxy}
            launch_args['proxy'] = proxy_config

        self.browser = self._playwright.chromium.launch(**launch_args)

        context_args = {
            'viewport': {'width': resolution[0], 'height': resolution[1]},
            'screen': {'width': resolution[0], 'height': resolution[1]},
            'user_agent': ua,
            'locale': _get_consistent_value(seed + "_locale", ['en-US', 'en-GB', 'en-CA', 'en-AU']),
            'timezone_id': timezone_id,
            'color_scheme': 'light',
            'has_touch': False,
            'is_mobile': False,
            'java_script_enabled': True,
            'ignore_https_errors': True,
        }

        self.context = self.browser.new_context(**context_args)

        # --- Comprehensive stealth injection ---
        self.context.add_init_script("""
        () => {
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Override navigator.plugins to look real
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
                          description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                          description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin',
                          description: '' },
                    ];
                    plugins.length = 3;
                    return plugins;
                }
            });

            // Override navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Fake deviceMemory and hardwareConcurrency
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => """ + str(device_memory) + """
            });

            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => """ + str(hardware_concurrency) + """
            });

            // Fix permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);

            // Hide automation indicators in chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() { return {}; },
                csi: function() { return {}; },
                app: { isInstalled: false },
            };

            // Spoof screen properties
            Object.defineProperty(screen, 'colorDepth', { get: () => """ + str(color_depth) + """ });
            Object.defineProperty(screen, 'pixelDepth', { get: () => """ + str(color_depth) + """ });

            // Override toString for spoofed functions to hide modifications
            const nativeToString = Function.prototype.toString;
            const spoofedFns = new Set();
            Function.prototype.toString = function() {
                if (spoofedFns.has(this)) {
                    return 'function () { [native code] }';
                }
                return nativeToString.call(this);
            };
            spoofedFns.add(Function.prototype.toString);

            // Override WebGL renderer to avoid fingerprinting
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };
            spoofedFns.add(WebGLRenderingContext.prototype.getParameter);

            // Prevent canvas fingerprinting
            const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                if (type === 'image/png' || type === undefined) {
                    const context = this.getContext('2d');
                    if (context) {
                        const imageData = context.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {
                            imageData.data[i] ^= 1;  // Tiny noise to break fingerprinting
                        }
                        context.putImageData(imageData, 0, 0);
                    }
                }
                return origToDataURL.apply(this, arguments);
            };
            spoofedFns.add(HTMLCanvasElement.prototype.toDataURL);
        }
        """)

        self.page = self.context.new_page()

        # Block common tracking/bot-detection scripts
        self.page.route("**/*", lambda route: (
            route.abort() if any(tracker in route.request.url for tracker in [
                'datadome.co', 'perimeterx.net', 'kasada.io',
                'arkoselabs.com', 'funcaptcha.com',
            ]) else route.continue_()
        ))

        logger.info(f"[{self.PLATFORM}] Browser launched for {self.username} "
                     f"(proxy={'yes' if proxy else 'NO'}, "
                     f"viewport={resolution[0]}x{resolution[1]})")

    def close_browser(self):
        """Clean up browser resources."""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, '_playwright') and self._playwright:
                self._playwright.stop()
            logger.info(f"[{self.PLATFORM}] Browser closed for {self.username}")
        except Exception as e:
            logger.error(f"[{self.PLATFORM}] Error closing browser: {e}")

    def human_delay(self, min_sec: float = 1, max_sec: float = 3):
        """Wait a random amount of time to mimic human behavior."""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def human_type(self, selector: str, text: str, min_delay: int = 30, max_delay: int = 100):
        """Type text character by character with random delays between keystrokes."""
        element = self.page.locator(selector)
        element.click()
        self.human_delay(0.3, 0.7)
        for char in text:
            element.press_sequentially(char, delay=random.randint(min_delay, max_delay))
            # Occasional pause mid-typing
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 1.0))

    def safe_click(self, selector: str, timeout: int = 10000):
        """Click an element with error handling."""
        try:
            self.page.locator(selector).click(timeout=timeout)
            self.human_delay(0.5, 1.5)
            return True
        except Exception as e:
            logger.warning(f"[{self.PLATFORM}] Failed to click {selector}: {e}")
            return False

    def wait_and_click(self, selector: str, timeout: int = 15000):
        """Wait for element to be visible then click."""
        try:
            self.page.wait_for_selector(selector, state='visible', timeout=timeout)
            self.human_delay(0.3, 0.8)
            self.page.locator(selector).click()
            return True
        except Exception as e:
            logger.warning(f"[{self.PLATFORM}] Element not found {selector}: {e}")
            return False

    def scroll_page(self, direction: str = 'down', amount: int = 300):
        """Scroll the page like a human."""
        if direction == 'down':
            self.page.mouse.wheel(0, amount + random.randint(-50, 50))
        else:
            self.page.mouse.wheel(0, -(amount + random.randint(-50, 50)))
        self.human_delay(0.5, 1.5)

    def random_mouse_movement(self):
        """Move mouse randomly to appear human."""
        x = random.randint(100, 1100)
        y = random.randint(100, 700)
        self.page.mouse.move(x, y)

    def take_screenshot(self, name: str = ''):
        """Take a debug screenshot."""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"data/screenshots/{self.PLATFORM}_{self.username}_{name}_{ts}.png"
        try:
            self.page.screenshot(path=filename)
            logger.debug(f"Screenshot saved: {filename}")
        except Exception:
            pass

    @property
    def comments_made(self) -> int:
        return self._comments_made

    # --- Abstract methods to implement in subclasses ---

    def login(self) -> bool:
        raise NotImplementedError

    def find_posts(self, **kwargs) -> list[dict]:
        raise NotImplementedError

    def post_comment(self, post_url: str, comment_text: str) -> bool:
        raise NotImplementedError
