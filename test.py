import requests

payload = {"faculty_name": "Andrea L Cherrington"}
resp = requests.post(
    "http://127.0.0.1:8000/fetch_scholar_by_name",
    json=payload
)
print(resp.status_code)
print(resp.json())