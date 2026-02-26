import requests
import time
import sys
import json

# Configuration
SUBMIT_URL = "https://mineru.net/api/v4/extract/task"
RESULT_URL_TEMPLATE = "https://mineru.net/api/v4/extract/task/{}"
demo_url = "https://weiwo-rag.oss-cn-shanghai.aliyuncs.com/demo_pdf/%E6%94%B9%E9%80%A0%E5%90%88%E5%90%8C.pdf"
TOKEN = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI5ODEwMDc3MSIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc3MTkzNDg3NSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiMTg1MDI1MjM4MjciLCJvcGVuSWQiOm51bGwsInV1aWQiOiIyNDdiYTA0Ny01NDFlLTQ2YTItYTRmYi01MWVkZDE1ZDk4M2EiLCJlbWFpbCI6IiIsImV4cCI6MTc3OTcxMDg3NX0.7_d75l3AIOL9zXY91meDy15Xs8K9GBrZ1rIgpaSlrx3TzuRoKfuD2d5kjkywqhDt6NL_ZxDh1FhX4wqSYlWLXQ"


HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}"
}

def submit_task(file_url):
    """Submits a file URL for extraction."""
    print(f"Submitting task for URL: {file_url}")
    data = {
        "url": file_url,
        "model_version": "vlm"
    }
    
    try:
        response = requests.post(SUBMIT_URL, headers=HEADERS, json=data)
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") != 0: # Assuming 0 is success based on typical APIs, but need to check response structure
            # Actually, let's look at the raw response if we can, but based on typical usage:
            # The previous script printed res.json()["data"], so let's assume standard structure.
            pass
            
        print("Submission response:", json.dumps(result, ensure_ascii=False))
        return result.get("data") # This should contain the task_id
    except Exception as e:
        print(f"Error submitting task: {e}")
        return None

def get_task_status(task_id):
    """Checks the status of a task."""
    url = RESULT_URL_TEMPLATE.format(task_id)
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error checking status: {e}")
        return None

def main():
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    else:
        target_url = input("Please enter the file URL: ").strip()

    if not target_url:
        print("URL is required.")
        return

    # 1. Submit Task
    submission_data = submit_task(target_url)
    
    if not submission_data:
        print("Failed to submit task.")
        return

    # Extract task_id. The previous script didn't explicitly show the structure of 'data', 
    # but usually it's a dict containing an ID or just the ID string.
    # Let's handle both cases or inspect what we get.
    # Based on minerU.py printing res.json()["data"], let's assume data might be the ID or contain it.
    # However, get_task_result.py uses a hardcoded UUID. 
    # It is highly likely submission_data is the task_id string or a dict with "id".
    
    task_id = None
    if isinstance(submission_data, str):
        task_id = submission_data
    elif isinstance(submission_data, dict):
        task_id = submission_data.get("id") or submission_data.get("task_id")
    
    if not task_id:
        # Fallback: maybe the data itself is what we need if the API is simple
        # Let's print it and ask user or try to guess? 
        # Actually, let's assume it returns a generic object and we need to find the ID.
        # But for now, let's assume submission_data is the ID or contains "id".
        print(f"Could not extract task_id from: {submission_data}")
        # If the response 'data' is the ID directly (common in some APIs):
        task_id = str(submission_data)

    print(f"Task ID: {task_id}")

    # 2. Poll for Result
    print("Polling for results...")
    start_time = time.time()
    while True:
        result = get_task_status(task_id)
        if not result:
            time.sleep(2)
            continue
            
        data = result.get("data", {})
        status = data.get("state") or data.get("status")
        
        # If we can't find status in data, maybe it's at root?
        if not status:
             status = result.get("state") or result.get("status")

        elapsed = int(time.time() - start_time)
        print(f"\rStatus: {status} (Elapsed: {elapsed}s)", end="", flush=True)

        if status in ["done", "success", "completed", "succeeded"]:
            print("\n\n=== Task Completed ===")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            break
        elif status in ["failed", "error"]:
            print("\n\n=== Task Failed ===")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            break
        
        time.sleep(2)

if __name__ == "__main__":
    main()
