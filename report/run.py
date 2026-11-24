import os
import sys
from pathlib import Path

# Add current folder and root to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from generator import generate_report_from_ai

if __name__ == "__main__":
    output_path = CURRENT_DIR / "retinareach_screening_report.html"
    print("=" * 60)
    print("Generating RetinaReach AI Screening Report...")
    print("=" * 60)
    
    generated_file = generate_report_from_ai(
        od_image_path=None,  # Or provide path to your fundus image
        os_image_path=None,
        ai_result_od={
            "top_class": "Mild NPDR",
            "microaneurysms": "72%",
            "hemorrhages": "64%",
            "exudates": "48%",
            "macular_involvement": "36%",
            "vessel_abnormalities": "22%"
        },
        ai_result_os={
            "top_class": "No DR",
            "microaneurysms": "18%",
            "hemorrhages": "12%",
            "exudates": "8%",
            "macular_involvement": "5%",
            "vessel_abnormalities": "6%"
        },
        patient_info={
            "name": "Lakshmi B",
            "age": 62,
            "gender": "Female",
            "phone": "9876543210",
            "address": "12, East Street, Vellore Village, Tiruvannamalai District - 606601"
        },
        output_html_path=str(output_path)
    )
    
    print("\n[DONE] You can open the generated report in your browser:")
    print(f"File: {generated_file}")
    print("\nTip: Press Ctrl+P or click 'Print / Save as PDF' to save as a 2-page A4 PDF.")
