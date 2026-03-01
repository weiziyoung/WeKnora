import time
import subprocess
import logging
import sys
import os
import signal
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Scheduler] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler()
    ]
)

class ScheduledTask:
    def __init__(self, script_path, interval_seconds, name):
        self.script_path = script_path
        self.interval_seconds = interval_seconds
        self.name = name
        self.last_run_time = 0
        self.process = None

    def is_running(self):
        if self.process is None:
            return False
        
        # Check if process is still running
        poll_result = self.process.poll()
        if poll_result is None:
            return True
        else:
            # Process finished
            if self.process.returncode != 0:
                logging.error(f"Task '{self.name}' finished with error code {self.process.returncode}")
            else:
                logging.info(f"Task '{self.name}' finished successfully.")
            self.process = None
            return False

    def run_if_needed(self):
        current_time = time.time()
        
        # Check if currently running
        if self.is_running():
            # logging.debug(f"Task '{self.name}' is still running. Skipping.")
            return

        # Check if it's time to run
        if current_time - self.last_run_time >= self.interval_seconds:
            logging.info(f"Starting task '{self.name}'...")
            try:
                # Use the same python interpreter as the scheduler
                self.process = subprocess.Popen([sys.executable, self.script_path])
                self.last_run_time = current_time
            except Exception as e:
                logging.error(f"Failed to start task '{self.name}': {e}")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define tasks
    tasks = [
        ScheduledTask(
            script_path=os.path.join(base_dir, "discover_files.py"),
            interval_seconds=600,  # 10 minutes
            name="Discover Files"
        ),
        ScheduledTask(
            script_path=os.path.join(base_dir, "submit_task.py"),
            interval_seconds=120,  # 2 minutes
            name="Submit Task"
        ),
        ScheduledTask(
            script_path=os.path.join(base_dir, "polling_task.py"),
            interval_seconds=120,  # 2 minutes
            name="Polling Task"
        )
    ]

    logging.info("Scheduler started. Press Ctrl+C to stop.")
    
    try:
        while True:
            for task in tasks:
                task.run_if_needed()
            
            # Check every 1 second
            time.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("Scheduler stopping...")
        # Terminate running processes
        for task in tasks:
            if task.process and task.process.poll() is None:
                logging.info(f"Terminating task '{task.name}'...")
                task.process.terminate()
                try:
                    task.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    task.process.kill()
        logging.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
