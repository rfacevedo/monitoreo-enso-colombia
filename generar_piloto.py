"""Genera el catálogo de municipios del modelo piloto (Eje Cafetero) con datos del terreno.

Para cada municipio toma la ubicación de su cabecera (coordenada aproximada; se comprueba que cae dentro del municipio) y, con el
Copernicus DEM GLO-30 (30 m, AWS Open Data), calcula en una ventana de ~5 km alrededor:
- elevación en la cabecera,
- pendiente (percentil 90, en grados) y relieve local (máximo menos mínimo, en metros).

Con eso asigna la amenaza: «inundacion» (fondos de valle llanos: relieve < 100 m y pendiente < 8°) o «deslizamiento» (laderas).
Imprime el catálogo listo para pegar en ``modelo_riesgo.py`` y lo guarda en ``_datos/piloto.json``.

    python generar_piloto.py
"""

import json
import math

import numpy as np
import rasterio
from rasterio.windows import from_bounds

import municipios_eje as me

URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
       "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")

# código DANE: (latitud, longitud) de la cabecera municipal (aproximadas)
CABECERAS = {
    "17001": (5.0689, -75.5174), "17873": (5.0447, -75.5144), "17174": (4.9833, -75.6049), "17524": (5.0167, -75.6167),
    "17486": (5.1667, -75.5167), "17050": (5.2667, -75.4833), "17653": (5.4064, -75.4881), "17614": (5.4231, -75.7036),
    "17042": (5.2325, -75.7867), "17380": (5.4500, -74.6667), "17013": (5.6167, -75.4569), "17513": (5.5303, -75.4586),
    "17777": (5.4500, -75.6500), "17541": (5.3856, -75.1594),
    "66001": (4.8133, -75.6961), "66170": (4.8397, -75.6728), "66682": (4.8687, -75.6217), "66440": (4.9356, -75.7378),
    "66400": (4.8997, -75.8786), "66088": (5.2000, -75.8667), "66045": (5.1042, -75.9422), "66594": (5.3394, -75.7347),
    "66572": (5.2214, -76.0306), "66687": (5.0711, -75.9650),
    "63001": (4.5339, -75.6811), "63130": (4.5292, -75.6428), "63470": (4.5667, -75.7500), "63594": (4.6247, -75.7631),
    "63401": (4.4528, -75.7894), "63190": (4.6178, -75.6350), "63690": (4.6372, -75.5714), "63272": (4.6753, -75.6603),
    "63548": (4.3342, -75.7003), "63302": (4.2058, -75.7906),
}


def _tesela(lat, lon):
    return URL.format(ns="N" if lat >= 0 else "S", lat=abs(math.floor(lat)), ew="E" if lon >= 0 else "W", lon=abs(math.floor(lon)))


def terreno(lat, lon, radio=0.025):
    """(elevación, pendiente p90 en grados, relieve en m) en una ventana de ±radio grados alrededor del punto."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(_tesela(lat, lon)) as ds:
            ventana = from_bounds(lon - radio, lat - radio, lon + radio, lat + radio, ds.transform)
            dem = ds.read(1, window=ventana, boundless=True, fill_value=0).astype(float)
            h0 = float(ds.read(1, window=from_bounds(lon - 0.0003, lat - 0.0003, lon + 0.0003, lat + 0.0003, ds.transform),
                               boundless=True, fill_value=0).mean())
    paso_m = 30.0
    gy, gx = np.gradient(dem, paso_m)
    pend = np.degrees(np.arctan(np.hypot(gx, gy)))
    return h0, float(np.percentile(pend, 90)), float(dem.max() - dem.min())


def dentro(m, lat, lon):
    o, s, e, n = m["b"]
    return o <= lon <= e and s <= lat <= n


def main():
    por = {m["u"]: m for m in me.MUNICIPIOS_EJE}
    salida = []
    for codigo, (lat, lon) in CABECERAS.items():
        m = por[codigo]
        if not dentro(m, lat, lon):
            print("  fuera de su municipio, se usa el centro:", m["n"], lat, lon)
            lon, lat = m["c"]
        h, pend, relieve = terreno(lat, lon)
        amenaza = "inundacion" if (relieve < 100 and pend < 8) else "deslizamiento"
        salida.append({"canton": m["n"], "provincia": m["p"], "lat": round(lat, 4), "lon": round(lon, 4), "elevacion": round(h, 0),
                       "pendiente": round(pend, 1), "relieve": round(relieve, 0), "amenaza": amenaza, "dane": codigo})
        print(f"  {m['n']:<22}{m['p']:<10} h={h:6.0f} m  pend90={pend:5.1f}°  relieve={relieve:5.0f} m  -> {amenaza}")
    json.dump(salida, open("_datos/piloto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return salida


if __name__ == "__main__":
    main()
