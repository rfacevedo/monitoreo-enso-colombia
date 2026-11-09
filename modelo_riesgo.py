"""Modelo indicativo de riesgo por lluvia (deslizamientos e inundaciones) y por déficit de lluvia para el piloto del Eje Cafetero.

IMPORTANTE: es un modelo sencillo y transparente para apoyar el monitoreo y la demostración; NO sustituye los boletines oficiales del
IDEAM (alertas por deslizamientos, seguimiento del ENOS), de la UNGRD ni del SGC. Los pesos y umbrales son una primera calibración
heredada de Ecuador y Perú y deben validarse con eventos reales (emergencias de la UNGRD). Autor y mentor: Raúl Acevedo.

Amenazas por lluvia (deslizamiento / inundación), 0 a 1:
    riesgo = w_lluvia · S_lluvia · (1 + k_Niña) + w_expo · S_expo + w_oficial · S_oficial

- S_lluvia: lluvia pronosticada (NOAA GFS por día; CFSv2 por mes) frente al clima PROPIO de cada municipio (``climatologia.json``). Para el
  día de hoy se toma el mayor entre el pronóstico y la lluvia OBSERVADA en las últimas 72 h por las estaciones automáticas del IDEAM.
- S_expo: exposición del terreno: pendiente (deslizamiento) o ribera de un río grande (inundación).
- S_oficial: nivel de la alerta por pronóstico de deslizamientos del IDEAM (BADT: alta 1, moderada 0,6, baja 0,25) para hoy y mañana.
  Si no hay alerta oficial vigente (fechas posteriores) el peso se reparte entre la lluvia y la exposición.
- k_Niña: hasta +15 % sobre la lluvia cuando el ONI es negativo (La Niña). Con El Niño no se amplifica: en Colombia suele llover menos.

Amenaza por DÉFICIT de lluvia (solo horizonte mensual CFSv2), 0 a 1:
    riesgo = 0,7 · S_déficit · (1 + 0,25 · El Niño) + 0,3 · El Niño
- S_déficit: cuánto queda la lluvia mensual pronosticada por debajo de la mediana del mismo mes (60 % por debajo = 1).
- El Niño: índice 0 a 1 según ONI y Niño 3.4 (NOAA CPC).

Cada fecha toma la amenaza de mayor riesgo y registra su tipo.
"""

