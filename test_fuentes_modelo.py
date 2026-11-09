"""Pruebas sin red de los lectores de fuentes y del modelo de riesgo (piloto Eje Cafetero, Colombia).

Ejecutar:  python -m unittest test_fuentes_modelo -v
"""
import datetime
import os
import tempfile
import unittest
from pathlib import Path

import almacen
import eje_perfil
import municipios_eje as me
import fuentes_datos as fd
import modelo_riesgo as mr

# Las pruebas nunca tocan la base real: usan una SQLite temporal
almacen.RUTA = Path(tempfile.mkdtemp()) / "prueba.sqlite"
almacen.SEMILLA = Path(tempfile.mkdtemp()) / "sin_semilla.json"      # las pruebas no usan la semilla real del repositorio

IDEAM_TEXTO = (
    "Fenómeno de El Niño Actualizado: 6 de noviembre de 2026 Se mantienen las condiciones de El Niño en el Pacífico ecuatorial "
    "INTENSIDAD MÁS PROBABLE Fuerte 70 % de probabilidad de mantener una intensidad fuerte hasta febrero de 2027 Este seguimiento se actualiza "
    "Próxima actualización 4 de diciembre de 2026 Ver boletín"
)

BADT_TEXTO = """Boletín No. 312
Actualización: 8 de noviembre de 2026
Alertas vigentes hasta: 9 de noviembre de 2026
Alerta Alta: Para algunos municipios de los departamentos de Caldas y Risaralda.
Alerta Moderada: Para algunos municipios de los departamentos de Caldas y Quindío.
REGIÓN ANDINA
ALERTA SITIOS PARA LOS CUALES SE GENERA LA ALERTA
CALDAS : La Dorada, Salamina
RISARALDA : Belén de Umbría
www.ideam.gov.co
REGIÓN ANDINA
ALERTA SITIOS PARA LOS CUALES SE GENERA LA ALERTA
CALDAS : Manizales
QUINDÍO : Salento
www.ideam.gov.co
"""


class PruebasLectores(unittest.TestCase):
    def test_oni(self):
        r = fd.parsear_oni("SEAS YR TOTAL ANOM\n  DJF 1950  24.72  -1.53\n  JAS 2026  29.12   2.16\n")
        self.assertEqual(r["trimestre"], "JAS 2026")
        self.assertAlmostEqual(r["anomalia"], 2.16)

    def test_nino_semanal(self):
        r = fd.parsear_nino_semanal(" 14OCT2026     26.2 5.2     29.2 4.2     30.0 3.3     29.7 1.1\n 21OCT2026     26.3 5.2     29.4 4.3     30.1 3.4     29.8 1.1\n")
        self.assertEqual(r["semana"], datetime.date(2026, 10, 21))
        self.assertAlmostEqual(r["nino34"], 3.4)

    def test_nino_semanal_con_valores_negativos_pegados(self):
        texto = (" Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA\n"
                 " 02SEP1981     20.6-0.1     24.8-0.1     26.5-0.2     28.3-0.3\n"
                 " 11NOV2026     24.1-1.2     25.0-0.9     26.4-1.1     28.0-0.6\n")
        r = fd.parsear_nino_semanal(texto)
        self.assertEqual(r["semana"], datetime.date(2026, 11, 11))
        self.assertAlmostEqual(r["nino34"], -1.1)

    def test_ideam_enso(self):
        r = fd.parsear_ideam_enso(IDEAM_TEXTO)
        self.assertEqual(r["actualizado"], datetime.date(2026, 11, 6))
        self.assertEqual((r["intensidad"], r["probabilidad"]), ("fuerte", 70))
        self.assertIn("febrero de 2027", r["hasta"])
        self.assertIn("4 de diciembre de 2026", r["proxima"])

    def test_ideam_enso_sin_datos_falla_claro(self):
        with self.assertRaises(ValueError):
            fd.parsear_ideam_enso("texto sin las cifras esperadas")

    def test_badt_niveles_por_orden(self):
        r = fd.parsear_badt(BADT_TEXTO)
        self.assertEqual(r["boletin"], 312)
        self.assertEqual(r["actualizacion"], datetime.date(2026, 11, 8))
        self.assertEqual(r["vigente_hasta"], datetime.date(2026, 11, 9))
        self.assertEqual(r["niveles"]["ALTA"], {"Caldas": ["La Dorada", "Salamina"], "Risaralda": ["Belén de Umbría"]})
        self.assertEqual(r["niveles"]["MODERADA"], {"Caldas": ["Manizales"], "Quindío": ["Salento"]})
        with self.assertRaises(ValueError):
            fd.parsear_badt("Boletín No. 1 sin alertas")

    def test_lluvia_observada_toma_la_mayor_estacion(self):
        r = fd.agregar_lluvia_observada([
            {"municipio": "Manizales", "codigoestacion": "1", "mm": "30.5", "ultima": "2026-11-08T10:00:00"},
            {"municipio": "Manizales", "codigoestacion": "2", "mm": "55.25", "ultima": "2026-11-08T11:00:00"},
            {"municipio": "Salento", "codigoestacion": "3", "mm": "5", "ultima": "2026-11-08T09:00:00"}])
        self.assertEqual(r["Manizales"], {"mm_72h": 55.2, "estaciones": 2, "ultima": "2026-11-08T11:00:00"})
        self.assertEqual(r["Salento"]["mm_72h"], 5.0)

    def test_ciifen(self):
        r = fd.parsear_ciifen(
            "• Durante septiembre... Septiembre de 2026: El Niño continúa fortaleciéndose Condiciones climáticas ENOS "
            "El Niño/La Niña en América Latina • El pronóstico para el trimestre noviembre de 2026 a enero de 2027 prevé el "
            "fortalecimiento de El Niño. Se espera que se mantenga hasta el primer trimestre de 2027. • Otro punto")
        self.assertEqual(r["estado"], "El Niño continúa fortaleciéndose")

    def test_ultimo_boletin_ciifen(self):
        html = ('<a href="https://ciifen.org/wp-content/uploads/2026/09/Boletin_ElNino_LaNina_Septiembre_2026.pdf">'
                '<a href="https://ciifen.org/wp-content/uploads/2026/10/Boletin_ElNino_LaNina_Octubre_2026.pdf">')
        self.assertEqual(fd.ultimo_boletin_ciifen(html)[:2], (2026, 10))

    def test_con_respaldo(self):
        self.assertEqual(fd.con_respaldo("prueba", lambda: {"x": 1})["_estado"], "ok")
        r = fd.con_respaldo("prueba", lambda: 1 / 0)
        self.assertEqual((r["_estado"], r["x"]), ("respaldo", 1))
        self.assertEqual(fd.con_respaldo("otra", lambda: 1 / 0)["_estado"], "error")


