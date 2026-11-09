# Monitoreo ENSO Colombia · Piloto Eje Cafetero

Sistema de alerta temprana y riesgo por El Niño / La Niña para el **Eje Cafetero** (Caldas, Risaralda y Quindío).
Proyecto GeoCiencias — Autor y mentor: **Raúl Acevedo**. Es la réplica para Colombia de los sistemas de Ecuador y Perú.
**Piloto para demostración: indicativo, no sustituye los boletines oficiales del IDEAM ni de la UNGRD.**

## Qué cambia respecto a Ecuador y Perú
En el Eje Cafetero (zona andina) el riesgo no es el mar sino la **ladera**: deslizamientos por lluvia en exceso con La Niña y
**déficit de lluvia** (sequía, incendios) con El Niño. El modelo incluye las dos amenazas.

## Qué hace
- **Visor 3D (CesiumJS)** con perfil del Eje Cafetero, buscador de **53 municipios** (SGC, código DANE), capas NOAA/NASA/CCSR-IRI y
  capa de **susceptibilidad a deslizamientos** (pendiente y relieve del Copernicus DEM).
- **Modelo para 34 municipios piloto**: lluvia frente al clima local + exposición del terreno + **alerta oficial del IDEAM (BADT)**;
  lluvia observada (estaciones automáticas IDEAM, 72 h) para el día de hoy; déficit de lluvia mensual reforzado por El Niño.
- Datos en vivo; al entrar no se descarga nada. Se renuevan con «Actualizar datos» o con la tarea diaria de GitHub Actions (06:00 hora de Colombia).

| Fuente | Qué se usa |
|---|---|
| IDEAM · micrositio de El Niño | Estado e intensidad más probable del ENOS |
| IDEAM · BADT (PDF diario) | Alertas por deslizamientos por municipio (alta / moderada / baja) |
| IDEAM · precipitación (datos.gov.co, `s54a-sgyg`) | Lluvia observada cada 10 min en estaciones automáticas |
| NOAA CPC | ONI y anomalías Niño 1+2, 3, 3.4 y 4 |
| NOAA GFS (Open-Meteo) · CCSR/IRI CFSv2 | Lluvia diaria (16 días) y mensual (10 meses) |
| CIIFEN | Boletín mensual El Niño/La Niña |
| SGC (ArcGIS REST) | Límites municipales y departamentales con código DANE |
| Copernicus DEM GLO-30 (ESA) | Terreno: pendiente, relieve, susceptibilidad |

## Limitaciones del piloto
- Pesos y umbrales heredados de Ecuador y Perú, **sin validar con eventos del Eje Cafetero** (siguiente fase: inventario de la UNGRD y del SGC).
- La susceptibilidad es un **proxy topográfico**: no incluye geología, suelos ni cobertura.
- El BADT se lee de un PDF; si el IDEAM cambia su formato, esa fuente queda sin datos y la app lo avisa.
- La lluvia observada es preliminar.

## Archivos
`app.py` (interfaz y visor) · `fuentes_datos.py` · `modelo_riesgo.py` · `almacen.py` (SQLite) · `datos_semilla.json` + `actualizar_semilla.py` +
`.github/workflows/actualizar_datos.yml` · `climatologia.json` (`generar_climatologia.py`) · `generar_municipios.py` · `generar_piloto.py` ·
`generar_susceptibilidad.py` · `test_fuentes_modelo.py` (`python -m unittest test_fuentes_modelo -v`).

## Ejecutar
```bash
pip install -r requirements.txt
streamlit run app.py
```
