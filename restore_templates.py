import zipfile
import os
import sys

log_file = 'restore_log.txt'

def log(message):
    with open(log_file, 'a') as f:
        f.write(message + '\n')
    print(message)

try:
    log("Starting extraction...")
    zip_path = 'templates.zip'
    extract_to = 'templates'
    
    if not os.path.exists(zip_path):
        log(f"Error: {zip_path} not found.")
        sys.exit(1)
        
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
        log(f"Created directory: {extract_to}")
        
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
        log(f"Extracted {len(zip_ref.namelist())} files into {extract_to}")
        for name in zip_ref.namelist():
            log(f" - {name}")
            
    log("Extraction complete.")
except Exception as e:
    log(f"Critical Error: {str(e)}")
