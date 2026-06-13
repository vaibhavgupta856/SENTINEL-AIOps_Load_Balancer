#!/usr/bin/env python3
import requests
import time
import sys
import threading

ORCHESTRATOR_URL = "http://localhost:8000"
SUBMIT_ENDPOINT = f"{ORCHESTRATOR_URL}/api/submit-job"

def submit_job(job_id):
    """Submit a job to the orchestrator"""
    payload = {
        "job_id": f"job-{job_id}",
        "task_name": f"compute-task-{job_id}",
        "estimated_duration": 15
    }
    try:
        response = requests.post(SUBMIT_ENDPOINT, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            assigned_node = data.get('assigned_node', 'unknown')
            node_load = data.get('node_load', 'unknown')
            print(f"Job {job_id:3d} -> {assigned_node:5s} ({node_load})")
            return True
        else:
            print(f"Job {job_id:3d} FAILED")
            return False
    except Exception as e:
        print(f"Job {job_id:3d} ERROR")
        return False

def main():
    print("Load Generator - High Volume Job Submission")
    print(f"Target: {ORCHESTRATOR_URL}")
    print("Submitting 5 concurrent jobs every 1 second...")
    print("Watch dashboard - nodes should show different CPU usage\n")
    
    job_counter = 1
    try:
        while True:
            threads = []
            for i in range(5):
                t = threading.Thread(target=submit_job, args=(job_counter,))
                threads.append(t)
                t.start()
                job_counter += 1
            
            for t in threads:
                t.join()
            
            print("---")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nLoad generator stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
