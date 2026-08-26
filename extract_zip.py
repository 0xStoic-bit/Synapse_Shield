import zipfile
import os
import shutil

zip_path = r"C:\Users\musta\Downloads\stitch_synapse_shield_cybersecurity_hub.zip"
target_dir = r"c:\Users\musta\Desktop\Synapse_Shield\static"
target_file = os.path.join(target_dir, "index.html")

print(f"Opening zip: {zip_path}")
if not os.path.exists(zip_path):
    print("Zip file not found!")
    exit(1)

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    files = zip_ref.namelist()
    code_file = next((f for f in files if f.endswith("code.html")), None)
    
    if code_file:
        print(f"Extracting {code_file}...")
        # Extract member
        extracted_path = zip_ref.extract(code_file)
        # Ensure target directory exists
        os.makedirs(target_dir, exist_ok=True)
        # Move and overwrite target file
        shutil.move(extracted_path, target_file)
        
        # Clean up extracted folders if nested
        root_extracted = code_file.split('/')[0] if '/' in code_file else code_file
        if os.path.exists(root_extracted) and os.path.isdir(root_extracted):
            shutil.rmtree(root_extracted)
        elif os.path.exists(code_file) and os.path.isfile(code_file):
            os.remove(code_file)
            
        print(f"Successfully replaced index.html with contents of {code_file}")
    else:
        print("code.html was not found in the zip file!")
        print("Available files:", files)