import datetime
import json
import unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------------------------
# Catálogo de municipios piloto (cabecera municipal; elevación, pendiente y relieve del Copernicus DEM GLO-30). Los nombres de las claves
# («canton», «provincia») vienen del modelo de Ecuador: aquí «canton» = municipio y «provincia» = departamento.
# ----------------------------------------------------------------------------------------------
CANTONES = [
    {"canton": 'Manizales', "provincia": 'Caldas', "lat": 5.0689, "lon": -75.5174, "elevacion": 2124.0, "pendiente": 32.1, "relieve": 654.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17001'},
    {"canton": 'Villamaría', "provincia": 'Caldas', "lat": 5.0447, "lon": -75.5144, "elevacion": 1888.0, "pendiente": 31.3, "relieve": 783.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17873'},
    {"canton": 'Chinchiná', "provincia": 'Caldas', "lat": 4.9833, "lon": -75.6049, "elevacion": 1383.0, "pendiente": 31.6, "relieve": 1838.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17174'},
    {"canton": 'Palestina', "provincia": 'Caldas', "lat": 5.0167, "lon": -75.6167, "elevacion": 1476.0, "pendiente": 24.7, "relieve": 1617.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17524'},
    {"canton": 'Neira', "provincia": 'Caldas', "lat": 5.1667, "lon": -75.5167, "elevacion": 1926.0, "pendiente": 34.4, "relieve": 797.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17486'},
    {"canton": 'Aranzazu', "provincia": 'Caldas', "lat": 5.2667, "lon": -75.4833, "elevacion": 1951.0, "pendiente": 35.1, "relieve": 775.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17050'},
    {"canton": 'Salamina', "provincia": 'Caldas', "lat": 5.4064, "lon": -75.4881, "elevacion": 1791.0, "pendiente": 40.7, "relieve": 970.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17653'},
    {"canton": 'Riosucio', "provincia": 'Caldas', "lat": 5.4231, "lon": -75.7036, "elevacion": 1762.0, "pendiente": 36.3, "relieve": 1080.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17614'},
    {"canton": 'Anserma', "provincia": 'Caldas', "lat": 5.2325, "lon": -75.7867, "elevacion": 1786.0, "pendiente": 29.9, "relieve": 897.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17042'},
    {"canton": 'La Dorada', "provincia": 'Caldas', "lat": 5.45, "lon": -74.6667, "elevacion": 179.0, "pendiente": 15.2, "relieve": 140.0, "amenaza": 'inundacion', "ribera": True, "dane": '17380'},
    {"canton": 'Aguadas', "provincia": 'Caldas', "lat": 5.6167, "lon": -75.4569, "elevacion": 2083.0, "pendiente": 36.3, "relieve": 1233.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17013'},
    {"canton": 'Pácora', "provincia": 'Caldas', "lat": 5.5303, "lon": -75.4586, "elevacion": 1776.0, "pendiente": 31.3, "relieve": 959.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17513'},
    {"canton": 'Supía', "provincia": 'Caldas', "lat": 5.45, "lon": -75.65, "elevacion": 1161.0, "pendiente": 29.2, "relieve": 944.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17777'},
    {"canton": 'Pensilvania', "provincia": 'Caldas', "lat": 5.3856, "lon": -75.1594, "elevacion": 2034.0, "pendiente": 37.3, "relieve": 1260.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '17541'},
    {"canton": 'Pereira', "provincia": 'Risaralda', "lat": 4.8133, "lon": -75.6961, "elevacion": 1413.0, "pendiente": 23.4, "relieve": 512.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66001'},
    {"canton": 'Dosquebradas', "provincia": 'Risaralda', "lat": 4.8397, "lon": -75.6728, "elevacion": 1432.0, "pendiente": 23.6, "relieve": 527.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66170'},
    {"canton": 'Santa Rosa de Cabal', "provincia": 'Risaralda', "lat": 4.8687, "lon": -75.6217, "elevacion": 1691.0, "pendiente": 26.7, "relieve": 486.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66682'},
    {"canton": 'Marsella', "provincia": 'Risaralda', "lat": 4.9356, "lon": -75.7378, "elevacion": 1540.0, "pendiente": 32.2, "relieve": 774.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66440'},
    {"canton": 'La Virginia', "provincia": 'Risaralda', "lat": 4.8997, "lon": -75.8786, "elevacion": 906.0, "pendiente": 17.2, "relieve": 234.0, "amenaza": 'inundacion', "ribera": True, "dane": '66400'},
    {"canton": 'Belén de Umbría', "provincia": 'Risaralda', "lat": 5.2, "lon": -75.8667, "elevacion": 1535.0, "pendiente": 28.6, "relieve": 652.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66088'},
    {"canton": 'Apía', "provincia": 'Risaralda', "lat": 5.1042, "lon": -75.9422, "elevacion": 1603.0, "pendiente": 34.9, "relieve": 980.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66045'},
    {"canton": 'Quinchía', "provincia": 'Risaralda', "lat": 5.3394, "lon": -75.7347, "elevacion": 1878.0, "pendiente": 34.0, "relieve": 871.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66594'},
    {"canton": 'Pueblo Rico', "provincia": 'Risaralda', "lat": 5.2214, "lon": -76.0306, "elevacion": 1566.0, "pendiente": 38.5, "relieve": 1130.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66572'},
    {"canton": 'Santuario', "provincia": 'Risaralda', "lat": 5.0711, "lon": -75.965, "elevacion": 1509.0, "pendiente": 36.0, "relieve": 980.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '66687'},
    {"canton": 'Armenia', "provincia": 'Quindío', "lat": 4.5339, "lon": -75.6811, "elevacion": 1476.0, "pendiente": 20.7, "relieve": 256.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63001'},
    {"canton": 'Calarcá', "provincia": 'Quindío', "lat": 4.5292, "lon": -75.6428, "elevacion": 1530.0, "pendiente": 27.2, "relieve": 819.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63130'},
    {"canton": 'Montenegro', "provincia": 'Quindío', "lat": 4.5667, "lon": -75.75, "elevacion": 1295.0, "pendiente": 19.5, "relieve": 218.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63470'},
    {"canton": 'Quimbaya', "provincia": 'Quindío', "lat": 4.6247, "lon": -75.7631, "elevacion": 1310.0, "pendiente": 20.6, "relieve": 232.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63594'},
    {"canton": 'La Tebaida', "provincia": 'Quindío', "lat": 4.4528, "lon": -75.7894, "elevacion": 1195.0, "pendiente": 12.2, "relieve": 157.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63401'},
    {"canton": 'Circasia', "provincia": 'Quindío', "lat": 4.6178, "lon": -75.635, "elevacion": 1770.0, "pendiente": 24.8, "relieve": 405.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63190'},
    {"canton": 'Salento', "provincia": 'Quindío', "lat": 4.6372, "lon": -75.5714, "elevacion": 1972.0, "pendiente": 34.5, "relieve": 877.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63690'},
    {"canton": 'Filandia', "provincia": 'Quindío', "lat": 4.6753, "lon": -75.6603, "elevacion": 1881.0, "pendiente": 27.2, "relieve": 389.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63272'},
    {"canton": 'Pijao', "provincia": 'Quindío', "lat": 4.3342, "lon": -75.7003, "elevacion": 1682.0, "pendiente": 36.3, "relieve": 1356.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63548'},
    {"canton": 'Génova', "provincia": 'Quindío', "lat": 4.2058, "lon": -75.7906, "elevacion": 1453.0, "pendiente": 34.6, "relieve": 985.0, "amenaza": 'deslizamiento', "ribera": False, "dane": '63302'},
]

# ----------------------------------------------------------------------------------------------
# Parámetros del modelo (ajustables)
# ----------------------------------------------------------------------------------------------
PESOS_OFICIAL = {"lluvia": 0.45, "expo": 0.15, "oficial": 0.40}      # con alerta oficial vigente (BADT)
PESOS_SIN_OFICIAL = {"lluvia": 0.65, "expo": 0.20, "oficial": 0.0}   # sin alerta oficial: una lluvia extrema sola lleva a «alto riesgo»
LLUVIA_DIA_MM = 60.0          # umbrales de respaldo (sin climatologia.json)
LLUVIA_3DIAS_MM = 120.0
LLUVIA_MES_MM = 450.0
MES_FACTOR_SATURACION = 2.0   # CFSv2 mensual: el P95 vale 0,5 y se llega a 1 con el doble del exceso sobre la mediana
NINA_MAX_AMPLIFICACION = 0.15
DEFICIT_SATURA = 0.6          # lluvia mensual 60 % por debajo de la mediana = déficit máximo
DEFICIT_PESOS = {"deficit": 0.7, "enso": 0.3}
DEFICIT_AMPLIFICACION_ENSO = 0.25
ONI_SATURA = 2.0              # °C de ONI que saturan el índice ENSO
NINO34_SATURA = 3.0           # °C de anomalía en Niño 3.4 que saturan el índice ENSO
PENDIENTE_BAJA, PENDIENTE_ALTA = 10.0, 35.0     # °: exposición 0 y 1 en laderas
EXPOSICION_RIBERA = 0.8       # exposición fija de los municipios de ribera (inundación)
NIVEL_OFICIAL = {"ALTA": 1.0, "MODERADA": 0.6, "BAJA": 0.25}

# Umbrales de alerta (primera calibración, heredada de Ecuador y Perú; pendiente de validar con eventos del Eje Cafetero).
UMBRALES = {"critico": 0.85, "alto": 0.70, "amarilla": 0.50, "deslave_medio": 0.40}


def _cargar_climatologia():
    """Estadísticas locales de lluvia por municipio (si el archivo no existe, el modelo usa los umbrales de respaldo)."""
    try:
        with open(Path(__file__).with_name("climatologia.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


CLIMATOLOGIA = _cargar_climatologia()


def _tope(x, minimo=0.0, maximo=1.0):
    return max(minimo, min(maximo, x))


def _normalizar(valor, bajo, alto):
    """0 en ``bajo`` (lluvia típica) y 1 en ``alto`` (lluvia extrema), lineal entre ambos."""
    return _tope((valor - bajo) / (alto - bajo)) if alto > bajo else 0.0


def sin_tilde(texto):
    """Minúsculas, sin tildes ni espacios sobrantes (para comparar nombres de municipios de distintas fuentes)."""
    return " ".join("".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn").split())


def s_lluvia_dia(canton, dia_mm, acum3_mm, clima=None):
    """S_lluvia (0-1) de un día GFS: el mayor entre la lluvia del día y la acumulada en 3 días, frente al clima local."""
    est = (CLIMATOLOGIA if clima is None else clima).get("cantones", {}).get(canton["canton"])
    if est:
        return max(_normalizar(dia_mm, est["dia_p50"], est["dia_p99"]),
                   _normalizar(acum3_mm, est["d3_p50"], est["d3_p99"]))
    return _tope(max(dia_mm / LLUVIA_DIA_MM, acum3_mm / LLUVIA_3DIAS_MM))


def s_lluvia_observada(canton, mm_72h, clima=None):
    """S_lluvia (0-1) de la lluvia observada en 72 h frente al clima local de las sumas de 3 días."""
    est = (CLIMATOLOGIA if clima is None else clima).get("cantones", {}).get(canton["canton"])
    if est:
        return _normalizar(mm_72h, est["d3_p50"], est["d3_p99"])
    return _tope(mm_72h / LLUVIA_3DIAS_MM)


def s_lluvia_mes(canton, mes, mes_mm, clima=None):
    """S_lluvia (0-1) de un mes CFSv2 frente a la mediana y el percentil 95 del mismo mes del año en ese municipio."""
    est = ((CLIMATOLOGIA if clima is None else clima).get("cantones", {}).get(canton["canton"]) or {}).get("mes", {}).get(str(mes))
    if est:
        return _normalizar(mes_mm, est["p50"], est["p50"] + MES_FACTOR_SATURACION * (est["p95"] - est["p50"]))
    return _tope(mes_mm / LLUVIA_MES_MM)


def s_deficit_mes(canton, mes, mes_mm, clima=None):
    """S_déficit (0-1): cuánto queda el mes por debajo de la mediana del mismo mes (DEFICIT_SATURA = 60 % por debajo = 1)."""
    est = ((CLIMATOLOGIA if clima is None else clima).get("cantones", {}).get(canton["canton"]) or {}).get("mes", {}).get(str(mes))
    if not est or est["p50"] <= 0:
        return 0.0
    return _tope((est["p50"] - mes_mm) / (DEFICIT_SATURA * est["p50"]))


def indice_enso_firmado(oni, nino34):
    """Índice ENSO entre -1 (La Niña fuerte) y +1 (El Niño fuerte): promedio de ONI y Niño 3.4 semanal. Sin datos -> 0."""
    partes = []
    if oni is not None:
        partes.append(_tope(oni / ONI_SATURA, -1.0, 1.0))
    if nino34 is not None:
        partes.append(_tope(nino34 / NINO34_SATURA, -1.0, 1.0))
    return sum(partes) / len(partes) if partes else 0.0


def nivel_alerta(riesgo, amenaza=None):
    if riesgo >= UMBRALES["critico"]:
        return "CRÍTICO"
    if riesgo >= UMBRALES["alto"]:
        return "ALTO RIESGO"
    if riesgo >= UMBRALES["amarilla"]:
        return "ALERTA AMARILLA"
    if riesgo >= UMBRALES["deslave_medio"]:
        return "MEDIO"
    return "BAJO"


def nivel_badt(canton, badt):
    """Nivel de la alerta por deslizamientos del IDEAM (BADT) para el municipio: «ALTA», «MODERADA», «BAJA» o None."""
    if not badt or badt.get("_estado") == "error":
        return None
    clave = (sin_tilde(canton["provincia"]), sin_tilde(canton["canton"]))
    for nivel in ("ALTA", "MODERADA", "BAJA"):
        if clave in {(sin_tilde(d), sin_tilde(m)) for d, ms in (badt.get("niveles", {}).get(nivel) or {}).items() for m in ms}:
            return nivel
    return None


def s_exposicion(canton):
    if canton["amenaza"] == "inundacion":
        return EXPOSICION_RIBERA if canton.get("ribera") else _tope(1.0 - canton["pendiente"] / 25.0)
    return _tope((canton["pendiente"] - PENDIENTE_BAJA) / (PENDIENTE_ALTA - PENDIENTE_BAJA))


def calcular_riesgo(canton, s_lluvia, s_oficial, enso, hay_oficial=None):
    """Riesgo 0-1 por lluvia de un municipio (S_lluvia, S_oficial en 0-1; ``enso`` firmado: negativo = La Niña)."""
    hay = (s_oficial > 0) if hay_oficial is None else hay_oficial
    w = PESOS_OFICIAL if hay else PESOS_SIN_OFICIAL
    k_nina = NINA_MAX_AMPLIFICACION * max(0.0, -enso)
    s_ll = _tope(s_lluvia * (1.0 + k_nina))
    return _tope(w["lluvia"] * s_ll + w["expo"] * s_exposicion(canton) + w["oficial"] * s_oficial)


def calcular_riesgo_deficit(s_deficit, enso):
    """Riesgo 0-1 por déficit de lluvia (solo El Niño lo refuerza)."""
    nino = max(0.0, enso)
    return _tope(DEFICIT_PESOS["deficit"] * _tope(s_deficit * (1.0 + DEFICIT_AMPLIFICACION_ENSO * nino)) + DEFICIT_PESOS["enso"] * nino)


def construir_registros(datos, hoy=None):
    """Convierte las fuentes descargadas en registros por municipio y fecha (diarios GFS + mensuales CFSv2)."""
    hoy = hoy or datetime.date.today()
    noaa = datos.get("noaa") or {}
    oni = (noaa.get("oni") or {}).get("anomalia")
    nino34 = (noaa.get("semanal") or {}).get("nino34")
    enso = indice_enso_firmado(oni, nino34)
    badt = datos.get("badt")
    obs = ((datos.get("ideam_lluvia") or {}).get("municipios")) or {}

    gfs = (datos.get("gfs") or {}).get("cantones") or {}
    cfs = (datos.get("cfsv2") or {}).get("cantones") or {}
    registros = []
    for c in CANTONES:
        nivel = nivel_badt(c, badt)
        s_of = NIVEL_OFICIAL.get(nivel, 0.0)
        o = obs.get(c["canton"]) or obs.get(sin_tilde(c["canton"]))
        diaria = gfs.get(c["canton"], [])
        ultima_gfs = diaria[-1][0] if diaria else None
        mm = [v for _, v in diaria]
        for i, (fecha, dia_mm) in enumerate(diaria):
            acum3 = sum(mm[max(0, i - 2): i + 1])
            s_ll = s_lluvia_dia(c, dia_mm, acum3)
            vigente = hoy <= fecha <= hoy + datetime.timedelta(days=1)       # la alerta del IDEAM cubre hoy y mañana
            if fecha == hoy and o:
                s_ll = max(s_ll, s_lluvia_observada(c, o["mm_72h"]))
            r = calcular_riesgo(c, s_ll, s_of if vigente else 0.0, enso)
            registros.append(_fila(c, fecha, dia_mm, r, "GFS · día", "Inundación" if c["amenaza"] == "inundacion" else "Deslizamiento",
                                   s_of if vigente else 0.0, o["mm_72h"] if (fecha == hoy and o) else None))
        for ini, mes_mm in cfs.get(c["canton"], []):
            fecha = ini.replace(day=15)
            if ultima_gfs is not None and fecha <= ultima_gfs:
                continue                       # el detalle diario de GFS manda dentro de su horizonte
            if fecha < hoy:
                continue
            r_ll = calcular_riesgo(c, s_lluvia_mes(c, ini.month, mes_mm), 0.0, enso)
            r_def = calcular_riesgo_deficit(s_deficit_mes(c, ini.month, mes_mm), enso)
            if r_def > r_ll:
                registros.append(_fila(c, fecha, mes_mm, r_def, "CFSv2 · mes", "Déficit de lluvia", 0.0, None))
            else:
                registros.append(_fila(c, fecha, mes_mm, r_ll, "CFSv2 · mes", "Inundación" if c["amenaza"] == "inundacion" else "Deslizamiento", 0.0, None))
    return registros, enso


def _fila(c, fecha, lluvia_mm, riesgo, horizonte, tipo, oficial_idx, obs_mm):
    return {
        "canton": c["canton"], "provincia": c["provincia"], "elevacion": c["elevacion"],
        "lluvia_mm": round(lluvia_mm, 1), "oficial_idx": round(oficial_idx, 2), "obs_mm": None if obs_mm is None else round(obs_mm, 1),
        "riesgo": round(riesgo, 2), "alerta": nivel_alerta(riesgo), "tipo": tipo,
        "lat": c["lat"], "lon": c["lon"], "fecha": fecha, "horizonte": horizonte,
    }
