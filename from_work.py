import json
import os
import urllib3

http = urllib3.PoolManager()

API_URL = "https://api-prod-0.sophia-app.com/api/services/search/keyword-search"

def build_payload(
    phrase: str,
    latitude: float,
    longitude: float,
    location_values=None
):
    if location_values is None:
        location_values = ["United States", "North Carolina", "Cumberland", "Fayetteville", "28301"]

    return {
        "payload": {
            "type": "keyword-search",
            "phrase": phrase,
            "searchLocationFilter": {
                "fieldToSearch": "service.serviceAreas.searchLocation.keyword",
                "values": location_values
            },
            "order": "relevance",
            "filtersApplied": [],
            "filterButtons": [
                {
                    "name": "languages",
                    "label": "Languages Offered",
                    "insideShowMoreFilters": False,
                    "displayOrder": 1,
                    "aggregationDetails": [
                        {
                            "aggregationName": "serviceLanguages",
                            "fieldToSearch": "service.languages.languageName.keyword"
                        },
                        {
                            "aggregationName": "locationLanguages",
                            "fieldToSearch": "location.languages.languageName.keyword"
                        }
                    ],
                    "excludeInOptions": ["No additional information provided"]
                },
                {
                    "name": "feeType",
                    "label": "Fee Type",
                    "insideShowMoreFilters": False,
                    "displayOrder": 3,
                    "aggregationDetails": [
                        {
                            "aggregationName": "feeType",
                            "fieldToSearch": "service.feeType.name.keyword"
                        }
                    ],
                    "excludeInOptions": []
                }
            ]
        }
    }


def lambda_handler(event, context):
    print("Received event: " + json.dumps(event))
    print(event["body"])
    
    e = json.loads(event["body"])
    # Generate a unique RequestId
    
    # Extract fields from event
    """
    Event example:
    {
      "phrase": "food",
      "latitude": 35.052062,
      "longitude": -78.878573,
      "location_values": ["United States","North Carolina","Cumberland","Fayetteville","28301"]
    }
    """
    
    phrase = e.get("Phrase")
    
    location_values =  [e.get("Country"),e.get("State"),e.get("County"),e.get("City"),e.get("zipCode")]
    latitude= 35.052062
    longitude= -78.878573
    tenant = os.environ.get("SOPHIA_TENANT", "sc-prod-0")
    origin = os.environ.get("SOPHIA_ORIGIN", "https://www.sc211.org")
    print(latitude,longitude,phrase,location_values)
    body_dict = build_payload(
        phrase=phrase,
        latitude=latitude,
        longitude=longitude,
        location_values=location_values
    )
    body_bytes = json.dumps(body_dict).encode("utf-8")
    print(body_bytes)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Tenant": tenant,
        "Origin": origin,
        # Optional but sometimes helpful:
        # "Referer": origin + "/",
        # If the API truly requires cookies (often it doesn't for pure API calls), add:
        # "Cookie": os.environ.get("SOPHIA_COOKIE", ""),
    }

    try:
        resp = http.request(
            "POST",
            API_URL,
            body=body_bytes,
            headers=headers,
            timeout=urllib3.Timeout(connect=5.0, read=25.0),
            retries=False,
        )

        # Decode response safely
        resp_text = resp.data.decode("utf-8", errors="replace")

        # Try JSON parse
        try:
            resp_json = json.loads(resp_text)
            print(resp_json)
        except json.JSONDecodeError:
            resp_json = {"raw": resp_text}

        return {
            "statusCode": resp.status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "upstream_status": resp.status,
                "response": resp_json
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": "Lambda request failed",
                "detail": str(e)
            })
        }