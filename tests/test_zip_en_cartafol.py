"""`.zip` dentro dun cartafol (e `.zip` dado directamente na xanela).

Antes (comprobado no portátil Windows o 15/11/2026) un cartafol con .zip e
PDF soltos anonimizaba os PDF e saltaba os .zip sen dicir nada; e a xanela
tampouco abría un .zip dado directamente (só a liña de ordes). Agora cada
.zip sae coma `<nome anonimizado>.anonimizado.zip`, coa mesma estrutura, e
nada sae sen anonimizar por ningún camiño: zip danado, con contrasinal,
demasiado grande, zip dentro de zip, rutas con `..`, erro ao escribir ou
cancelar o lote. Os nomes (do zip e de dentro) anonimízanse ao final do
lote, para que non cambien os códigos nin os avisos de homónimo dos
documentos (ver `pipeline.preparar_zip`). Datos inventados."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import contextlib
import io
import re
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

import docx
import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import cli, explorador, pipeline, web
from anonimizador.pipeline import (
    LimiteDescompresion,
    ZipRexeitado,
    gardar_zip_preparado,
    listar_ficheiros_soportados,
    preparar_zip,
)
from anonimizador.registry import RexistroCorrespondencias

# Todo o que nunca pode quedar á vista (nomes, DNI, teléfono, correo).
REAIS = ["Xosé", "Carballo", "Portela", "12345678", "600123456", "xose.carballo",
         "Ferrándiz", "Salcedo", "30014811"]
TEXTO_XOSE = ("Comparece Xosé Carballo Portela, con DNI 12345678Z, teléfono 600123456 "
              "e correo xose.carballo@example.com, e presenta a demanda.")
TEXTO_MANUEL = "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou como testemuña."
# Dá un aviso de posible fuga sen detectar (ver test_automatico_revisar).
TEXTO_FUGA = "Comparece don Xoán Páez Veiga. Referencia 34867809 do expediente."


def _docx_bytes(texto: str, autor: str) -> bytes:
    doc = docx.Document()
    doc.add_paragraph().add_run(texto).bold = True
    doc.core_properties.author = autor
    doc.core_properties.title = "Informe de " + autor
    saida = io.BytesIO()
    doc.save(saida)
    return saida.getvalue()


def _pdf_bytes(texto: str, autor: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), texto, fontsize=10)
    doc.set_metadata({"author": autor, "title": "Escrito de " + autor})
    return doc.tobytes()


def _zip(ruta: Path, entradas: dict) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, datos in entradas.items():
            z.writestr(nome, datos)
    return ruta


def _textos_do_zip(ruta: Path) -> dict:
    """Todo o texto de cada entrada, metadatos incluídos (o XML enteiro dun
    .docx/.odt, o texto e os metadatos dun PDF)."""
    textos = {}
    with zipfile.ZipFile(ruta) as z:
        for nome in z.namelist():
            datos = z.read(nome)
            if nome.endswith((".docx", ".odt")):
                with zipfile.ZipFile(io.BytesIO(datos)) as d:
                    textos[nome] = "\n".join(d.read(m).decode("utf-8", "replace") for m in d.namelist())
            elif nome.endswith(".pdf"):
                pdf = fitz.open(stream=datos, filetype="pdf")
                textos[nome] = "".join(p.get_text() for p in pdf) + str(pdf.metadata) + (pdf.get_xml_metadata() or "")
            else:
                textos[nome] = datos.decode("utf-8")
    return textos


class _Base(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.cartafol = self.dir / "entrada"
        self.cartafol.mkdir()
        self.saida = self.dir / "saida"
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def procesar(self, ruta=None, modo="automatico", saida=True, **extra) -> str:
        datos = {"ruta": str(ruta or self.cartafol), "rexistro": self.rexistro_dir, "modo": modo, **extra}
        if saida:
            datos["cartafol_saida"] = str(self.saida)
        r = self.client.post("/procesar", data=datos)
        self.assertIn(r.status_code, (200, 302), r.get_data(as_text=True)[:2000])
        return r.get_data(as_text=True)

    def zips_de_saida(self) -> list:
        return sorted(self.saida.glob("*.anonimizado.zip"))

    def assertSenDatosReais(self, texto: str, onde: str):
        for real in REAIS:
            self.assertNotIn(real.casefold(), texto.casefold(), f"«{real}» á vista en {onde}")


class TestZipEnCartafol(_Base):
    def _expediente(self):
        (self.cartafol / "demanda.txt").write_text(TEXTO_XOSE, encoding="utf-8")
        _zip(self.cartafol / "Expediente Xosé Carballo Portela.zip", {
            "Cliente Xosé Carballo Portela/nota.txt": TEXTO_XOSE,
            "Cliente Xosé Carballo Portela/Informe Manuel Ferrándiz Salcedo.docx":
                _docx_bytes(TEXTO_MANUEL, "Xosé Carballo Portela"),
            "escritos/Escrito Manuel Ferrándiz Salcedo.pdf": _pdf_bytes(TEXTO_MANUEL, "Manuel Ferrándiz Salcedo"),
            "planos/plano Carballo.dwg": b"\x00\x01binario",
            "__MACOSX/Cliente Xosé Carballo Portela/._nota.txt": b"\x00\x05",
            "Cliente Xosé Carballo Portela/._nota.txt": b"\x00\x05",
        })

    def test_nada_sen_anonimizar_no_zip_de_saida_nin_nos_md(self):
        self._expediente()
        html = self.procesar(copia_md="1")
        zips = self.zips_de_saida()
        self.assertEqual(len(zips), 1, list(self.saida.iterdir()))
        self.assertSenDatosReais(zips[0].name, "o nome do zip")
        textos = _textos_do_zip(zips[0])
        for nome, texto in textos.items():
            self.assertSenDatosReais(nome, "o nome dunha entrada")
            self.assertSenDatosReais(texto, nome)
        nomes = sorted(textos)
        # Mesma estrutura: 3 documentos (txt, docx, pdf), cada un coa súa copia .md.
        self.assertEqual(len([n for n in nomes if n.endswith(".md")]), 3, nomes)
        self.assertEqual(len([n for n in nomes if not n.endswith(".md")]), 3, nomes)
        self.assertTrue(any(n.startswith("escritos/") and n.endswith(".anonimizado.pdf") for n in nomes), nomes)
        self.assertTrue(any(n.endswith(".anonimizado.docx") for n in nomes), nomes)
        self.assertEqual(len({PurePath_parent(n) for n in nomes if n.endswith(".anonimizado.txt")}), 1)
        # Nada do que non se pode analizar entra no zip.
        self.assertFalse(any("dwg" in n or "MACOSX" in n or "/._" in n for n in nomes), nomes)
        # ... e a pantalla dio, co motivo.
        self.assertIn("plano Carballo.dwg", html)
        self.assertIn("formato que non se pode analizar", html)
        self.assertIn("metadatos de macOS", html)
        self.assertIn("3 documento(s) anonimizado(s) dentro do .zip", html)
        # O PDF solto do cartafol tamén saíu.
        self.assertTrue(list(self.saida.glob("*.anonimizado.txt")))

    def test_mesmo_codigo_no_cartafol_e_dentro_do_zip(self):
        (self.cartafol / "demanda.txt").write_text(TEXTO_XOSE, encoding="utf-8")
        _zip(self.cartafol / "exp.zip", {
            "Xosé Carballo Portela/indice.txt": "Índice do expediente, sen nomes.",
            "Xosé Carballo Portela/escrito.txt": TEXTO_XOSE,
        })
        self.procesar()
        solto = next(self.saida.glob("*.anonimizado.txt")).read_text(encoding="utf-8")
        codigo = re.search(r"PERSOA_\d+", solto).group(0)
        textos = _textos_do_zip(self.zips_de_saida()[0])
        escrito = next(t for n, t in textos.items() if n.endswith("escrito.anonimizado.txt"))
        self.assertIn(codigo, escrito)
        # O cartafol interno leva ese mesmo código, tamén para o índice (que
        # non nomea a ninguén): as persoas de todo o zip valen para os nomes.
        for nome in textos:
            self.assertEqual(nome.split("/")[0], codigo, sorted(textos))

    def test_nome_do_zip_non_cambia_codigos_nin_avisos_dun_documento_posterior(self):
        """A persoa do nome do zip aparece por primeira vez nun documento
        POSTERIOR do cartafol: o documento debe saír igual ca sen o zip
        (mesmo código, sen aviso de posible homónimo)."""
        def lote(con_zip: bool, base: Path) -> tuple:
            entrada = base / "entrada"
            entrada.mkdir(parents=True)
            if con_zip:
                _zip(entrada / "a Expediente Xosé Carballo Portela.zip", {
                    "Cliente Xosé Carballo Portela/indice.txt": "Índice do expediente, sen nomes.",
                })
            (entrada / "b demanda.txt").write_text(TEXTO_XOSE, encoding="utf-8")
            r = self.client.post("/procesar", data={
                "ruta": str(entrada), "rexistro": str(base / "rexistro"), "modo": "automatico",
                "cartafol_saida": str(base / "saida"),
            })
            html = r.get_data(as_text=True)
            texto = next((base / "saida").glob("b demanda*.anonimizado.txt")).read_text(encoding="utf-8")
            resumo = re.search(r"b demanda\.txt</strong>.*?<br>\s*([^<]*?mosaico)", html, re.S).group(1)
            return texto, resumo, html

        texto_sen, resumo_sen, _ = lote(False, self.dir / "sen")
        texto_con, resumo_con, html = lote(True, self.dir / "con")
        self.assertEqual(texto_con, texto_sen)
        self.assertEqual(resumo_con, resumo_sen)
        self.assertIn("0 persoa(s) marcada(s)", resumo_con)
        zip_saida = next((self.dir / "con" / "saida").glob("*.anonimizado.zip"))
        self.assertSenDatosReais(zip_saida.name, "o nome do zip")
        for nome in _textos_do_zip(zip_saida):
            self.assertSenDatosReais(nome, "o nome dunha entrada")

    def test_entradas_duplicadas_conservan_cada_informe_e_aviso(self):
        """Dúas entradas co mesmo nome no zip: o aviso de posibles fugas da
        primeira non pode perderse tapado polo informe da segunda."""
        with zipfile.ZipFile(self.cartafol / "dup.zip", "w") as z, warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile avisa do nome duplicado
            z.writestr("nota.txt", TEXTO_FUGA)
            z.writestr("nota.txt", "Documento sen nomes.")
        html = self.procesar()
        self.assertIn("2 documento(s) anonimizado(s) dentro do .zip", html)
        self.assertIn("1 documento(s) do .zip con posibles fugas", html)
        textos = _textos_do_zip(self.zips_de_saida()[0])
        self.assertEqual(len([n for n in textos if not n.endswith(".md")]), 2)
        resultado = pipeline.anonimizar_zip(
            str(self.cartafol / "dup.zip"), str(self.dir / "s.zip"), RexistroCorrespondencias(str(self.dir / "r2")))
        self.assertEqual([d["nome"] for d in resultado["documentos"]], ["nota.txt", "nota.txt"])
        self.assertEqual(len(resultado["ficheiros"]), 2)
        self.assertEqual(len(set(resultado["saidas"].values())), 2)

    def test_zip_danado_ou_con_contrasinal_omitese_e_o_lote_segue(self):
        (self.cartafol / "roto.zip").write_bytes(b"isto non e un zip")
        # Zip válido por fóra pero cos datos estragados (CRC mal ao descomprimir).
        bo = _zip(self.dir / "bo.zip", {"Xosé Carballo Portela.txt": TEXTO_XOSE * 20})
        datos = bytearray(bo.read_bytes())
        datos[60:90] = b"\xff" * 30
        (self.cartafol / "estragado.zip").write_bytes(bytes(datos))
        # Contrasinal: o bit de cifrado na entrada (zipfile non sabe cifrar).
        secreto = bytearray(_zip(self.dir / "s.zip", {"Xosé Carballo Portela.txt": TEXTO_XOSE}).read_bytes())
        secreto[6] |= 0x1  # cabeceira local
        secreto[secreto.index(b"PK\x01\x02") + 8] |= 0x1  # directorio central
        (self.cartafol / "secreto.zip").write_bytes(bytes(secreto))
        (self.cartafol / "nota.txt").write_text(TEXTO_MANUEL, encoding="utf-8")
        html = self.procesar()
        self.assertEqual(self.zips_de_saida(), [])
        self.assertEqual(len(list(self.saida.glob("*.anonimizado.txt"))), 1)
        self.assertIn("roto.zip", html)
        self.assertIn("estragado.zip", html)
        self.assertIn("non se puido abrir o .zip (danado)", html)
        self.assertIn(".zip protexido con contrasinal", html)
        for ficheiro in self.saida.rglob("*"):
            self.assertSenDatosReais(ficheiro.name, "a saída")

    def test_zip_dentro_de_zip_non_se_abre(self):
        interior = io.BytesIO()
        with zipfile.ZipFile(interior, "w") as z:
            z.writestr("Xosé Carballo Portela.txt", TEXTO_XOSE)
        _zip(self.cartafol / "exterior.zip", {
            "dentro/Expediente Carballo.zip": interior.getvalue(),
            "nota.txt": TEXTO_MANUEL,
        })
        html = self.procesar()
        textos = _textos_do_zip(self.zips_de_saida()[0])
        self.assertEqual([n for n in textos if not n.endswith(".md")], ["nota.anonimizado.txt"])
        self.assertSenDatosReais("".join(textos.values()), "o zip de saída")
        self.assertIn("dentro/Expediente Carballo.zip", html)
        self.assertIn(".zip dentro doutro .zip", html)

    def test_rutas_con_puntos_non_saen_do_cartafol(self):
        _zip(self.cartafol / "malo.zip", {
            "../../fora/Xosé Carballo Portela.txt": TEXTO_XOSE,
            "/absoluta/nota.txt": TEXTO_MANUEL,
            "C:/unidade/outra.txt": TEXTO_MANUEL,
            "..\\..\\barras\\informe.txt": TEXTO_MANUEL,
        })
        self.procesar()
        textos = _textos_do_zip(self.zips_de_saida()[0])
        self.assertEqual(len(textos), 4, sorted(textos))
        for nome in textos:
            partes = nome.split("/")
            self.assertNotIn("..", partes, nome)
            self.assertFalse(nome.startswith("/") or ":" in partes[0] or "\\" in nome, nome)
            self.assertSenDatosReais(nome, "o nome dunha entrada")
        self.assertTrue(any(n.startswith("fora/") for n in textos), sorted(textos))
        self.assertFalse((self.dir / "fora").exists())

    def test_limite_de_descompresion_compartido_no_lote(self):
        _zip(self.cartafol / "a.zip", {"a.txt": TEXTO_MANUEL})
        _zip(self.cartafol / "b.zip", {"Xosé Carballo Portela.txt": TEXTO_XOSE})
        with mock.patch.object(pipeline, "MAX_DESCOMPRIMIDO", len(TEXTO_MANUEL.encode()) + 10):
            html = self.procesar()
        self.assertEqual(len(self.zips_de_saida()), 1)
        self.assertIn("b.zip", html)
        self.assertIn("demasiado grande", html)

    def test_un_zip_xa_anonimizado_non_se_volve_procesar(self):
        _zip(self.cartafol / "exp.zip", {"nota.txt": TEXTO_MANUEL})
        self.procesar(saida=False)  # sae canda o orixinal
        self.assertEqual(len(list(self.cartafol.glob("*.anonimizado.zip"))), 1)
        soportados, omitidos = listar_ficheiros_soportados(str(self.cartafol))
        self.assertEqual([Path(s).name for s in soportados], ["exp.zip"])
        self.assertEqual([Path(o).name for o in omitidos], ["exp.anonimizado.zip"])
        self.procesar(saida=False)
        self.assertEqual(list(self.cartafol.glob("*.anonimizado.anonimizado*")), [])

    def test_modo_revisar_anonimiza_o_zip_en_automatico_e_dio(self):
        self._expediente()
        html = self.procesar(modo="revisar")
        self.assertEqual(len(web.SESIONS), 1)  # demanda.txt, para revisar
        self.assertEqual(len(self.zips_de_saida()), 1)
        self.assertIn("1 ficheiro(s) .zip anonimizado(s) en automático", html)
        self.assertIn("1 documento(s) procesado(s)", html)

    def test_zip_dado_directamente_na_xanela(self):
        ruta = _zip(self.dir / "Expediente Xosé Carballo Portela.zip", {"nota.txt": TEXTO_XOSE})
        for modo in ("automatico", "revisar"):
            with self.subTest(modo=modo):
                for vello in self.saida.glob("*"):
                    vello.unlink()
                self.procesar(ruta, modo=modo)
                zips = self.zips_de_saida()
                self.assertEqual(len(zips), 1)
                self.assertSenDatosReais(zips[0].name, "o nome do zip")
                self.assertSenDatosReais("".join(_textos_do_zip(zips[0]).values()), "o zip")

    def test_explorador_marca_o_zip_coma_soportado(self):
        _zip(self.cartafol / "exp.zip", {"nota.txt": TEXTO_MANUEL})
        datos = explorador.listar(str(self.cartafol))
        self.assertTrue(next(e for e in datos["entradas"] if e["nome"] == "exp.zip")["soportado"])


class TestTraballoConZips(_Base):
    def _traballo(self, modo="automatico"):
        traballo, erro = web._preparar_traballo(str(self.cartafol), self.rexistro_dir, str(self.saida), modo)
        self.assertIsNone(erro)
        return traballo

    def test_barra_de_progreso_con_zip(self):
        _zip(self.cartafol / "a.zip", {"Xosé Carballo Portela.txt": TEXTO_XOSE})
        (self.cartafol / "b.txt").write_text(TEXTO_MANUEL, encoding="utf-8")
        traballo = self._traballo()
        web._executar_traballo(traballo)
        self.assertEqual(traballo["estado"], "rematado")
        self.assertEqual((traballo["feitos"], len(traballo["ficheiros"])), (2, 2))
        web.TRABALLOS[traballo["id"]] = traballo
        html = self.client.get(f"/traballo/{traballo['id']}/resultado").get_data(as_text=True)
        self.assertIn("2 de 2", html)
        self.assertIn("dentro do .zip", html)
        self.assertEqual(len(self.zips_de_saida()), 1)

    def test_cancelar_despois_dun_zip_escribeo_e_non_deixa_temporais(self):
        _zip(self.cartafol / "a.zip", {"Xosé Carballo Portela.txt": TEXTO_XOSE})
        (self.cartafol / "b.txt").write_text(TEXTO_MANUEL, encoding="utf-8")
        traballo = self._traballo()
        preparados = []
        orixinal = pipeline.preparar_zip

        def preparar_e_cancelar(*a, **k):
            preparados.append(orixinal(*a, **k))
            traballo["cancelar"].set()
            return preparados[-1]

        with mock.patch.object(web, "preparar_zip", preparar_e_cancelar):
            web._executar_traballo(traballo)
        self.assertEqual(traballo["estado"], "cancelado")
        zips = self.zips_de_saida()
        self.assertEqual(len(zips), 1)
        self.assertSenDatosReais(zips[0].name + "".join(_textos_do_zip(zips[0])), "o zip")
        self.assertEqual(list(self.saida.glob("b*")), [])
        self.assertFalse(preparados[0].dir.exists())


class TestFasesDoZip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_erro_ao_escribir_non_deixa_zip_a_medias(self):
        entrada = _zip(self.dir / "e.zip", {"a.txt": TEXTO_XOSE, "b.txt": TEXTO_MANUEL})
        saida = self.dir / "e.anonimizado.zip"
        preparado = preparar_zip(str(entrada), self.rexistro)
        try:
            with mock.patch.object(pipeline, "_anonimizar_cartafoles_ruta", side_effect=RuntimeError("proba")):
                with self.assertRaises(RuntimeError):
                    gardar_zip_preparado(preparado, str(saida), self.rexistro)
        finally:
            preparado.limpar()
        self.assertFalse(saida.exists())
        self.assertFalse(preparado.dir.exists())
        self.assertEqual(list(self.dir.glob(".anonimizando-*")), [])

    def test_cabeceira_mentirosa_rexeitase(self):
        """O directorio central di 10 bytes e hai 5000: non se descomprime
        máis do declarado nin do límite, e o zip rexéitase enteiro."""
        datos = bytearray(_zip(self.dir / "orixe.zip", {"a.txt": "x" * 5000}).read_bytes())
        central = datos.index(b"PK\x01\x02")
        datos[central + 24:central + 28] = (10).to_bytes(4, "little")
        entrada = self.dir / "e.zip"
        entrada.write_bytes(bytes(datos))
        with self.assertRaises(ZipRexeitado) as e:
            preparar_zip(str(entrada), self.rexistro, limite=LimiteDescompresion(1000))
        self.assertIn(e.exception.motivo, ("zip_demasiado_grande", "zip_ilexible"))

    def test_cabeceira_maior_co_limite_rexeitase_sen_descomprimir(self):
        entrada = _zip(self.dir / "e.zip", {"a.txt": "x" * 5000})
        limite = LimiteDescompresion(1000)
        with self.assertRaises(ZipRexeitado) as e:
            preparar_zip(str(entrada), self.rexistro, limite=limite)
        self.assertEqual(e.exception.motivo, "zip_demasiado_grande")
        self.assertEqual(limite.queda, 1000)

    def test_documento_roto_dentro_queda_fora_e_os_demais_saen(self):
        entrada = _zip(self.dir / "e.zip", {"roto.pdf": b"%PDF-1.4 roto", "nota.txt": TEXTO_MANUEL})
        resultado = pipeline.anonimizar_zip(str(entrada), str(self.dir / "s.zip"), self.rexistro)
        self.assertEqual(resultado["motivos"], {"roto.pdf": "documento_ilexible"})
        with zipfile.ZipFile(self.dir / "s.zip") as z:
            self.assertEqual(z.namelist(), ["nota.anonimizado.txt"])

    def test_nomes_iguais_despois_de_anonimizar_non_se_pisan(self):
        entrada = _zip(self.dir / "e.zip", {
            "Xosé Carballo Portela.txt": TEXTO_XOSE, "xosé carballo portela.TXT": TEXTO_XOSE,
        })
        resultado = pipeline.anonimizar_zip(str(entrada), str(self.dir / "s.zip"), self.rexistro)
        saidas = list(resultado["saidas"].values())
        self.assertEqual(len({s.casefold() for s in saidas}), 2, saidas)

    def test_persoa_que_aparece_no_segundo_documento_do_zip(self):
        """k>1 dentro do zip: o cartafol interno nomea a unha persoa que só
        aparece no SEGUNDO documento. Se os nomes se fixasen tras o primeiro
        documento, o escrito levaría un código novo marcado coma posible
        homónimo; debe saír igual ca o mesmo escrito solto."""
        entrada = _zip(self.dir / "Expediente Xosé Carballo Portela.zip", {
            "Xosé Carballo Portela/1 indice.txt": "Índice do expediente, sen nomes.",
            "Xosé Carballo Portela/2 escrito.txt": TEXTO_XOSE,
        })
        resultado = pipeline.anonimizar_zip(str(entrada), str(self.dir / "s.zip"), self.rexistro)
        informe = resultado["ficheiros"]["Xosé Carballo Portela/2 escrito.txt"]
        self.assertEqual([p["marcado_para_revision"] for p in informe["persoas"]], [False])
        with zipfile.ZipFile(self.dir / "s.zip") as z:
            textos = {n: z.read(n).decode("utf-8") for n in z.namelist()}
        escrito = next(t for n, t in textos.items() if n.endswith("2 escrito.anonimizado.txt"))
        solto_rexistro = RexistroCorrespondencias(str(self.dir / "rex_solto"))
        solto = self.dir / "escrito.txt"
        solto.write_text(TEXTO_XOSE, encoding="utf-8")
        texto_solto, informe_solto = pipeline.anonimizar_e_gardar(
            str(solto), str(self.dir / "escrito.anonimizado.txt"), solto_rexistro)
        self.assertEqual(escrito, texto_solto)
        self.assertEqual([p["marcado_para_revision"] for p in informe_solto["persoas"]], [False])
        codigo = re.search(r"PERSOA_\d+", escrito).group(0)
        self.assertEqual({n.split("/")[0] for n in textos}, {codigo})

    def test_fallo_ao_escribir_non_pisa_un_zip_completo_anterior(self):
        entrada = _zip(self.dir / "e.zip", {"a.txt": TEXTO_XOSE})
        saida = self.dir / "e.anonimizado.zip"
        saida.write_bytes(b"ZIP COMPLETO ANTERIOR")
        preparado = preparar_zip(str(entrada), self.rexistro)
        try:
            with mock.patch.object(pipeline, "_anonimizar_cartafoles_ruta", side_effect=RuntimeError("proba")):
                with self.assertRaises(RuntimeError):
                    gardar_zip_preparado(preparado, str(saida), self.rexistro)
        finally:
            preparado.limpar()
        self.assertEqual(saida.read_bytes(), b"ZIP COMPLETO ANTERIOR")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir() if p.is_file()), ["e.anonimizado.zip", "e.zip"])

    def test_permissionerror_ao_substituir_non_deixa_temporal_nin_pisa_o_anterior(self):
        """Windows: o zip anterior está aberto noutro programa e o
        renomeamento falla con PermissionError (tamén despois dos reintentos)."""
        entrada = _zip(self.dir / "e.zip", {"a.txt": TEXTO_XOSE})
        saida = self.dir / "e.anonimizado.zip"
        saida.write_bytes(b"ZIP COMPLETO ANTERIOR")
        preparado = preparar_zip(str(entrada), self.rexistro)
        try:
            with mock.patch.object(pipeline, "substituir_con_reintentos",
                                   side_effect=PermissionError(13, "aberto noutro programa")):
                with self.assertRaises(PermissionError):
                    gardar_zip_preparado(preparado, str(saida), self.rexistro)
        finally:
            preparado.limpar()
        self.assertEqual(saida.read_bytes(), b"ZIP COMPLETO ANTERIOR")
        self.assertEqual(list(self.dir.glob(".anonimizando-*")), [])

    def test_borrar_o_temporal_reintenta_tras_permissionerror(self):
        entrada = _zip(self.dir / "e.zip", {"a.txt": TEXTO_XOSE})
        preparado = preparar_zip(str(entrada), self.rexistro)
        orixinal = Path.unlink
        fallos = []

        def unlink_que_falla_unha_vez(ruta, *a, **k):
            if ruta.name.startswith(".anonimizando-") and not fallos:
                fallos.append(ruta)
                raise PermissionError(32, "usado por outro proceso")
            return orixinal(ruta, *a, **k)

        try:
            with mock.patch.object(pipeline, "substituir_con_reintentos", side_effect=PermissionError(32, "x")), \
                    mock.patch.object(Path, "unlink", unlink_que_falla_unha_vez), \
                    mock.patch.object(pipeline.time, "sleep"):
                with self.assertRaises(PermissionError):
                    gardar_zip_preparado(preparado, str(self.dir / "s.zip"), self.rexistro)
        finally:
            preparado.limpar()
        self.assertEqual(len(fallos), 1)
        self.assertEqual(list(self.dir.glob(".anonimizando-*")), [])
        self.assertFalse((self.dir / "s.zip").exists())

    def test_permissionerror_no_lote_da_xanela_avisa_e_segue(self):
        cartafol = self.dir / "c"
        cartafol.mkdir()
        _zip(cartafol / "a.zip", {"a.txt": TEXTO_XOSE})
        (cartafol / "b.txt").write_text(TEXTO_MANUEL, encoding="utf-8")
        saida = self.dir / "saida"
        traballo, _ = web._preparar_traballo(str(cartafol), str(self.dir / "rex"), str(saida), "automatico")
        with mock.patch.object(pipeline, "substituir_con_reintentos",
                               side_effect=PermissionError(13, "aberto noutro programa")):
            web._executar_traballo(traballo)
        self.assertEqual(traballo["estado"], "rematado")
        self.assertEqual([Path(e["ruta"]).name for e in traballo["erros"]], ["a.zip"])
        self.assertEqual(sorted(p.name for p in saida.iterdir()), ["b.anonimizado.txt"])


class TestCliZip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _cli(self, *args) -> tuple:
        saida = io.StringIO()
        erros = io.StringIO()
        codigo = 0
        with mock.patch.object(sys, "argv", ["anonimizador", *args]), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erros):
            try:
                cli.main()
            except SystemExit as e:
                codigo = e.code
        return codigo, saida.getvalue(), erros.getvalue()

    def test_omitidos_co_motivo_e_nome_do_zip_anonimizado(self):
        entrada = _zip(self.dir / "Expediente Xosé Carballo Portela.zip", {
            "nota.txt": TEXTO_XOSE, "plano.dwg": b"\x00", "outro.zip": b"PK",
        })
        codigo, saida, _ = self._cli("anonimizar", str(entrada), "--rexistro", str(self.dir / "rex"))
        self.assertEqual(codigo, 0)
        self.assertIn("plano.dwg -- formato que non se pode analizar", saida)
        self.assertIn("outro.zip -- .zip dentro doutro .zip", saida)
        zips = list(self.dir.glob("*.anonimizado.zip"))
        self.assertEqual(len(zips), 1)
        for real in REAIS:
            self.assertNotIn(real.casefold(), zips[0].name.casefold())

    def test_zip_danado_sae_con_erro_e_sen_escribir_nada(self):
        entrada = self.dir / "roto.zip"
        entrada.write_bytes(b"non e un zip")
        codigo, _, erros = self._cli("anonimizar", str(entrada), "--rexistro", str(self.dir / "rex"))
        self.assertEqual(codigo, 1)
        self.assertIn("danado", erros)
        self.assertEqual(list(self.dir.glob("*.anonimizado*")), [])


def PurePath_parent(nome: str) -> str:
    return nome.rsplit("/", 1)[0] if "/" in nome else ""


if __name__ == "__main__":
    unittest.main()