class PruebasAlmacen(unittest.TestCase):
    def setUp(self):
        almacen.RUTA = Path(tempfile.mkdtemp()) / "t.sqlite"
        fd._ULTIMO_BUENO.clear()

    def test_fuente_conserva_fechas_y_clave(self):
        datos = {"emision": datetime.date(2026, 10, 1), "cantones": {"A": [(datetime.date(2026, 11, 1), 3.5)]}, "_estado": "ok"}
        almacen.guardar_fuente("gfs", datos, clave="abc")
        leido, edad = almacen.leer_fuente("gfs", "abc")
        self.assertEqual(leido["emision"], datetime.date(2026, 10, 1))
        self.assertEqual(leido["cantones"]["A"][0], [datetime.date(2026, 11, 1), 3.5])   # tupla -> lista, fecha intacta
        self.assertNotIn("_estado", leido)
        self.assertIsInstance(leido["_descargado"], datetime.datetime)
        self.assertGreaterEqual(edad, 0)
        self.assertEqual(almacen.leer_fuente("gfs", "otra-clave"), (None, None))        # catálogo distinto: no sirve
        self.assertEqual(almacen.leer_fuente("no_existe"), (None, None))

    def test_series_enso(self):
        almacen.guardar_series_enso([(1998, "DJF", 2.2), (2026, "JAS", 2.16)], [("2026-10-21", 5.2, 4.3, 3.4, 1.1)])
        almacen.guardar_series_enso([(2026, "JAS", 2.16)], [("2026-10-21", 5.2, 4.3, 3.4, 1.1)])   # repetir no duplica
        self.assertEqual([f["anio"] for f in almacen.leer_oni(1990)], [1998, 2026])
        self.assertEqual(len(almacen.leer_nino_semanal()), 1)

    def test_historial_riesgo(self):
        d1 = datetime.datetime(2026, 11, 1, 12, tzinfo=datetime.timezone.utc)
        d2 = d1 + datetime.timedelta(hours=3)
        reg = lambda r: [{"canton": "Piura", "fecha": datetime.date(2026, 11, 2), "riesgo": r, "alerta": "BAJO",
                          "lluvia_mm": 1.0, "oficial_idx": 0.0, "horizonte": "GFS · día"},
                         {"canton": "Piura", "fecha": datetime.date(2026, 11, 3), "riesgo": r / 2, "alerta": "BAJO",
                          "lluvia_mm": 1.0, "oficial_idx": 0.0, "horizonte": "GFS · día"}]
        self.assertTrue(almacen.guardar_riesgo(d1, reg(0.4)))
        self.assertFalse(almacen.guardar_riesgo(d1, reg(0.9)))        # misma descarga: no se repite
        self.assertTrue(almacen.guardar_riesgo(d2, reg(0.6)))
        evo = almacen.leer_evolucion_riesgo()
        self.assertEqual([round(e["riesgo_max"], 2) for e in evo], [0.4, 0.6])
        self.assertEqual(almacen.resumen()["fotos_riesgo"], 2)

    def test_asegurar_series_descarga_solo_si_el_almacen_esta_vacio(self):
        oni = "SEAS YR TOTAL ANOM\n  JAS 2026  29.12   2.16\n"
        nino = " 21OCT2026     26.3 5.2     29.4 4.3     30.1 3.4     29.8 1.1\n"
        pedidos = []

        class R:
            def __init__(self, texto):
                self.text = texto

        original = fd._get
        try:
            fd._get = lambda url, **kw: pedidos.append(url) or R(oni if url == fd.URL_ONI else nino)
            fd.asegurar_series_enso()
            self.assertEqual(len(pedidos), 2)
            self.assertEqual(almacen.resumen()["oni"], 1)
            fd.asegurar_series_enso()                       # ya hay series: no vuelve a descargar
            self.assertEqual(len(pedidos), 2)
        finally:
            fd._get = original

    def test_evolucion_con_marcas_de_tiempo_de_formatos_mixtos(self):
        """Falló en la nube: marcas con y sin microsegundos hacían fallar pd.to_datetime y rompían la página."""
        import pandas as pd
        reg = [{"canton": "Piura", "fecha": datetime.date(2026, 11, 2), "riesgo": 0.5, "alerta": "BAJO",
                "lluvia_mm": 1.0, "oficial_idx": 0.0, "horizonte": "GFS · día"}]
        almacen.guardar_riesgo(datetime.datetime(2026, 11, 1, 20, 49, 32, 123456, tzinfo=datetime.timezone.utc), reg)
        almacen.guardar_riesgo(datetime.datetime(2026, 11, 1, 23, 51, 21, tzinfo=datetime.timezone.utc), reg)
        evo = pd.DataFrame(almacen.leer_evolucion_riesgo())
        momentos = pd.to_datetime(evo["descarga_utc"], format="ISO8601", utc=True).dt.tz_convert("America/Bogota")
        self.assertEqual(len(momentos), 2)
        self.assertEqual(momentos.iloc[1].hour, 18)                       # 23:51 UTC = 18:51 en Colombia

    def test_respaldo_desde_sqlite_si_se_pierde_la_memoria(self):
        fd.con_respaldo("ideam_prueba", lambda: {"estado": "x"})
        fd._ULTIMO_BUENO.clear()                                       # reinicio del proceso
        r = fd.con_respaldo("ideam_prueba", lambda: 1 / 0)
        self.assertEqual((r["_estado"], r["estado"]), ("respaldo", "x"))

    def test_arranque_rapido_no_descarga_si_hay_dato_reciente(self):
        llamadas = []
        originales = (fd.obtener_noaa_enso, fd.obtener_gfs, fd.obtener_cfsv2, fd.obtener_ideam_enso, fd.obtener_badt, fd.obtener_ideam_lluvia, fd.obtener_ciifen)
        try:
            fd.obtener_noaa_enso = lambda: llamadas.append("noaa") or {"oni": {"anomalia": 2.0}, "semanal": {"nino34": 2.0}}
            fd.obtener_gfs = lambda c: llamadas.append("gfs") or {"cantones": {}}
            fd.obtener_cfsv2 = lambda c: llamadas.append("cfs") or {"cantones": {}}
            fd.obtener_badt = lambda: llamadas.append("badt") or {"niveles": {}}
            fd.obtener_ideam_lluvia = lambda: llamadas.append("lluvia") or {"municipios": {}}
            fd.obtener_ideam_enso = lambda: llamadas.append("ideam") or {"estado": "fuerte"}
            fd.obtener_ciifen = lambda: llamadas.append("ciifen") or {"estado": "x"}
            primera = fd.cargar_todo(mr.CANTONES)
            self.assertEqual(sorted(llamadas), ["badt", "cfs", "ciifen", "gfs", "ideam", "lluvia", "noaa"])
            llamadas.clear()
            segunda = fd.cargar_todo(mr.CANTONES)                      # todo reciente en SQLite: cero descargas
            self.assertEqual(llamadas, [])
            self.assertEqual(segunda["ideam_enso"]["_origen"], "sqlite")
            self.assertEqual(segunda["ideam_enso"]["estado"], "fuerte")
            fd.cargar_todo(mr.CANTONES, max_edad_s=-1)                 # caducado: vuelve a descargar
            self.assertEqual(len(llamadas), 7)
            self.assertEqual(primera["_cargado"], segunda["_cargado"])   # mismo momento: no se duplica la «foto» del riesgo
        finally:
            (fd.obtener_noaa_enso, fd.obtener_gfs, fd.obtener_cfsv2, fd.obtener_ideam_enso, fd.obtener_badt, fd.obtener_ideam_lluvia, fd.obtener_ciifen) = originales



