"""Concordância entre registros, relatório, notebooks e README; sem executar LLM."""
import hashlib
import json
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import nbformat
from rotas_medicas.config import PROJECT_ROOT,OUTPUT_ROOT
from rotas_medicas.storage import write_json,utc_now

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
analysis_path=OUTPUT_ROOT/"analysis/summary.json"
analysis=json.loads(analysis_path.read_text(encoding="utf-8"))
report_data=json.loads((OUTPUT_ROOT/"analysis/report-data.json").read_text(encoding="utf-8"))
docx=PROJECT_ROOT/report_data["path"]
with ZipFile(docx) as archive:
    xml=ET.fromstring(archive.read("word/document.xml"))
    doc_text=" ".join(t.text or "" for t in xml.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
readme=(PROJECT_ROOT/"README.md").read_text(encoding="utf-8")
checks=[{"name":"table_hash","passed":analysis["results_sha256"]==digest(OUTPUT_ROOT/"experiments/results.csv")},
        {"name":"docx_hash","passed":report_data["sha256"]==digest(docx)},
        {"name":"report_analysis_hash","passed":report_data["analysis_sha256"]==digest(analysis_path)},
        {"name":"numeric_text_in_docx","passed":all(v in doc_text for v in report_data["required_numeric_text"])},
        {"name":"readme_table_hash","passed":analysis["results_sha256"] in readme}]
artifacts=[{"path":p.relative_to(PROJECT_ROOT).as_posix(),"sha256":digest(p)} for p in [docx,PROJECT_ROOT/"README.md",analysis_path]]
for path in sorted((PROJECT_ROOT/"notebooks").glob("*.ipynb")):
    nb=nbformat.read(path,as_version=4)
    stream="\n".join(o.get("text","") for c in nb.cells if c.cell_type=="code" for o in c.get("outputs",[]) if o.output_type=="stream")
    checks.append({"name":path.name+"_table_hash","passed":analysis["results_sha256"] in stream})
    checks.append({"name":path.name+"_no_error","passed":not any(o.output_type=="error" for c in nb.cells if c.cell_type=="code" for o in c.get("outputs",[]))})
    artifacts.append({"path":path.relative_to(PROJECT_ROOT).as_posix(),"sha256":digest(path)})
report={"status":"aprovado" if all(c["passed"] for c in checks) else "falhou","created_at":utc_now(),"checks":checks,"artifacts":artifacts,"results_sha256":analysis["results_sha256"]}
write_json(OUTPUT_ROOT/"validation/consistency.json",report)
print(report["status"],checks)
raise SystemExit(0 if report["status"]=="aprovado" else 1)
