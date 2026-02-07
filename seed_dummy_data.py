import requests
import json
import random
from datetime import datetime, timedelta

base_url = "http://localhost:8000/internal-api"

def seed_data():
    print("Starting data seeding...")

    # 1. Seed Cases
    cases = []
    statuses = ["Open", "Negotiation", "Settled", "Closed", "Litigation"]
    first_names = ["John", "Jane", "Michael", "Sarah", "Robert", "Linda", "William", "Elizabeth", "David", "James"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

    for i in range(1, 11):
        case_id = f"CASE-{1000 + i}"
        patient_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        status = random.choice(statuses)
        fees = round(random.uniform(1000, 5000), 2)
        savings = round(random.uniform(500, 2000), 2)
        revenue = round(random.uniform(5000, 20000), 2)
        
        case_payload = {
            "id": case_id,
            "patient_name": patient_name,
            "status": status,
            "fees_taken": fees,
            "savings": savings,
            "revenue": revenue,
            "emails_received": random.randint(5, 50),
            "emails_sent": random.randint(5, 40)
        }
        
        print(f"Creating case {case_id}...")
        res = requests.post(f"{base_url}/cases", json=case_payload)
        if res.status_code == 200:
            cases.append(case_id)
        else:
            print(f"Failed to create case: {res.text}")

    if not cases:
        print("No cases created. Aborting.")
        return

    # 2. Seed Negotiations
    neg_types = ["Initial Demand", "Counter Offer", "Final Demand", "Settlement Offer"]
    insurance_cos = ["State Farm", "Geico", "Progressive", "Allstate", "Liberty Mutual"]
    results = ["Pending", "Accepted", "Rejected", "Countered"]

    for case_id in cases:
        for _ in range(random.randint(1, 3)):
            actual = round(random.uniform(5000, 50000), 2)
            offered = round(actual * random.uniform(0.3, 0.7), 2)
            
            neg_payload = {
                "case_id": case_id,
                "negotiation_type": random.choice(neg_types),
                "to": random.choice(insurance_cos),
                "email_body": f"Please see our demand for case {case_id}. We are seeking policy limits based on the attached medical records.",
                "date": (datetime.now() - timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d"),
                "actual_bill": actual,
                "offered_bill": offered,
                "sent_by_us": random.choice([True, False]),
                "result": random.choice(results)
            }
            print(f"Adding negotiation for {case_id}...")
            requests.post(f"{base_url}/negotiations", json=neg_payload)

    # 3. Seed Classifications
    for case_id in cases:
        cls_payload = {
            "case_id": case_id,
            "ocr_performed": random.choice([True, False]),
            "number_of_documents": random.randint(1, 10),
            "confidence": round(random.uniform(0.8, 0.99), 2)
        }
        print(f"Adding classification for {case_id}...")
        requests.post(f"{base_url}/classifications", json=cls_payload)

    # 4. Seed Reminders
    for case_id in cases:
        for i in range(1, 3):
            rem_payload = {
                "case_id": case_id,
                "reminder_number": i,
                "reminder_date": (datetime.now() + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
                "reminder_email_body": f"Reminder {i}: Follow up on case {case_id} documents."
            }
            print(f"Adding reminder for {case_id}...")
            requests.post(f"{base_url}/reminders", json=rem_payload)

    # 5. Seed Token Usage (via Turso instance if possible, but let's try endpoint)
    # The endpoint /internal-api/token_usage is GET only. 
    # We might need to add a POST endpoint for token usage if we want to seed it via API.
    # For now, let's skip or add it.

    print("\nSeeding completed successfully!")

if __name__ == "__main__":
    seed_data()
