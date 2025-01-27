import os
import time
import requests
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from gspread_formatting import CellFormat, Color, format_cell_range, TextFormat
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
    destinations = "PMO, CTA, FCO, MXP"
    params = {
        "fly_from": "CLT,RDU,IAD,JFK",  # Multiple origin airports
        "fly_to": destinations,         # Dynamic destinations
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
    # List of preferred destination cities
    preferred_destinations = ["Palermo", "Catania", "Rome", "Milan"]

    # Filter flights for preferred destinations
    filtered_flights = [
        flight for flight in flights
        if flight["route"][0]["cityTo"] in preferred_destinations
    ]

    # Check if headers already exist
    existing_data = sheet.get_all_values()
    if not existing_data or existing_data[0] != ["Price (USD)", "Duration", "Origin", "Destination", "Departure Time", "Booking Link"]:
        headers = ["Price (USD)", "Duration", "Origin", "Destination", "Departure Time", "Booking Link"]
        sheet.insert_row(headers, index=1)  # Add headers to the first row

    # Append filtered flight data rows
    for flight in filtered_flights:
        try:
            # Convert seconds to hours and minutes
            duration_seconds = flight["duration"]["departure"]
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            formatted_duration = f"{hours}h {minutes}m"
            
            # Format the departure time
            departure_time_utc = flight["route"][0]["utc_departure"]
            departure_time_local = datetime.strptime(departure_time_utc, "%Y-%m-%dT%H:%M:%S.%fZ").strftime('%Y-%m-%d %H:%M')

            # Simplify the booking link
            deep_link = flight["deep_link"]
            booking_link = f'=HYPERLINK("{deep_link}", "Book Now")'

            # Create the row
            row = [
                f"${flight['price']}" if "price" in flight else "N/A",  # Add $ symbol
                formatted_duration,  # Format duration in hours and minutes
                flight["route"][0]["cityFrom"],
                flight["route"][0]["cityTo"],
                departure_time_local,  # Formatted departure time
                booking_link  # Simplified link
            ]

            # Append the row to the Google Sheet
            sheet.append_row(row, value_input_option="USER_ENTERED")  # Ensures formulas are interpreted
        except KeyError as e:
            print(f"Missing key in flight data: {e}")
    print(f"Filtered {len(filtered_flights)} flights saved to Google Sheets.")

# Send email notifications for price changes
def send_email_notification(subject, body, booking_url):
    sender_email = "banton65@gmail.com"  # Replace with your email
    receiver_email = "banton65@gmail.com"  # Replace with your email
    
    # Create an HTML email for better formatting
    html_body = f"""
    <html>
        <body>
            <p>{body}</p>
            <p>Book here: <a href="{booking_url}" target="_blank">Click Here to Book</a></p>
        </body>
    </html>
    """
    
    # MIMEText with HTML content
    msg = MIMEText(html_body, "html")
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

        
def format_google_sheet(sheet):
    # Header formatting (bold, centered)
    header_format = CellFormat(
        backgroundColor=Color(0.9, 0.9, 0.9),  # Light gray
        textFormat=TextFormat(bold=True, foregroundColor=Color(0, 0, 0))
    )
    format_cell_range(sheet, "A1:F1", header_format)

    # Body formatting (e.g., alternate row colors)
    body_format = CellFormat(
        backgroundColor=Color(1, 1, 1),  # White
        textFormat=TextFormat(foregroundColor=Color(0, 0, 0))
    )
    format_cell_range(sheet, "A2:F", body_format)

# Main function to fetch flights and notify
def fetch_and_notify():
    print("Checking for flight deals...")
    sheet = setup_google_sheets()
    flights = fetch_flight_data()

    if flights:
        save_to_google_sheets(flights, sheet)
        format_google_sheet(sheet)

        has_deals = False  # Track if any flight meets the price threshold
        for flight in flights:
            # Notify if price drops below threshold
            if flight["price"] < PRICE_THRESHOLD:
                has_deals = True
                subject = f"🔥 Flight Alert: ${flight['price']} - {flight['route'][0]['cityFrom']} to {flight['route'][0]['cityTo']}"
                body = f"""
                Great Deal!
                - Price: ${flight['price']}
                - From: {flight['route'][0]['cityFrom']} to {flight['route'][0]['cityTo']}
                - Departure: {flight['route'][0]['local_departure']}
                """
                send_email_notification(subject, body, flight["deep_link"])

        if not has_deals:
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
