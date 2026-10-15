"""Conservación do formato E EXTENSIÓN orixinais en PDF (informe: "que
sempre manteña o formato e extensión do arquivo orixinal"), tanto con
texto nativo coma escaneado (`pdf_estrutura.py`).

O máis importante a verificar en TODOS os casos: o texto orixinal ten que
quedar REALMENTE eliminado do PDF final -- non abonda con que non se vexa,
ten que estar ausente tamén da capa de texto extraíble (e, nunha páxina
escaneada, dos propios píxeles: verificado facendo OCR de novo sobre a
imaxe final). É o mesmo tipo de erro crítico xa atopado antes neste
proxecto (CSV, número de colexiado...) pero aplicado a PDF.
"""

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import web
from anonimizador.pipeline import (
    anonimizar_e_gardar,
    anonimizar_texto_detallado,
    anonimizar_zip,
    cargar_documento_estruturado,
    gardar_documento_estruturado,
    ruta_saida_por_defecto,
)
from anonimizador.pdf_estrutura import SEPARADOR_PAXINAS, cargar_pdf_estruturado, gardar_pdf_estruturado
from anonimizador.registry import RexistroCorrespondencias

_TESSERACT_DISPOÑIBLE = shutil.which("tesseract") is not None


def _crear_pdf_con_texto(ruta: Path, paxinas: list) -> None:
    documento = fitz.open()
    for texto in paxinas:
        paxina = documento.new_page()
        paxina.insert_text((72, 100), texto, fontsize=12)
    documento.save(str(ruta))
    documento.close()


def _crear_pdf_escaneado(ruta: Path, texto: str) -> None:
    """Simula unha páxina escaneada: o texto vai debuxado como imaxe (non
    como capa de texto seleccionable), coma un escáner real."""
    documento = fitz.open()
    paxina = documento.new_page(width=900, height=300)
    imaxe_doc = fitz.open()
    imaxe_paxina = imaxe_doc.new_page(width=900, height=300)
    imaxe_paxina.insert_text((30, 100), texto, fontsize=28)
    pix_texto = imaxe_paxina.get_pixmap()
    paxina.insert_image(fitz.Rect(0, 0, 900, 300), pixmap=pix_texto)
    documento.save(str(ruta))
    documento.close()
    imaxe_doc.close()


def _texto_completo(ruta_pdf) -> str:
    with fitz.open(str(ruta_pdf)) as doc:
        return "".join(p.get_text() for p in doc)


def _png_qr(contido: str, tamano_modulo: int = 8, marxe_modulos: int = 4) -> bytes:
    """Xera un QR real coma PNG usando SÓ `cv2.QRCodeEncoder` (sen
    depender da libraría `qrcode`, que non fai falta en produción -- a
    app só detecta e redacta, nunca xera QR)."""
    modulos = cv2.QRCodeEncoder.create().encode(contido)
    con_marxe = np.pad(modulos, marxe_modulos, constant_values=255)
    grande = np.kron(con_marxe, np.ones((tamano_modulo, tamano_modulo), dtype=np.uint8))
    return cv2.imencode(".png", grande)[1].tobytes()


def _ten_codigo_detectable(ruta_pdf) -> bool:
    with fitz.open(str(ruta_pdf)) as doc:
        escala = 300 / 72
        for pagina in doc:
            pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), colorspace=fitz.csGRAY)
            imaxe = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            if cv2.QRCodeDetector().detectMulti(imaxe)[0]:
                return True
    return False


