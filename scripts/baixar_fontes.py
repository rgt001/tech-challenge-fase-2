"""Download pequeno de fontes fixadas; mantém SHA-256 e conteúdo original."""
from pathlib import Path
import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "d236a2ae6a08fefdb8ee9f1ca3f8201223a92da3"
FILES = ["LICENSE", "README.md", "genetic_algorithm.py", "tsp.py", "benchmark_att48.py",
         "draw_functions.py", "demo_crossover.py", "demo_mutation.py"]
BENCHMARKS = {"A-n32-k5": (4, 784), "A-n54-k7": (21, 1167), "A-n80-k10": (31, 1763)}


def main():
    records = []
    for name in FILES:
        url = f"https://raw.githubusercontent.com/FIAP/genetic_algorithm_tsp/{COMMIT}/{name}"
        target = ROOT / "data" / "sources" / "fiap" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = urllib.request.urlopen(url, timeout=45).read()
        target.write_bytes(data)
        records.append({"path": target.relative_to(ROOT).as_posix(), "url": url,
                        "sha256": hashlib.sha256(data).hexdigest(), "commit": COMMIT})
    repo_commit = json.loads(urllib.request.urlopen(
        'https://api.github.com/repos/vidalt/CVRPLIB/commits/main', timeout=45).read())["sha"]
    for name, (instance_id, optimum) in BENCHMARKS.items():
        url = f"https://galgos.inf.puc-rio.br/cvrplib/en/download/instance/{instance_id}"
        target = ROOT / "data" / "sources" / "cvrplib" / f"{name}.vrp"
        target.parent.mkdir(parents=True, exist_ok=True)
        retrieval_url = url
        try:
            data = urllib.request.urlopen(url, timeout=45).read()
        except urllib.error.URLError:
            # Espelho mantido por Thibaut Vidal; TLS continua sendo verificado.
            retrieval_url = f"https://raw.githubusercontent.com/vidalt/CVRPLIB/{repo_commit}/A/Instances/{name}.vrp"
            data = urllib.request.urlopen(retrieval_url, timeout=45).read()
        if not data.lstrip().startswith(b"NAME") or name.encode() not in data[:200]:
            raise ValueError(f"Resposta inesperada para {name}")
        target.write_bytes(data)
        records.append({"path": target.relative_to(ROOT).as_posix(), "url": url,
                        "retrieval_url": retrieval_url,
                        "sha256": hashlib.sha256(data).hexdigest(), "known_optimum": optimum,
                        "optimum_source": "https://galgos.inf.puc-rio.br/cvrplib/en/instances"})
        solution_url = f"https://raw.githubusercontent.com/vidalt/CVRPLIB/{repo_commit}/A/Solutions/{name}.sol"
        solution_data = urllib.request.urlopen(solution_url, timeout=45).read()
        solution_target = target.with_suffix('.sol')
        solution_target.write_bytes(solution_data)
        records.append({"path": solution_target.relative_to(ROOT).as_posix(), "url": solution_url,
                        "sha256": hashlib.sha256(solution_data).hexdigest()})
    manifest = ROOT / "data" / "sources" / "manifest.json"
    manifest.write_text(json.dumps({"retrieved_at": datetime.now(timezone.utc).isoformat(),
                                   "files": records}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Fontes preservadas: {len(records)} arquivos")


if __name__ == "__main__":
    main()
