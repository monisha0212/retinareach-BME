# RetinaReach Report Generator

This directory contains the complete report generation module for the **RetinaReach AI-Powered Diabetic Retinopathy Screening Report**.

---

## 📁 Files in this folder

- **`generator.py`**: The core Python engine and data classes for constructing and styling the 2-page report.
- **`run.py`**: A quick script to generate a sample report.
- **`__init__.py`**: Allows importing as a standard Python module (`from report import generate_report_from_ai`).
- **`retinareach_screening_report.html`**: The generated 2-page print & PDF-ready HTML report.

---

## 🚀 How to Run

### 1. Generate Report from Terminal
```powershell
python report/run.py
```

### 2. Open in Browser
```powershell
Start-Process report/retinareach_screening_report.html
```

### 3. Save as PDF
Click the blue **"🖨️ Print / Save as PDF"** button at the top (or press `Ctrl + P`) and select **Save as PDF** (Paper size: A4).

---

## 🐍 Python Usage

```python
from report import generate_report_from_ai

# Generate report with custom AI results
report_path = generate_report_from_ai(
    od_image_path="path/to/od_fundus.jpg",   # Right eye image
    os_image_path="path/to/os_fundus.jpg",   # Left eye image (optional)
    ai_result_od={"top_class": "Mild NPDR", "microaneurysms": "72%"},
    ai_result_os={"top_class": "No DR", "microaneurysms": "18%"},
    patient_info={
        "name": "Lakshmi B",
        "age": 62,
        "gender": "Female",
        "phone": "9876543210"
    },
    output_html_path="report/my_report.html"
)
```
