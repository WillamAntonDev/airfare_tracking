import os
import time
import requests
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
import schedule  # For scheduling the weekly email alerts

# Load environment variables
load_dotenv()

# API and Google credentials
API_KEY = os.getenv("API_KEY")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
DESTINATIONS = os.getenv("DESTINATIONS", "PMO,FCO,MXP,CTA")  # Add this for dynamic destinations
PRICE_THRESHOLD = 400  # Add this for price alerts (can be updated dynamically)

# Google Sheets setup
def setup_google_sheets():
    # Absolute path for credentials.json
    credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    client = gspread.authorize(credentials)
    return client.open("Flight Tracker").sheet1  # Ensure the Google Sheet is named "Flight Tracker"

# Fetch flight data from Kiwi API
def fetch_flight_data():
    print("Fetching flight data...")
    BASE_URL = "https://tequila-api.kiwi.com/v2/search"
    headers = {"apikey": API_KEY}
    params = {
        "fly_from": "CLT,RDU,IAD,JFK",  # Multiple origin airports
        "fly_to": DESTINATIONS,         # Dynamic destinations
        "date_from": "01/06/2025",
        "date_to": "30/06/2025",
        "limit": 10                     # Limit to 10 results
    }
    try:
        response = requests.get(BASE_URL, headers=headers, params=params)
        response.raise_for_status()
        flights = response.json().get("data", [])
        print(f"Fetched {len(flights)} flights.")
        return flights
    except requests.exceptions.RequestException as e:
        print(f"Error fetching flight data: {e}")
        return []

# Save data to Google Sheets
def save_to_google_sheets(flights, sheet):
    # Check if headers already exist
    existing_data = sheet.get_all_values()
    if not existing_data or existing_data[0] != ["Price (USD)", "Duration (Seconds)", "Origin", "Destination", "Departure Time", "Booking Link"]:
        headers = ["Price (USD)", "Duration (Seconds)", "Origin", "Destination", "Departure Time", "Booking Link"]
        sheet.insert_row(headers, index=1)  # Add headers to the first row

    # Append flight data rows
    for flight in flights:
        try:
            row = [
                flight["price"],
                flight["duration"]["departure"],  # Total departure duration in seconds
                flight["route"][0]["cityFrom"],
                flight["route"][0]["cityTo"],
                flight["route"][0]["local_departure"],
                flight["deep_link"]  # Booking link
            ]
            sheet.append_row(row)
        except KeyError as e:
            print(f"Missing key in flight data: {e}")
    print("Flight data saved to Google Sheets.")

# Send email notifications for price changes
def send_email_notification(subject, body):
    sender_email = "banton65@gmail.com"  # Replace with your email
    receiver_email = "banton65@gmail.com"  # Replace with your email
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, EMAIL_PASSWORD)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

# Main function to fetch flights and notify
def fetch_and_notify():
    print("Checking for flight deals...")
    sheet = setup_google_sheets()
    flights = fetch_flight_data()

    if flights:
        save_to_google_sheets(flights, sheet)

        for flight in flights:
            # Notify if price drops below threshold
            if flight["price"] < PRICE_THRESHOLD:
                subject = f"🔥 Flight Alert: ${flight['price']} - {flight['route'][0]['cityFrom']} to {flight['route'][0]['cityTo']}"
                body = f"""
                Great Deal!
                - Price: ${flight['price']}
                - From: {flight['route'][0]['cityFrom']} to {flight['route'][0]['cityTo']}
                - Departure: {flight['route'][0]['local_departure']}
                - Book here: {flight['deep_link']}
                """
                send_email_notification(subject, body)
            else:
                print(f"No flights under ${PRICE_THRESHOLD} found.")
    else:
        print("No flights available.")

# Schedule the script to run weekly
schedule.every().monday.at("08:00").do(fetch_and_notify)

if __name__ == "__main__":
    print("Starting flight tracker...")
    
    # Debug mode: run the task immediately
    DEBUG = True  # Set this to False for scheduled execution
    
    if DEBUG:
        print("Running fetch_and_notify immediately for debugging...")
        fetch_and_notify()
    else:
        while True:
            schedule.run_pending()
            time.sleep(1)  # Wait a second before checking the schedule again
