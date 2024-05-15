import json
import os
import time
import logging
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import schedule
import sys
import argparse
from dotenv import load_dotenv
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import requests

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    filename='logins.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger()

# Path to the JSON files
json_file_path = os.getenv('LOGIN_JSON', 'logins.json')
config_file_path = os.getenv('CONFIG_JSON', 'config.json')
screenshots_base_path = os.getenv('SCREENSHOTS_PATH', 'screenshots')

# Template for the JSON file
json_template = [
    {
        "url": "https://example.com/login",
        "username": "your_username",
        "password": "your_password",
        "expected_redirect_url": "https://example.com/dashboard",
        "stats_url": "https://example.com/stats",
        "site_name": "example"
    }
]

# Template for the config file
config_template = {
    "schedule": {
        "time": "14:30",
        "interval_days": 1,
        "enable_scheduling": True,
        "execute_on_start": True
    },
    "retention_policy": {
        "max_screenshots": 10,
        "retention_days": 30
    },
    "pushover": {
        "user_key": "your_pushover_user_key",
        "api_token": "your_pushover_api_token"
    }
}

# Function to send Pushover notification
def send_pushover_notification(message, title="Notification"):
    user_key = config['pushover']['user_key']
    api_token = config['pushover']['api_token']
    if user_key and api_token:
        data = {
            "token": api_token,
            "user": user_key,
            "message": message,
            "title": title
        }
        try:
            response = requests.post("https://api.pushover.net/1/messages.json", data=data)
            if response.status_code == 200:
                logger.info("Pushover notification sent successfully.")
            else:
                logger.error(f"Failed to send Pushover notification: {response.text}")
        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")

# Function to create a JSON file with a template if it doesn't exist
def create_json_if_not_exists(file_path, template):
    if not os.path.exists(file_path):
        with open(file_path, 'w') as jsonfile:
            json.dump(template, jsonfile, indent=4)
        logger.info(f"{file_path} created. Please update it with your details.")
        sys.exit()

# Function to find the first available element from a list of potential names
def find_element(driver, field_names):
    for name in field_names:
        try:
            element = driver.find_element(By.NAME, name)
            return element
        except:
            continue
    raise Exception(f"None of the expected elements found: {field_names}")

# Function to initialize the Chrome browser
def init_browser():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)

# Function to log in and take a screenshot
def login_and_screenshot(url, username, password, index, expected_redirect_url, stats_url, site_name):
    driver = init_browser()  # Initialize the Chrome driver
    try:
        # Open the login page
        driver.get(url)
        
        # Allow some time for the page to load
        time.sleep(2)
        
        # Locate the username and password fields and enter the login credentials
        username_field = find_element(driver, ["username", "user", "email", "login"])
        password_field = find_element(driver, ["password", "pass", "pwd"])
        
        username_field.send_keys(username)
        password_field.send_keys(password)
        
        # Submit the login form (adjust the method to match the actual form on the page)
        password_field.send_keys(Keys.RETURN)
        
        # Allow some time for the login process to complete
        time.sleep(5)
        
        # Verify if the login was successful by checking the current URL
        current_url = driver.current_url
        if expected_redirect_url not in current_url:
            logger.error(f"Login failed for {username} at {url}. Current URL: {current_url}")
            send_pushover_notification(f"Login failed for {username} at {url}.", "Login Failed")
            return
        
        # Navigate to the stats page
        driver.get(stats_url)
        
        # Allow some time for the stats page to load
        time.sleep(5)
        
        # Get the current time and date
        current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        
        # Create directory for site if it doesn't exist
        site_path = os.path.join(screenshots_base_path, site_name)
        if not os.path.exists(site_path):
            os.makedirs(site_path)
        
        # Construct the screenshot filename
        screenshot_path = os.path.join(site_path, f'screenshot_{current_time}_{index}.png')
        
        # Take a screenshot on the stats page
        driver.save_screenshot(screenshot_path)
        
        logger.info(f'Screenshot saved to {screenshot_path}')
        send_pushover_notification(f'Screenshot saved to {screenshot_path}', "Screenshot Taken")
    
    except Exception as e:
        logger.error(f"An error occurred for {username} at {url}: {e}")
        send_pushover_notification(f"An error occurred for {username} at {url}: {e}", "Error")
    
    finally:
        driver.quit()  # Close the browser after each login