class PruebasSinDescargaAlEntrar(unittest.TestCase):
    """Entrar a la aplicación no descarga nada de internet: solo el botón «Actualizar datos» lo hace."""

    def setUp(self):
        self.llamadas = []
        self.originales = (fd.obtener_noaa_enso, fd.obtener_gfs, fd.obtener_cfsv2, fd.obtener_ideam_enso, fd.obtener_badt, fd.obtener_ideam_lluvia, fd.obtener_ciifen)
        fd.obtener_noaa_enso = lambda: self.llamadas.append("noaa") or {"oni": {"anomalia": 2.0}, "semanal": {"nino34": 2.0}}
        fd.obtener_gfs = lambda c: self.llamadas.append("gfs") or {"cantones": {}}
        fd.obtener_cfsv2 = lambda c: self.llamadas.append("cfs") or {"cantones": {}}
        fd.obtener_badt = lambda: self.llamadas.append("badt") or {"niveles": {}}
        fd.obtener_ideam_lluvia = lambda: self.llamadas.append("lluvia") or {"municipios": {}}
        fd.obtener_ideam_enso = lambda: self.llamadas.append("ideam") or {"estado": "fuerte"}
        fd.obtener_ciifen = lambda: self.llamadas.append("ciifen") or {"estado": "x"}
        self.ruta = almacen.RUTA
        almacen.RUTA = Path(tempfile.mkdtemp()) / "entrar.sqlite"          # base limpia para cada prueba

    def tearDown(self):
        almacen.RUTA = self.ruta
        (fd.obtener_noaa_enso, fd.obtener_gfs, fd.obtener_cfsv2, fd.obtener_ideam_enso, fd.obtener_badt, fd.obtener_ideam_lluvia, fd.obtener_ciifen) = self.originales

    def _guardar_antiguo(self, horas):
        viejo = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=horas)
        clave = fd._clave_cantones(mr.CANTONES)
        for nombre, datos, k in (("noaa", {"oni": {"anomalia": 1.0}, "semanal": {"nino34": 1.0}}, None), ("gfs", {"cantones": {}}, clave),
                                 ("cfsv2", {"cantones": {}}, clave), ("ideam_enso", {"estado": "debil"}, None), ("badt", {"niveles": {}}, None), ("ideam_lluvia", {"municipios": {}}, None), ("ciifen", {"estado": "y"}, None)):
            almacen.guardar_fuente(nombre, datos, k, viejo)

    def test_dato_muy_antiguo_no_dispara_descarga(self):
        self._guardar_antiguo(horas=200)                       # más de una semana: antes habría descargado
        datos = fd.cargar_todo(mr.CANTONES)
        self.assertEqual(self.llamadas, [])
        self.assertEqual(datos["ideam_enso"]["estado"], "debil")
        self.assertEqual(datos["ideam_enso"]["_origen"], "sqlite")
        self.assertEqual({k for k in datos if not k.startswith("_")}, set(fd.FUENTES))     # FUENTES = lo que carga cargar_todo()

    def test_refrescar_descarga_todo(self):
        self._guardar_antiguo(horas=1)
        datos = fd.cargar_todo(mr.CANTONES, refrescar=True)
        self.assertEqual(sorted(self.llamadas), ["badt", "cfs", "ciifen", "gfs", "ideam", "lluvia", "noaa"])
        self.assertEqual(datos["ideam_enso"]["estado"], "fuerte")

    def test_actualizar_todo_no_se_solapa(self):
        fd._BLOQUEO_DESCARGA.acquire()                         # otro usuario ya está descargando
        try:
            self.assertIsNone(fd.actualizar_todo(mr.CANTONES))
            self.assertTrue(fd.descarga_en_curso())
        finally:
            fd._BLOQUEO_DESCARGA.release()
        self.assertIsNotNone(fd.actualizar_todo(mr.CANTONES))  # libre: descarga
        self.assertFalse(fd.descarga_en_curso())

    def test_semilla_evita_la_descarga_con_el_almacen_vacio(self):
        self._guardar_antiguo(horas=5)
        almacen.guardar_series_enso([(2026, "JAS", 2.1)], [("2026-10-28", 1.0, 2.0, 3.0, 4.0)])
        semilla = Path(tempfile.mkdtemp()) / "semilla.json"
        almacen.exportar_semilla(semilla)
        almacen.RUTA = Path(tempfile.mkdtemp()) / "servidor_nuevo.sqlite"    # servidor recién iniciado: almacén vacío
        self.assertEqual(almacen.importar_semilla(semilla), 7)
        self.assertEqual(almacen.importar_semilla(semilla), 0)               # no pisa ni duplica
        self.assertEqual(almacen.resumen()["oni"], 1)
        almacen.SEMILLA, previa = semilla, almacen.SEMILLA
        try:
            almacen.RUTA = Path(tempfile.mkdtemp()) / "otro_servidor.sqlite"
            datos = fd.cargar_todo(mr.CANTONES)                              # importa la semilla por su cuenta
        finally:
            almacen.SEMILLA = previa
        self.assertEqual(self.llamadas, [])
        self.assertEqual(datos["noaa"]["oni"]["anomalia"], 1.0)

    def test_semilla_del_repositorio_es_valida(self):
        import json
        with open(Path(__file__).with_name("datos_semilla.json"), encoding="utf-8") as f:
            semilla = json.load(f)
        self.assertEqual({x["nombre"] for x in semilla["fuente"]}, {"noaa", "gfs", "cfsv2", "ideam_enso", "badt", "ideam_lluvia", "ciifen"})
        self.assertGreater(len(semilla["oni"]), 800)
        self.assertGreater(len(semilla["nino_semanal"]), 2000)



