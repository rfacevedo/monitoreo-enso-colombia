"""Genera los datos geográficos del piloto del Eje Cafetero (Caldas, Risaralda y Quindío).

Fuente: Servicio Geológico Colombiano (SGC), servicio ArcGIS «Mapa_Nacional_Amenaza_Mov_Masa_100K», capas de límites municipales
(capa 3, con código DANE) y departamentales (capa 2), https://srvags.sgc.gov.co/arcgis/rest/services . Los límites son los oficiales a
escala 1:100.000 (IGAC / DANE). Se simplifican con Douglas-Peucker.

Salidas:
- ``municipios_eje.py``: los 53 municipios para el buscador «Buscar Municipio».
- ``eje_perfil.py``: el contorno de los tres departamentos, siempre visible en el visor.

    python generar_municipios.py
"""

import json
import math

import requests

BASE = "https://srvags.sgc.gov.co/arcgis/rest/services/Mapa_Nacional_Amenaza_Mov_Masa_100K/Mapa_Nacional_Amenaza_Movimientos_Masa_100K/MapServer"
CODIGOS = ("17", "66", "63")                          # Caldas, Risaralda, Quindío
DEPARTAMENTOS = {"17": "Caldas", "66": "Risaralda", "63": "Quindío"}
TOLERANCIA = 0.003                                    # grados (~330 m)
ISLOTE_MIN = 0.01


def _consulta(capa, where, campos):
    r = requests.get(f"{BASE}/{capa}/query", timeout=240, params={
        "where": where, "outFields": campos, "returnGeometry": "true", "outSR": "4326", "f": "geojson"})
    r.raise_for_status()
    return r.json()["features"]


def area(anillo):
    return sum(anillo[i][0] * anillo[i + 1][1] - anillo[i + 1][0] * anillo[i][1] for i in range(len(anillo) - 1)) / 2


def centroide(anillo):
    a = area(anillo)
    if abs(a) < 1e-12:
        return [sum(p[0] for p in anillo) / len(anillo), sum(p[1] for p in anillo) / len(anillo)]
    cx = cy = 0.0
    for i in range(len(anillo) - 1):
        f = anillo[i][0] * anillo[i + 1][1] - anillo[i + 1][0] * anillo[i][1]
        cx += (anillo[i][0] + anillo[i + 1][0]) * f
        cy += (anillo[i][1] + anillo[i + 1][1]) * f
    return [cx / (6 * a), cy / (6 * a)]


def douglas_peucker(pts, tol):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norma = math.hypot(dx, dy)
    mejor, idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        d = (math.hypot(pts[i][0] - x1, pts[i][1] - y1) if norma == 0
             else abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / norma)
        if d > mejor:
            mejor, idx = d, i
    if mejor <= tol:
        return [pts[0], pts[-1]]
    return douglas_peucker(pts[: idx + 1], tol)[:-1] + douglas_peucker(pts[idx:], tol)


def plano(anillo, tol):
    """Anillo simplificado y plano [lon, lat, lon, lat, ...], sin repetir el primer punto (el visor cierra el contorno)."""
    s = douglas_peucker([[p[0], p[1]] for p in anillo], tol)
    if s[0] != s[-1]:
        s.append(s[0])
    return [round(v, 4) for x, y in s[:-1] for v in (x, y)] if len(s) >= 4 else None


def exteriores(geometria):
    """Anillos exteriores de un Polygon / MultiPolygon GeoJSON."""
    if geometria["type"] == "Polygon":
        return [geometria["coordinates"][0]]
    return [p[0] for p in geometria["coordinates"]]


CORRECCIONES = {"Dos Quebradas": "Dosquebradas", "Pijáo": "Pijao", "Pijao ": "Pijao"}      # el SGC escribe estos nombres distinto al DANE


def titulo(txt):
    menores = {"de", "del", "la", "las", "los", "el", "y"}
    p = txt.lower().split()
    return " ".join(w if (i and w in menores) else w.capitalize() for i, w in enumerate(p))


def main():
    donde = " OR ".join(f"CODIGO_DAN LIKE '{c}%'" for c in CODIGOS)
    salida = []
    for f in _consulta(3, donde, "DEPARTAMEN,MUNICIPIO,CODIGO_DAN"):
        a = f["properties"]
        anillos = exteriores(f["geometry"])
        grande = max(anillos, key=lambda r: abs(area(r)))
        planos = []
        for r in anillos:
            xs, ys = [p[0] for p in r], [p[1] for p in r]
            if max(max(xs) - min(xs), max(ys) - min(ys)) < ISLOTE_MIN and r is not grande:
                continue
            s = plano(r, TOLERANCIA)
            if s:
                planos.append(s)
        todos = [p for r in anillos for p in r]
        xs, ys = [p[0] for p in todos], [p[1] for p in todos]
        salida.append({"u": a["CODIGO_DAN"], "n": CORRECCIONES.get(a["MUNICIPIO"].strip(), a["MUNICIPIO"].strip()), "p": DEPARTAMENTOS[a["CODIGO_DAN"][:2]],
                       "c": [round(v, 4) for v in centroide(grande)],
                       "b": [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)], "r": planos})
    salida.sort(key=lambda m: m["u"])
    with open("municipios_eje.py", "w", encoding="utf-8") as fh:
        fh.write('"""Municipios de Caldas, Risaralda y Quindío para el buscador «Buscar Municipio».\n\n'
                 "Fuente: Servicio Geológico Colombiano (servicio ArcGIS del Mapa Nacional de Amenaza por Movimientos en Masa), límites\n"
                 "municipales oficiales 1:100.000 con código DANE. Contornos simplificados (Douglas-Peucker, 0,003°).\n"
                 'Campos: u = código DANE, n = municipio, p = departamento, c = centro [lon, lat], b = caja [oeste, sur, este, norte], r = contornos.\n"""\n\n')
        fh.write("MUNICIPIOS_EJE = " + json.dumps(salida, ensure_ascii=False, separators=(",", ":")) + "\n")
    perfil = []
    for f in _consulta(2, " OR ".join(f"COD_DEPARTAMENTO='{c}'" for c in CODIGOS), "DEPARTAMENTO,COD_DEPARTAMENTO"):
        for r in exteriores(f["geometry"]):
            s = plano(r, 0.006)
            if s:
                perfil.append(s)
    with open("eje_perfil.py", "w", encoding="utf-8") as fh:
        fh.write('"""Contorno de los departamentos de Caldas, Risaralda y Quindío (SGC, límites departamentales 1:100.000, simplificado)."""\n\n')
        fh.write("EJE_PERFIL = " + json.dumps(perfil, separators=(",", ":")) + "\n")
    print(len(salida), "municipios;", sum(len(m["r"]) for m in salida), "anillos;", len(perfil), "anillos en el perfil")


if __name__ == "__main__":
    main()