# Function to read login credentials and perform login for each entry
def run_logins():
    with open(json_file_path, 'r') as jsonfile:
        logins = json.load(jsonfile)
        
        for index, login in enumerate(logins):
            url = login['url']
            username = login['username']
            password = login['password']
            expected_redirect_url = login['expected_redirect_url']
            stats_url = login['stats_url']
            site_name = login['site_name']
            login_and_screenshot(url, username, password, index, expected_redirect_url, stats_url, site_name)
            manage_screenshots(site_name)

# Function to manage screenshots based on the retention policy
def manage_screenshots(site_name):
    site_path = os.path.join(screenshots_base_path, site_name)
    if not os.path.exists(site_path):
        return
    
    screenshots = [os.path.join(site_path, f) for f in os.listdir(site_path) if f.startswith('screenshot_')]
    screenshots.sort(key=os.path.getctime)

    # Delete old screenshots if they exceed max_screenshots
    if len(screenshots) > config['retention_policy']['max_screenshots']:
        for f in screenshots[:-config['retention_policy']['max_screenshots']]:
            os.remove(f)
            logger.info(f"Deleted old screenshot: {f}")

    # Delete screenshots older than retention_days
    retention_period = timedelta(days=config['retention_policy']['retention_days'])
    for f in screenshots:
        file_time = datetime.fromtimestamp(os.path.getctime(f))
        if datetime.now() - file_time > retention_period:
            os.remove(f)
            logger.info(f"Deleted expired screenshot: {f}")

# Create the JSON file with a template if it doesn't exist
create_json_if_not_exists(json_file_path, json_template)
create_json_if_not_exists(config_file_path, config_template)

# Load the configuration file
with open(config_file_path, 'r') as configfile:
    config = json.load(configfile)

# Set up argument parser
parser = argparse.ArgumentParser(description='Automate logins and manage screenshots.')
parser.add_argument('--time', type=str, help='Schedule time in HH:MM format')
parser.add_argument('--interval_days', type=int, help='Interval in days between runs')
parser.add_argument('--enable_scheduling', type=bool, help='Enable or disable scheduling')
parser.add_argument('--execute_on_start', type=bool, help='Execute logins immediately on start')
parser.add_argument('--max_screenshots', type=int, help='Maximum number of screenshots to retain')
parser.add_argument('--retention_days', type=int, help='Number of days to retain screenshots')

args = parser.parse_args()

# Override config with command-line arguments if provided
if args.time:
    config['schedule']['time'] = args.time
if args.interval_days:
    config['schedule']['interval_days'] = args.interval_days
if args.enable_scheduling is not None:
    config['schedule']['enable_scheduling'] = args.enable_scheduling
if args.execute_on_start is not None:
    config['schedule']['execute_on_start'] = args.execute_on_start
if args.max_screenshots:
    config['retention_policy']['max_screenshots'] = args.max_screenshots
if args.retention_days:
    config['retention_policy']['retention_days'] = args.retention_days

# Get the schedule settings from the config file
schedule_time = config['schedule']['time']
interval_days = config['schedule']['interval_days']
enable_scheduling = config['schedule']['enable_scheduling']
execute_on_start = config['schedule']['execute_on_start']

# Execute logins immediately on start if enabled
if execute_on_start:
    run_logins()

# Schedule the task based on the interval if scheduling is enabled
if enable_scheduling:
    schedule.every(interval_days).days.at(schedule_time).do(run_logins)
    logger.info(f"Scheduled to run every {interval_days} days at {schedule_time}.")

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(1)
