import time
import requests
import logging
import pandas as pd
import os
import re

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
UBER_LOGIN_URL = (
    "https://auth.uber.com/v2/?breeze_init_req_id=7a7db0f0-4ce5-4b4d-bc45-cbce3ef4999f "
    "&breeze_local_zone=phx6&next_url=https%3A%2F%2Fm.uber.com%2Flogin-redirect%2F"
    "%3Fmarketing_vistor_id%3D43139685-07cf-4836-80bd-dcbf077de8db%26previousPath%3D%252F"
    "%26uclick_id%3Dbb971367-5b8d-4c39-8c2c-f95e73bd096b&state=3AeIps-hR9KGubqmqdpnsZGHV4Tb64W5r2UARh9gXFA%3D"
)

UBER_SUBMIT_URL = "https://auth.uber.com/v2/submit-form "

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Referer": "https://auth.uber.com/ ",
    "Origin": "https://auth.uber.com ",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "*/*"
}

COUNTRY_CODE = "+91"  # India
POLL_INTERVAL = 60  # Seconds between checks

# --- Utility Functions ---

def load_phone_numbers():
    try:
        df = pd.read_excel("phone_numbers.xlsx", engine="openpyxl")
        if "phone_number" not in df.columns:
            logging.error("Column 'phone_number' not found in Excel file.")
            return set()
        return set(df["phone_number"].astype(str).str.strip().tolist())
    except Exception as e:
        logging.error(f"Error loading phone numbers: {e}")
        return set()

def load_used_numbers():
    if not os.path.exists("used_numbers.txt"):
        return set()
    try:
        with open("used_numbers.txt", "r") as f:
            return set(line.strip() for line in f.readlines())
    except Exception as e:
        logging.warning(f"Error reading used numbers: {e}")
        return set()

def mark_as_used(number):
    with open("used_numbers.txt", "a") as f:
        f.write(f"{number}\n")

# --- Dynamic Token Extraction ---

def extract_tokens_and_cookies(session):
    try:
        logging.info("Fetching initial page to extract dynamic tokens...")
        res = session.get(UBER_LOGIN_URL.strip(), headers=HEADERS)
        res.raise_for_status()

        # Extract marketing visitor ID from Set-Cookie header
        marketing_id = None
        for cookie in res.headers.get("Set-Cookie", []):
            if "marketing_vistor_id=" in cookie:
                marketing_id = cookie.split("marketing_vistor_id=")[1].split(";")[0]

        # Extract analytics session ID from response text
        analytics_session_id = re.search(r'"X-Uber-Analytics-Session-Id":"([^"]+)"', res.text)
        analytics_session_id = analytics_session_id.group(1) if analytics_session_id else None

        # Extract XSRF Token from cookies
        xsrf_token = session.cookies.get("XSRF-TOKEN")

        return {
            "marketing_id": marketing_id,
            "analytics_session_id": analytics_session_id,
            "xsrf_token": xsrf_token
        }

    except Exception as e:
        logging.error(f"Error extracting tokens: {e}")
        return {}

# --- Submit Phone Number ---

def submit_to_uber(session, phone, tokens):
    full_number = COUNTRY_CODE + phone

    # Build dynamic headers using fresh tokens
    dynamic_headers = HEADERS.copy()
    dynamic_headers.update({
        "X-Csrf-Token": tokens["xsrf_token"] or "x",
        "X-Uber-Analytics-Session-Id": tokens["analytics_session_id"] or "fallback-id",
        "X-Uber-Marketing-Id": tokens["marketing_id"] or "fallback-marketing-id",
        "X-Uber-Challenge-Provider": "ARKOSE_TOKEN",
        "X-Uber-Challenge-Token": "65818426586360715.3227652504|r=ap-southeast-1|meta=3|metabgclr=transparent|metaiconclr=%23757575|guitextcolor=%23000000|pk=30000F36-CADF-490C-929A-C6A7DD8B33C4|at=40|sup=1|rid=90|ag=101|cdn_url=https%3A%2F%2Fuber-api.arkoselabs.com%2Fcdn%2Ffc|surl=https%3A%2F%2Fuber-api.arkoselabs.com|smurl=https%3A%2F%2Fuber-api.arkoselabs.com%2Fcdn%2Ffc%2Fassets%2Fstyle-manager",
        "X-Uber-Client-Name": "usl_desktop",
        "X-Uber-Request-Uuid": "bed3ea30-81c1-44ae-a14a-67db0ed53737",
        "X-Uber-Usl-Id": tokens["marketing_id"] or "fallback-marketing-id"
    })

    payload = {
        "phoneNumber": full_number,
        "nextUrl": "/login-redirect/..."  # You can update this based on real value
    }

    try:
        logging.info(f"Submitting: {full_number}")
        res = session.post(UBER_SUBMIT_URL.strip(), json=payload, headers=dynamic_headers, timeout=10)
        if res.status_code == 200:
            logging.info(f"[SUCCESS] Submitted: {full_number}")
            return True
        else:
            logging.warning(f"[FAILED] {full_number} | Status: {res.status_code}")
            logging.debug(res.text[:300])  # Show partial response
            return False
    except Exception as e:
        logging.error(f"[EXCEPTION] {full_number}: {e}")
        return False

# --- Main Automation Loop ---

def process_numbers(session):
    all_numbers = load_phone_numbers()
    used_numbers = load_used_numbers()
    new_numbers = sorted(all_numbers - used_numbers)

    if not new_numbers:
        logging.info("No new phone numbers found.")
        return

    logging.info(f"Found {len(new_numbers)} new number(s) to process.")

    tokens = extract_tokens_and_cookies(session)
    if not tokens:
        logging.error("Failed to extract required tokens. Skipping submission.")
        return

    for number in new_numbers:
        success = submit_to_uber(session, number, tokens)
        if success:
            mark_as_used(number)
        time.sleep(3)  # Rate limiting delay

def main():
    logging.info("Uber Phone Automation started.")
    logging.info("This script will run continuously and check for new phone numbers every minute.")

    session = requests.Session()

    while True:
        try:
            process_numbers(session)
            logging.info(f"Sleeping for {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logging.info("Shutting down gracefully...")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
