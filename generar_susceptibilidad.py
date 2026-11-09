"""Genera la capa de SUSCEPTIBILIDAD a deslizamientos (proxy topográfico) del Eje Cafetero con datos reales.

Parte del análisis de mapas ponderado de los pilotos de Ecuador y Perú, pero para una región de montaña: lo que vuelve susceptible a una
ladera es la PENDIENTE y el RELIEVE local, no la cercanía al mar.

- Topografía: Copernicus DEM GLO-30 (ESA, 30 m), abierto en AWS (sin clave), remuestreado a ~92 m.
    * pendiente (°) con filtro de 3 × 3 celdas,
    * relieve local (altura sobre el punto más bajo en ~2 km).
- Índice = 0,75 · pendiente normalizada (10° = 0, 35° = 1) + 0,25 · relieve normalizado (100 m = 0, 400 m = 1).
- Clases: baja (< 0,35), media (0,35 a 0,65), alta (≥ 0,65).

Es un proxy topográfico: NO incluye geología, suelos, cobertura, lluvia ni inventario de deslizamientos. Para la amenaza oficial hay que ver el
Mapa Nacional de Amenaza por Movimientos en Masa del Servicio Geológico Colombiano (1:100.000).

Salidas: ``susceptibilidad_inundacion.tif`` / ``.png`` / ``.json`` (se conservan los nombres de los pilotos anteriores; la capa es de
deslizamientos). GeoTIFF EPSG:4326 con clases 1 = baja, 2 = media, 3 = alta; PNG RGBA para el visor.

    python generar_susceptibilidad.py
"""

import json
import math
import sys

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from PIL import Image
from scipy import ndimage

# Extensión: Eje Cafetero (Caldas, Risaralda y Quindío)
OESTE, SUR, ESTE, NORTE = -76.3, 4.0, -74.6, 5.85
PASO = 1.0 / 1200                             # grados (~92 m): 1200 px por tesela de 1° exactos (sin costuras)
URL_TESELA = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
              "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")

PENDIENTE_BAJA, PENDIENTE_ALTA = 10.0, 35.0
RELIEVE_BAJO, RELIEVE_ALTO = 100.0, 400.0
PESO_PENDIENTE, PESO_RELIEVE = 0.75, 0.25
UMBRAL_MEDIA, UMBRAL_ALTA = 0.35, 0.65
COLORES = {1: (34, 197, 94, 30), 2: (250, 204, 21, 140), 3: (220, 38, 38, 190)}   # RGBA por clase (baja, media, alta)


def leer_dem():
    ancho = int(round((ESTE - OESTE) / PASO))
    alto = int(round((NORTE - SUR) / PASO))
    dem = np.full((alto, ancho), np.nan, np.float32)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES", GDAL_HTTP_MAX_RETRY="4"):
        for lat in range(math.floor(SUR), math.ceil(NORTE)):
            for lon in range(math.floor(OESTE), math.ceil(ESTE)):
                url = URL_TESELA.format(ns="N" if lat >= 0 else "S", lat=abs(lat), ew="E" if lon >= 0 else "W", lon=abs(lon))
                try:
                    with rasterio.open(url) as ds:
                        n = int(round(1 / PASO))                # 1200
                        bloque = ds.read(1, out_shape=(n, n), resampling=Resampling.average)
                except Exception:          # tesela inexistente
                    continue
                f0 = int(round((NORTE - (lat + 1)) / PASO)); c0 = int(round((lon - OESTE) / PASO))
                f1, c1 = max(f0, 0), max(c0, 0)
                sub = bloque[f1 - f0: f1 - f0 + (alto - f1), c1 - c0: c1 - c0 + (ancho - c1)]
                h = min(sub.shape[0], alto - f1); w = min(sub.shape[1], ancho - c1)
                dem[f1:f1 + h, c1:c1 + w] = sub[:h, :w]
                print(f"  tesela {lat:+d},{lon:+d} ok", file=sys.stderr)
    return np.nan_to_num(dem, nan=0.0)


def calcular(dem):
    """Clases (1 baja, 2 media, 3 alta) e índice 0-1 de susceptibilidad topográfica a deslizamientos."""
    paso_m = PASO * 111_000.0
    gy, gx = np.gradient(ndimage.uniform_filter(dem, size=3), paso_m)
    pendiente = np.degrees(np.arctan(np.hypot(gx, gy)))
    relieve = dem - ndimage.minimum_filter(dem, size=21)                       # ~2 km
    s_pend = np.clip((pendiente - PENDIENTE_BAJA) / (PENDIENTE_ALTA - PENDIENTE_BAJA), 0, 1)
    s_rel = np.clip((relieve - RELIEVE_BAJO) / (RELIEVE_ALTO - RELIEVE_BAJO), 0, 1)
    indice = np.clip(PESO_PENDIENTE * s_pend + PESO_RELIEVE * s_rel, 0, 1)
    clases = np.where(indice >= UMBRAL_ALTA, 3, np.where(indice >= UMBRAL_MEDIA, 2, 1)).astype(np.uint8)
    return clases, indice, np.ones(dem.shape, bool)


def main():
    print("Leyendo el DEM Copernicus GLO-30 …", file=sys.stderr)
    dem = leer_dem()
    clases, indice, tierra = calcular(dem)
    alto, ancho = clases.shape
    transform = from_origin(OESTE, NORTE, PASO, PASO)
    with rasterio.open("susceptibilidad_inundacion.tif", "w", driver="GTiff", height=alto, width=ancho, count=1, dtype="uint8",
                       crs="EPSG:4326", transform=transform, nodata=0, compress="deflate") as dst:
        dst.write(clases, 1)
    rgba = np.zeros((alto, ancho, 4), np.uint8)
    for k, color in COLORES.items():
        rgba[clases == k] = color
    Image.fromarray(rgba, "RGBA").save("susceptibilidad_inundacion.png", optimize=True)
    n_tierra = int(tierra.sum())
    estad = {c: round(100.0 * float((clases == c).sum()) / n_tierra, 1) for c in (1, 2, 3)}
    json.dump({"extension": {"oeste": OESTE, "sur": SUR, "este": ESTE, "norte": NORTE}, "paso_grados": PASO,
               "tamano_px": [ancho, alto], "porcentaje_de_tierra_por_clase": {"baja": estad[1], "media": estad[2], "alta": estad[3]},
               "pesos": {"pendiente": PESO_PENDIENTE, "relieve": PESO_RELIEVE}, "umbrales": {"media": UMBRAL_MEDIA, "alta": UMBRAL_ALTA},
               "fuente": "Copernicus DEM GLO-30 (ESA) vía AWS Open Data"},
              open("susceptibilidad_inundacion.json", "w"), indent=1, ensure_ascii=False)
    print("Listo. Porcentaje del área por clase (baja/media/alta):", estad, file=sys.stderr)


if __name__ == "__main__":
    main()