class TestPdfNativoConservaFormato(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_saida_por_defecto_mantén_a_extension_pdf(self):
        self.assertEqual(ruta_saida_por_defecto("/casos/escrito.pdf"), "/casos/escrito.anonimizado.pdf")

    def test_anonimizar_e_gardar_produce_un_pdf_valido(self):
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presenta este escrito.",
        ])
        saida = self.dir / "escrito.anonimizado.pdf"

        texto_anon, informe = anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        self.assertTrue(saida.exists())
        texto_final = _texto_completo(saida)
        self.assertNotIn("Manuel", texto_final)
        self.assertNotIn("Ferrándiz", texto_final)
        self.assertNotIn("30014811", texto_final)
        self.assertIn("PERSOA_", texto_final)

    def test_multiples_paxinas_cada_substitucion_na_paxina_correcta(self):
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Primeira páxina: Manuel Ferrándiz Salcedo declarou.",
            "Segunda páxina: Rita Martorell Vilela tamén declarou.",
        ])
        saida = self.dir / "escrito.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        with fitz.open(str(saida)) as doc:
            self.assertEqual(doc.page_count, 2)
            texto_pax1 = doc[0].get_text()
            texto_pax2 = doc[1].get_text()

        self.assertIn("PERSOA_", texto_pax1)
        self.assertNotIn("Manuel", texto_pax1)
        self.assertNotIn("Rita", texto_pax1)  # non se debe filtrar á páxina 1

        self.assertIn("PERSOA_", texto_pax2)
        self.assertNotIn("Rita", texto_pax2)
        self.assertNotIn("Manuel", texto_pax2)  # nin a segunda ao contrario

    def test_conserva_texto_non_sensible_ao_redor(self):
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Manuel Ferrándiz Salcedo acudiu á vista sinalada onte pola tarde.",
        ])
        saida = self.dir / "escrito.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        texto_final = _texto_completo(saida)
        self.assertIn("acudiu", texto_final)
        self.assertIn("vista sinalada", texto_final)

    def test_edicion_manual_da_paxina_recae_en_reserva_sen_perder_o_texto(self):
        """Se o letrado edita o texto dunha páxina de xeito que xa non
        coincide coas substitucións orixinais, esa páxina redáctase enteira
        e reescríbese co texto editado -- perde formato pero non datos, e
        o orixinal sensible segue sen aparecer."""
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, [
            "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presenta este escrito.",
        ])
        texto, contexto = cargar_documento_estruturado(str(entrada))
        texto_anon, informe, substitucions = anonimizar_texto_detallado(texto, self.rexistro)

        texto_editado_a_man = texto_anon + " Engadido á man polo letrado."
        saida = self.dir / "escrito.editado.pdf"
        gardar_documento_estruturado(contexto, texto_editado_a_man, str(saida), substitucions)

        texto_final = _texto_completo(saida)
        self.assertNotIn("Manuel", texto_final)
        self.assertNotIn("30014811", texto_final)
        self.assertIn("Engadido", texto_final)

    def test_redacta_so_o_numero_mantendo_a_etiqueta_visible(self):
        """Patrón crítico xa atopado noutros formatos (README): "colegiado
        número"/CSV/"referencia" só deben perder a cifra, non a etiqueta
        que a acompaña -- ten que seguir a funcionar igual en PDF."""
        entrada = self.dir / "colexiado.pdf"
        _crear_pdf_con_texto(entrada, [
            "O informe foi asinado polo colegiado numero 2481 do colexio de Pontevedra.",
        ])
        saida = self.dir / "colexiado.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        texto_final = _texto_completo(saida)
        self.assertIn("colegiado", texto_final)
        self.assertIn("numero", texto_final)
        self.assertNotIn("2481", texto_final)
        self.assertIn("[COLEXIADO]", texto_final)

    def test_desaliñar_paxinas_lanza_valueerror(self):
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, ["Unha soa páxina de texto."])
        texto, contexto = cargar_documento_estruturado(str(entrada))
        saida = self.dir / "escrito.malo.pdf"
        texto_con_paxina_de_mais = "Unha soa páxina." + SEPARADOR_PAXINAS + "Outra páxina de máis."
        with self.assertRaises(ValueError):
            gardar_documento_estruturado(contexto, texto_con_paxina_de_mais, str(saida))

    def test_liña_en_branco_dentro_de_paxina_non_se_confunde_con_paxina_de_mais(self):
        """Proba estrutural do separador entre páxinas: se algunha vez un
        extractor de texto (nativo ou OCR) chegase a producir unha liña en
        branco DENTRO do texto da propia páxina (salto de parágrafo, moi
        habitual en cartas -- saúdo, corpo, sinatura), a conta de "páxinas"
        NON se debe confundir con esa liña en branco propia. É por iso que
        `SEPARADOR_PAXINAS` xa non é unha liña en branco a secas (`"\\n\\n"`)."""
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, ["Primeira páxina.", "Segunda páxina."])
        texto, contexto = cargar_documento_estruturado(str(entrada))
        contexto["paxinas"][0].texto += "\n\nParágrafo con liña en branco propia."
        texto_coa_liña_en_branco = SEPARADOR_PAXINAS.join(p.texto for p in contexto["paxinas"])

        saida = self.dir / "escrito.ok.pdf"
        gardar_pdf_estruturado(contexto, texto_coa_liña_en_branco, str(saida), [])
        self.assertTrue(saida.exists())


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "Tesseract non está instalado neste ordenador")
class TestPdfEscaneadoConservaFormato(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_redacta_tamen_os_pixeles_da_imaxe_non_so_o_texto_vectorial(self):
        import pytesseract
        from PIL import Image

        entrada = self.dir / "escaneado.pdf"
        _crear_pdf_escaneado(entrada, "Manuel Ferrandiz Salcedo DNI 30014811Z")
        saida = self.dir / "escaneado.anonimizado.pdf"

        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        self.assertEqual(Path(saida).suffix, ".pdf")

        with fitz.open(str(saida)) as doc:
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
            imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # verificación crítica: reOCR sobre a imaxe FINAL, non sobre o texto
        # vectorial -- confirma que os PÍXELES orixinais tamén desapareceron
        texto_reocr = pytesseract.image_to_string(imaxe, lang="spa")
        self.assertNotIn("Manuel", texto_reocr)
        self.assertNotIn("Ferrandiz", texto_reocr)
        self.assertNotIn("30014811", texto_reocr)


class TestPdfEnZip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_pdf_dentro_dun_zip_conserva_extension_e_formato(self):
        pdf_entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(pdf_entrada, ["Manuel Ferrándiz Salcedo presenta este escrito."])

        zip_entrada = self.dir / "expediente.zip"
        with zipfile.ZipFile(zip_entrada, "w") as zf:
            zf.write(str(pdf_entrada), arcname="escrito.pdf")

        zip_saida = self.dir / "expediente.anonimizado.zip"
        resultado = anonimizar_zip(str(zip_entrada), str(zip_saida), self.rexistro)

        self.assertNotIn("escrito.pdf", resultado["omitidos"])
        with zipfile.ZipFile(zip_saida) as zf:
            nomes = zf.namelist()
            self.assertIn("escrito.anonimizado.pdf", nomes)
            with tempfile.TemporaryDirectory() as d2:
                ruta_extraida = Path(d2) / "saida.pdf"
                ruta_extraida.write_bytes(zf.read("escrito.anonimizado.pdf"))
                texto_final = _texto_completo(ruta_extraida)
                self.assertNotIn("Manuel", texto_final)
                self.assertIn("PERSOA_", texto_final)


class TestPdfNaWeb(unittest.TestCase):
    def setUp(self):
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def test_fluxo_completo_dende_a_interface_web(self):
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, ["Manuel Ferrándiz Salcedo presenta este escrito."])

        resposta = self.client.post(
            "/procesar",
            data={"ruta": str(entrada), "rexistro": self.rexistro_dir},
            follow_redirects=True,
        )
        sid = resposta.request.path.rsplit("/", 1)[-1]
        sesion = web.SESIONS[sid]
        self.assertIsNotNone(sesion["contexto"])
        self.assertEqual(sesion["contexto"]["tipo"], "pdf")

        conf = self.client.post(
            f"/revisar/{sid}/confirmar",
            data={"texto_final": sesion["texto_anonimizado"], "rexistro_dir": self.rexistro_dir},
        )
        self.assertEqual(conf.status_code, 200)

        ruta_saida = entrada.with_suffix("").as_posix() + ".anonimizado.pdf"
        self.assertTrue(Path(ruta_saida).exists())
        texto_final = _texto_completo(ruta_saida)
        self.assertNotIn("Manuel", texto_final)
        self.assertIn("PERSOA_", texto_final)


