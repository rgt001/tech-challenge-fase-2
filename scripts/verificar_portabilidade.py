"""Ambiente novo e cópia em outra pasta; execução também fora da raiz da cópia."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from rotas_medicas.config import PROJECT_ROOT,OUTPUT_ROOT
from rotas_medicas.storage import write_json,utc_now

task=PROJECT_ROOT/".tools"/f"portability-{uuid.uuid4().hex[:8]}"
clone=task/"project"
clone.mkdir(parents=True)
for name in ["pyproject.toml","README.md",".gitignore","requirements-lock.txt"]:shutil.copy2(PROJECT_ROOT/name,clone/name)
for name in ["src","tests","data/sources/fiap","data/sources/cvrplib"]:
    shutil.copytree(PROJECT_ROOT/name,clone/name,ignore=shutil.ignore_patterns("__pycache__","*.egg-info"))
shutil.copy2(PROJECT_ROOT/"data/sources/manifest.json",clone/"data/sources/manifest.json")
(clone/"data/scenarios").mkdir(parents=True)
shutil.copy2(PROJECT_ROOT/"data/scenarios/sp_evaluation_12.json",clone/"data/scenarios/sp_evaluation_12.json")
environment=task/"venv"
subprocess.run([sys.executable,"-m","venv",str(environment)],check=True)
python=environment/("Scripts/python.exe" if sys.platform=="win32" else "bin/python")
log=[]
checks=[]
commands=[
    ("locked_install",[str(python),"-m","pip","install","-r",str(clone/"requirements-lock.txt"),"--disable-pip-version-check"],clone),
    ("editable_install_in_new_folder",[str(python),"-m","pip","install","-e",str(clone),"--no-deps","--disable-pip-version-check"],task),
    ("pip_check",[str(python),"-m","pip","check"],task),
    ("test_suite_in_copy",[str(python),"-m","pytest",str(clone/"tests"),"--junitxml",str(task/"tests.xml")],task),
    ("cli_outside_root",[str(python),"-m","rotas_medicas","otimizar","sp_evaluation_12","--avaliacoes","1000"],task),
]
for name,command,cwd in commands:
    print(name,flush=True)
    run=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding="utf-8",errors="replace")
    # Remover caminhos particulares do log que acompanhará a entrega.
    output=run.stdout+run.stderr
    for prefix,label in [(task,"<temporary>"),(PROJECT_ROOT,"<project>"),(Path(os.environ.get("USERPROFILE",str(Path.home()))),"<user>")]:
        for spelling in [str(prefix),prefix.as_posix()]:output=re.sub(re.escape(spelling),lambda _:label,output,flags=re.IGNORECASE)
    log.append(f"{name}\n{output}")
    checks.append({"name":name,"passed":run.returncode==0,"exit_code":run.returncode})
    if run.returncode!=0:break
solution_path=clone/"outputs/solutions/sp_evaluation_12_genetic_42.json"
if solution_path.exists():
    result=json.loads(solution_path.read_text(encoding="utf-8"))
    checks.append({"name":"copied_data_solution","passed":result["status"]=="feasible" and result["verification"]["valid"]})
folder=OUTPUT_ROOT/"validation"
(folder/"portability.log").write_text("\n".join(log),encoding="utf-8")
artifacts=[{"path":"requirements-lock.txt","sha256":hashlib.sha256((PROJECT_ROOT/"requirements-lock.txt").read_bytes()).hexdigest()},
           {"path":"pyproject.toml","sha256":hashlib.sha256((PROJECT_ROOT/"pyproject.toml").read_bytes()).hexdigest()}]
for p in sorted((PROJECT_ROOT/"src").rglob("*.py")):
    other=clone/p.relative_to(PROJECT_ROOT)
    checks.append({"name":p.relative_to(PROJECT_ROOT).as_posix(),"passed":other.read_bytes()==p.read_bytes()})
    artifacts.append({"path":p.relative_to(PROJECT_ROOT).as_posix(),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
report={"status":"aprovado" if len(checks)>=6 and all(c["passed"] for c in checks) else "falhou","created_at":utc_now(),"checks":checks,"artifacts":artifacts,
        "method":"new virtual environment, locked dependencies, copied source/data, tests and CLI launched outside repository root","platform":"Windows CPU Python 3.13","temporary":"ignored .tools workspace"}
write_json(folder/"portability.json",report)
print(report["status"])
raise SystemExit(0 if report["status"]=="aprovado" else 1)
