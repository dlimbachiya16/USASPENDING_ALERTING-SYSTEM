import requests
import json
import os
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen_awards.json"
MIN_AMOUNT = 5_000_000

# Each tuple: (list of type codes, sort field)
AWARD_TYPE_GROUPS = [
    (["A", "B", "C", "D"],                                                              "Award Amount"),  # contracts
    (["02", "03", "04", "05"],                                                           "Award Amount"),  # grants
    (["06", "10"],                                                                       "Award Amount"),  # other financial assistance
    (["09", "11", "-1"],                                                                 "Award Amount"),  # direct payments
    (["07", "08"],                                                                       "Last Modified Date"),  # loans (Amount not supported)
    (["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"],  "Award Amount"),  # idvs
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

def fetch_awards_for_group(type_codes, sort_field):
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    date_start = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    date_end = datetime.utcnow().strftime("%Y-%m-%d")

    payload = {
        "filters": {
            "award_type_codes": type_codes,
            "time_period": [
                {
                    "start_date": "2026-01-01",
                    "end_date": date_end
                }
            ],
            "award_amounts": [
                {
                    "lower_bound": MIN_AMOUNT
                }
            ]
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Award Type",
            "Description",
            "Start Date",
            "Place of Performance State Code",
            "Place of Performance Country Code"
        ],
        "sort": sort_field,
        "order": "desc",
        "limit": 100,
        "page": 1
    }

    all_awards = []
    while True:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"API error for {type_codes}: {resp.status_code} {resp.text[:300]}")
            break
        data = resp.json()
        results = data.get("results", [])
        all_awards.extend(results)
        if len(results) < payload["limit"]:
            break
        payload["page"] += 1

    return all_awards

def fetch_all_awards():
    all_awards = []
    for type_codes, sort_field in AWARD_TYPE_GROUPS:
        print(f"Fetching group: {type_codes}")
        awards = fetch_awards_for_group(type_codes, sort_field)
        print(f"  Got {len(awards)} awards")
        all_awards.extend(awards)
    return all_awards

def format_amount(amount):
    if amount is None:
        return "N/A"
    if amount >= 1_000_000_000:
        return f"${amount/1_000_000_000:.2f}B"
    return f"${amount/1_000_000:.2f}M"

def main():
    seen = load_seen()
    awards = fetch_all_awards()
    new_seen = set(seen)
    alerts_sent = 0

    for award in awards:
        award_id = award.get("Award ID")
        if not award_id or award_id in seen:
            continue

        amount = award.get("Award Amount") or 0
        if amount < MIN_AMOUNT:
            continue

        new_seen.add(award_id)

        recipient = award.get("Recipient Name") or "Unknown Recipient"
        agency = award.get("Awarding Agency") or "Unknown Agency"
        sub_agency = award.get("Awarding Sub Agency") or ""
        award_type = award.get("Award Type") or "Unknown Type"
        description = award.get("Description") or "No description"
        start_date = award.get("Start Date") or "N/A"
        state = award.get("Place of Performance State Code") or ""
        country = award.get("Place of Performance Country Code") or ""
        location = f"{state}, {country}".strip(", ") if state or country else "N/A"

        if len(description) > 120:
            description = description[:117] + "..."

        message = (
            f"🏛 <b>NEW GOV AWARD &gt; $5M</b>\n\n"
            f"💰 <b>Amount:</b> {format_amount(amount)}\n"
            f"🏢 <b>Recipient:</b> {recipient}\n"
            f"🏦 <b>Agency:</b> {agency}\n"
            f"📁 <b>Sub-Agency:</b> {sub_agency}\n"
            f"📋 <b>Type:</b> {award_type}\n"
            f"📝 <b>Desc:</b> {description}\n"
            f"📅 <b>Start Date:</b> {start_date}\n"
            f"📍 <b>Location:</b> {location}\n"
            f"🔗 <b>ID:</b> {award_id}"
        )

        send_telegram(message)
        alerts_sent += 1
        print(f"Sent alert for {award_id}: {recipient} {format_amount(amount)}")

    save_seen(new_seen)
    print(f"Done. {alerts_sent} new alerts sent. Total seen: {len(new_seen)}")

if __name__ == "__main__":
    main()