class PruebasActualizacionDiaria(unittest.TestCase):
    def setUp(self):
        self.ruta = almacen.RUTA
        almacen.RUTA = Path(tempfile.mkdtemp()) / "diaria.sqlite"

    def tearDown(self):
        almacen.RUTA = self.ruta

    def test_toca_actualizar_solo_al_cambiar_el_dia_en_ecuador(self):
        utc = datetime.timezone.utc
        ayer = datetime.datetime(2026, 11, 2, 20, 0, tzinfo=utc)                  # 15:00 del 2 en Colombia
        self.assertFalse(fd.toca_actualizar(ayer, datetime.datetime(2026, 11, 3, 9, 0, tzinfo=utc)))    # 04:00 del 3: aún no
        self.assertTrue(fd.toca_actualizar(ayer, datetime.datetime(2026, 11, 3, 10, 30, tzinfo=utc)))   # 05:30 del 3: toca
        self.assertFalse(fd.toca_actualizar(datetime.datetime(2026, 11, 3, 10, 40, tzinfo=utc),
                                            datetime.datetime(2026, 11, 3, 22, 0, tzinfo=utc)))        # ya es de hoy
        self.assertTrue(fd.toca_actualizar(None, datetime.datetime(2026, 11, 3, 12, 0, tzinfo=utc)))     # sin datos y de día
        # 03:00 UTC del 3 = 22:00 del 2 en Colombia: sigue siendo el mismo día
        self.assertFalse(fd.toca_actualizar(ayer, datetime.datetime(2026, 11, 3, 3, 0, tzinfo=utc)))

    def test_semilla_mas_nueva_reemplaza_y_la_mas_vieja_no(self):
        semilla = Path(tempfile.mkdtemp()) / "semilla.json"
        viejo = datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc)
        nuevo = datetime.datetime(2026, 11, 3, tzinfo=datetime.timezone.utc)
        almacen.guardar_fuente("ideam_enso", {"estado": "debil"}, None, nuevo)
        almacen.exportar_semilla(semilla)                                     # semilla con el dato NUEVO (10 cm)
        almacen.guardar_fuente("ideam_enso", {"estado": "otra"}, None, nuevo + datetime.timedelta(days=1))
        self.assertEqual(almacen.importar_semilla(semilla), 0)               # el almacén tiene algo más nuevo: no se pisa
        self.assertEqual(almacen.leer_fuente("ideam_enso")[0]["estado"], "otra")
        almacen.guardar_fuente("ideam_enso", {"estado": "otra2"}, None, viejo)  # el almacén tiene algo más viejo
        self.assertEqual(almacen.importar_semilla(semilla), 1)
        self.assertEqual(almacen.leer_fuente("ideam_enso")[0]["estado"], "debil")

    def test_hilo_diario_actualiza_cuando_cambia_el_dia(self):
        llamadas, avisos = [], []
        originales = (fd.actualizar_todo, fd._ultima_descarga, fd.toca_actualizar, fd._ACTUALIZADOR["hilo"])
        try:
            fd._ACTUALIZADOR["hilo"] = None
            fd._ultima_descarga = lambda c: None
            fd.toca_actualizar = lambda ultima, ahora=None: True
            fd.actualizar_todo = lambda c: llamadas.append(1) or {"ok": 1}
            hilo = fd.iniciar_actualizador_diario(mr.CANTONES, al_actualizar=lambda: avisos.append(1), cada_s=0.05, espera_inicial_s=0)
            self.assertIs(fd.iniciar_actualizador_diario(mr.CANTONES), hilo)    # una sola vez por proceso
            import time
            for _ in range(60):
                if llamadas and avisos:
                    break
                time.sleep(0.05)
            hilo.parar.set()
            hilo.join(2)
            self.assertTrue(llamadas and avisos)
        finally:
            (fd.actualizar_todo, fd._ultima_descarga, fd.toca_actualizar, fd._ACTUALIZADOR["hilo"]) = originales

    def test_actualizar_semilla_conserva_la_semilla_si_falla_la_lluvia(self):
        import subprocess, sys, os
        raiz = Path(__file__).parent
        copia = Path(tempfile.mkdtemp())
        for f in ("actualizar_semilla.py", "almacen.py", "fuentes_datos.py", "modelo_riesgo.py", "municipios_eje.py", "climatologia.json", "datos_semilla.json"):
            if (raiz / f).exists():                                             # climatologia.json puede faltar en un clon nuevo
                (copia / f).write_bytes((raiz / f).read_bytes())
        antes = (copia / "datos_semilla.json").read_bytes()
        sitecustomize = copia / "sitecustomize.py"                              # sin red: toda petición HTTP falla
        sitecustomize.write_text("import requests\ndef _f(*a, **k):\n    raise RuntimeError('sin red')\nrequests.get = _f\n")
        r = subprocess.run([sys.executable, "actualizar_semilla.py"], cwd=copia, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONPATH": str(copia)})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)                 # la lluvia sale «respaldo», no «ok»: error
        self.assertIn("respaldo", r.stdout)
        self.assertEqual((copia / "datos_semilla.json").read_bytes(), antes)




class PruebasBuscadorMunicipios(unittest.TestCase):
    def test_datos_del_buscador(self):
        lista = me.MUNICIPIOS_EJE
        self.assertEqual(len(lista), 53)
        self.assertEqual({c["p"] for c in lista}, {"Caldas", "Risaralda", "Quindío"})
        for c in lista:
            self.assertTrue(c["r"], c["n"])
            oeste, sur, este, norte = c["b"]
            self.assertTrue(oeste <= c["c"][0] <= este and sur <= c["c"][1] <= norte, c["n"])
            self.assertTrue(-76.5 < oeste < este < -74.5 and 4.0 < sur < norte < 6.0, c["n"])
            for anillo in c["r"]:
                self.assertEqual(len(anillo) % 2, 0)
                self.assertGreaterEqual(len(anillo), 6)
        self.assertEqual(len({c["u"] for c in lista}), 53)
        self.assertTrue(eje_perfil.EJE_PERFIL)

    def test_municipios_del_modelo_dentro_de_su_municipio(self):
        por = {d["u"]: d for d in me.MUNICIPIOS_EJE}
        self.assertEqual(len(mr.CANTONES), 34)
        for c in mr.CANTONES:
            m = por[c["dane"]]
            self.assertEqual(m["n"], c["canton"])
            self.assertEqual(m["p"], c["provincia"])
            oeste, sur, este, norte = m["b"]
            self.assertTrue(oeste <= c["lon"] <= este and sur <= c["lat"] <= norte, c["canton"])


class PruebasFormatoContornos(unittest.TestCase):
    def test_anillo_plano_acepta_pares_y_planos(self):
        import re
        fuente = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        cuerpo = re.search(r"def _anillo_plano\(anillo\):.*?\n\n\n", fuente, re.S).group(0)
        ns = {}
        exec(cuerpo, ns)
        plano, pares = [1.0, 2.0, 3.0, 4.0], [[1.0, 2.0], [3.0, 4.0]]
        self.assertEqual(ns["_anillo_plano"](plano), plano)
        self.assertEqual(ns["_anillo_plano"](pares), plano)
        self.assertEqual(ns["_anillo_plano"]([]), [])


CLIMA = {"cantones": {"Manizales": {"dia_p50": 5.0, "dia_p99": 55.0, "d3_p50": 10.0, "d3_p99": 110.0,
                                    "mes": {"11": {"p50": 300.0, "p95": 500.0}}}}}


class PruebasModelo(unittest.TestCase):
    def c(self, nombre):
        return next(x for x in mr.CANTONES if x["canton"] == nombre)

    def test_niveles_de_alerta(self):
        self.assertEqual([mr.nivel_alerta(x) for x in (0.9, 0.75, 0.55, 0.45, 0.1)],
                         ["CRÍTICO", "ALTO RIESGO", "ALERTA AMARILLA", "MEDIO", "BAJO"])

    def test_lluvia_relativa_al_clima_local(self):
        m = self.c("Manizales")
        self.assertEqual(mr.s_lluvia_dia(m, 5.0, 5.0, CLIMA), 0.0)          # lluvia típica = 0
        self.assertEqual(mr.s_lluvia_dia(m, 55.0, 5.0, CLIMA), 1.0)         # extrema = 1
        self.assertAlmostEqual(mr.s_lluvia_observada(m, 60.0, CLIMA), 0.5)
        self.assertGreater(mr.s_lluvia_dia(m, 40.0, 40.0, {}), 0.5)         # sin clima: umbrales de respaldo

    def test_deficit_solo_si_llueve_menos_que_la_mediana(self):
        m = self.c("Manizales")
        self.assertEqual(mr.s_deficit_mes(m, 11, 400.0, CLIMA), 0.0)
        self.assertAlmostEqual(mr.s_deficit_mes(m, 11, 120.0, CLIMA), 1.0)  # 60 % por debajo
        self.assertEqual(mr.s_deficit_mes(m, 3, 10.0, CLIMA), 0.0)          # mes sin estadística

    def test_indice_enso_firmado(self):
        self.assertEqual(mr.indice_enso_firmado(None, None), 0.0)
        self.assertEqual(mr.indice_enso_firmado(2.0, 3.0), 1.0)
        self.assertEqual(mr.indice_enso_firmado(-2.0, -3.0), -1.0)

    def test_la_nina_refuerza_la_lluvia_y_el_nino_no(self):
        m = self.c("Manizales")
        base = mr.calcular_riesgo(m, 0.6, 0.0, 0.0)
        self.assertGreater(mr.calcular_riesgo(m, 0.6, 0.0, -1.0), base)
        self.assertEqual(mr.calcular_riesgo(m, 0.6, 0.0, 1.0), base)

    def test_el_nino_refuerza_el_deficit(self):
        self.assertGreater(mr.calcular_riesgo_deficit(0.5, 1.0), mr.calcular_riesgo_deficit(0.5, 0.0))
        self.assertEqual(mr.calcular_riesgo_deficit(0.0, -1.0), 0.0)

    def test_alerta_oficial_sube_el_riesgo(self):
        m = self.c("Manizales")
        self.assertGreater(mr.calcular_riesgo(m, 0.3, 1.0, 0.0), mr.calcular_riesgo(m, 0.3, 0.0, 0.0))
        self.assertLessEqual(mr.calcular_riesgo(m, 1.0, 1.0, -1.0), 1.0)

    def test_lluvia_extrema_sola_llega_a_alto_riesgo_en_ladera(self):
        m = self.c("Pueblo Rico")                                          # pendiente alta
        self.assertGreaterEqual(mr.calcular_riesgo(m, 1.0, 0.0, 0.0), mr.UMBRALES["alto"])

    def test_nivel_badt_ignora_tildes_y_mayusculas(self):
        badt = {"niveles": {"ALTA": {"CALDAS": ["la dorada"]}, "MODERADA": {"quindio": ["SALENTO"]}, "BAJA": {}}}
        self.assertEqual(mr.nivel_badt(self.c("La Dorada"), badt), "ALTA")
        self.assertEqual(mr.nivel_badt(self.c("Salento"), badt), "MODERADA")
        self.assertIsNone(mr.nivel_badt(self.c("Manizales"), badt))
        self.assertIsNone(mr.nivel_badt(self.c("Salento"), {"_estado": "error"}))

    def test_exposicion_en_rango(self):
        for c in mr.CANTONES:
            self.assertTrue(0.0 <= mr.s_exposicion(c) <= 1.0, c["canton"])
        self.assertEqual(mr.s_exposicion(self.c("La Dorada")), mr.EXPOSICION_RIBERA)

    def test_construir_registros(self):
        hoy = datetime.date(2026, 11, 8)
        dias = [(hoy + datetime.timedelta(days=i), 20.0) for i in range(4)]
        datos = {"noaa": {"oni": {"anomalia": 2.0}, "semanal": {"nino34": 3.0}},
                 "badt": {"niveles": {"ALTA": {"Caldas": ["La Dorada"]}, "MODERADA": {}, "BAJA": {}}},
                 "ideam_lluvia": {"municipios": {"La Dorada": {"mm_72h": 90.0}}},
                 "gfs": {"cantones": {"La Dorada": dias}},
                 "cfsv2": {"cantones": {"La Dorada": [(datetime.date(2026, 12, 1), 10.0)]}}}
        regs, enso = mr.construir_registros(datos, hoy=hoy)
        self.assertEqual(enso, 1.0)
        dor = [r for r in regs if r["canton"] == "La Dorada"]
        self.assertEqual(len(dor), 5)
        self.assertEqual(dor[0]["horizonte"], "GFS · día")
        self.assertEqual(dor[0]["oficial_idx"], 1.0)                       # hoy: alerta vigente
        self.assertEqual(dor[0]["obs_mm"], 90.0)                           # hoy: lluvia observada
        self.assertEqual(dor[3]["oficial_idx"], 0.0)                       # pasado mañana: ya no
        self.assertEqual(dor[4]["horizonte"], "CFSv2 · mes")
        self.assertEqual(dor[4]["tipo"], "Déficit de lluvia")              # El Niño + mes seco
        self.assertGreater(dor[0]["riesgo"], dor[3]["riesgo"])


class TestSusceptibilidad(unittest.TestCase):
    """La capa de susceptibilidad a deslizamientos (generar_susceptibilidad.py) y su archivo de metadatos."""

    def test_json_coherente(self):
        import json
        with open(os.path.join(os.path.dirname(__file__), "susceptibilidad_inundacion.json"), encoding="utf-8") as f:
            j = json.load(f)
        e = j["extension"]
        self.assertEqual((e["oeste"], e["sur"], e["este"], e["norte"]), (-76.3, 4.0, -74.6, 5.85))
        pct = j["porcentaje_de_tierra_por_clase"]
        self.assertAlmostEqual(sum(pct.values()), 100.0, delta=0.5)
        self.assertGreater(pct["baja"], pct["alta"])
        self.assertLess(max(j["tamano_px"]), 4096)

    def test_png_tamano_y_colores(self):
        from PIL import Image
        with Image.open(os.path.join(os.path.dirname(__file__), "susceptibilidad_inundacion.png")) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertLess(max(im.size), 4096)

    def test_calculo_sintetico(self):
        try:
            import numpy as np
            import generar_susceptibilidad as g
        except ImportError:
            self.skipTest("requiere rasterio, scipy y numpy (solo para regenerar la capa)")
        dem = np.zeros((120, 120), np.float32)
        dem[:, 60:] = np.arange(60)[None, :] * 80.0                      # ladera muy empinada (80 m por celda de ~92 m: ~41°)
        clases, indice, tierra = g.calcular(dem)
        self.assertEqual(clases[60, 10], 1)                              # llano: baja
        self.assertEqual(clases[60, 100], 3)                             # ladera: alta


if __name__ == "__main__":
    unittest.main()