class TestCodigosQrEBarras(unittest.TestCase):
    """QR e códigos de barras: elemento VISUAL, independente de se hai
    texto nativo ou é escaneado (ver `pdf_estrutura._redactar_codigos_da_paxina`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_qr_de_verificacion_queda_redactado(self):
        entrada = self.dir / "escrito.pdf"
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), "Manuel Ferrándiz Salcedo presentou este escrito.")
        pagina.insert_image(fitz.Rect(400, 650, 480, 730), stream=_png_qr("CSV:VERIFICACION-REAL"))
        documento.save(str(entrada))
        documento.close()
        self.assertTrue(_ten_codigo_detectable(entrada))  # confirma que o QR de proba é real

        saida = self.dir / "escrito.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        self.assertEqual(saida.suffix, ".pdf")
        self.assertFalse(_ten_codigo_detectable(saida))
        texto_final = _texto_completo(saida)
        self.assertIn("[CODIGO]", texto_final)
        self.assertNotIn("Manuel Ferrándiz Salcedo", texto_final)

    def test_documento_sen_qr_non_se_altera(self):
        """Non debe haber falsos positivos en documentos normais sen
        ningún código -- a páxina non debe cambiar por esta pasada."""
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, ["Manuel Ferrándiz Salcedo presentou este escrito."])
        saida = self.dir / "escrito.anonimizado.pdf"

        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        texto_final = _texto_completo(saida)
        self.assertNotIn("[CODIGO]", texto_final)
        self.assertIn("PERSOA_", texto_final)


def _engadir_widget_sinatura(pagina: "fitz.Page", nome: str = "Signature1") -> None:
    widget = fitz.Widget()
    widget.field_name = nome
    widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    widget.rect = fitz.Rect(72, 650, 300, 720)
    pagina.add_widget(widget)


def _ten_widget_sinatura(ruta_pdf) -> bool:
    with fitz.open(str(ruta_pdf)) as doc:
        for pagina in doc:
            if any(w.field_type_string == "Signature" for w in (pagina.widgets() or [])):
                return True
    return False


class TestSinaturaDixital(unittest.TestCase):
    """Caso real atopado nun informe técnico asinado dixitalmente: o selo
    visual da sinatura (DNI e nome completo do asinante) vive nun WIDGET
    de formulario, non no texto da páxina -- invisible tanto para
    `recognizers.py` coma para `ner.py` (ver
    `pdf_estrutura._eliminar_sinaturas_dixitais_da_paxina`)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_widget_de_sinatura_elimínase_e_deixa_etiqueta(self):
        entrada = self.dir / "informe.pdf"
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), "Manuel Ferrándiz Salcedo presentou este escrito.")
        _engadir_widget_sinatura(pagina)
        documento.save(str(entrada))
        documento.close()
        self.assertTrue(_ten_widget_sinatura(entrada))  # confirma que o widget de proba é real

        saida = self.dir / "informe.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        self.assertFalse(_ten_widget_sinatura(saida))
        texto_final = _texto_completo(saida)
        self.assertIn("[SINATURA_DIXITAL]", texto_final)
        self.assertNotIn("Manuel Ferrándiz Salcedo", texto_final)

    def test_widget_de_sinatura_con_rect_baleiro_non_rompe(self):
        """Caso real: un certificado de apoderamento xudicial ten campos
        de sinatura SEN selo visual ningún -- rect de área cero,
        validación puramente electrónica (PyMuPDF nin sequera deixa crear
        un widget novo así, `_validate` esixe un rect real -- por iso se
        crea normal e se sobrescribe o `/Rect` a baixo nivel, coma o
        seguiría facendo o software que xerou o PDF orixinal).
        `insert_textbox` esixe un rectángulo non baleiro, así que
        insertalo aí facía fallar TODO o proceso de anonimización."""
        entrada = self.dir / "certificado.pdf"
        documento = fitz.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 100), "Manuel Ferrándiz Salcedo presentou este escrito.")
        _engadir_widget_sinatura(pagina)
        documento.save(str(entrada))
        documento.close()

        doc_baixo_nivel = fitz.open(str(entrada))
        widget = list(doc_baixo_nivel[0].widgets())[0]
        doc_baixo_nivel.xref_set_key(widget.xref, "Rect", "[0 0 0 0]")
        doc_baixo_nivel.saveIncr()
        doc_baixo_nivel.close()

        saida = self.dir / "certificado.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)  # non debe lanzar

        self.assertFalse(_ten_widget_sinatura(saida))
        texto_final = _texto_completo(saida)
        self.assertNotIn("Manuel Ferrándiz Salcedo", texto_final)

    def test_documento_sen_sinatura_non_se_altera(self):
        """Non debe haber falsos positivos en documentos normais sen
        ningún widget de sinatura."""
        entrada = self.dir / "escrito.pdf"
        _crear_pdf_con_texto(entrada, ["Manuel Ferrándiz Salcedo presentou este escrito."])
        saida = self.dir / "escrito.anonimizado.pdf"

        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        texto_final = _texto_completo(saida)
        self.assertNotIn("[SINATURA_DIXITAL]", texto_final)
        self.assertIn("PERSOA_", texto_final)


if __name__ == "__main__":
    unittest.main()
