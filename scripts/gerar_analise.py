from rotas_medicas.analysis import make_analysis
report=make_analysis()
print(f"{len(report['figures'])} gráficos e {len(report['maps'])} mapas gerados a partir de {report['runs']} execuções.")
