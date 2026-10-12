"""Executa cada notebook em kernel novo e preserva a evidência de todas as células."""
import hashlib
import sys
import nbformat
from nbclient import NotebookClient
from rotas_medicas.config import PROJECT_ROOT,OUTPUT_ROOT
from rotas_medicas.storage import write_json,utc_now

records=[]
for path in sorted((PROJECT_ROOT/"notebooks").glob("*.ipynb")):
    notebook=nbformat.read(path,as_version=4)
    client=NotebookClient(notebook,timeout=300,kernel_name="python3",resources={"metadata":{"path":str(PROJECT_ROOT)}})
    client.execute()
    nbformat.write(notebook,path)
    code=[c for c in notebook.cells if c.cell_type=="code"]
    errors=[o for c in code for o in c.get("outputs",[]) if o.output_type=="error"]
    passed=all(c.execution_count is not None for c in code) and not errors
    records.append({"path":path.relative_to(PROJECT_ROOT).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"code_cells":len(code),"all_executed":passed,"error_count":len(errors)})
    print(f"{path.name}: {len(code)} células executadas",flush=True)
report={"status":"aprovado" if len(records)==2 and all(r["all_executed"] for r in records) else "falhou","created_at":utc_now(),"artifacts":records,"kernel":"fresh python3 per notebook"}
write_json(OUTPUT_ROOT/"validation"/"notebooks.json",report)
raise SystemExit(0 if report["status"]=="aprovado" else 1)
