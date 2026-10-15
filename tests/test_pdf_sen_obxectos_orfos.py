"""Fallo de seguridade crítico atopado probando contra documentos reais
escaneados do despacho: sen "garbage collection" ao gardar, PyMuPDF deixa
o obxecto de IMAXE ORIXINAL (sen redactar) coma "orfo" dentro do propio
ficheiro PDF -- xa non o amosa a páxina nin ningún visor normal, pero
segue a ser extraíble directamente do ficheiro (`fitz.Pixmap(doc, xref)`)
por calquera ferramenta que percorra o PDF. Un síntoma doado de detectar
sen abrir o contido: o ficheiro de saída queda moitísimo máis grande có
agardado (nun caso real, 6,8 MB -> 346 MB).

Este test verifica as DÚAS cousas: que non quede ningún obxecto de imaxe
sen usar no PDF final, e que ningunha imaxe que quede (usada ou non)
conteña o texto orixinal ao voltar a facerlle OCR.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_e_gardar
from anonimizador.registry import RexistroCorrespondencias

_TESSERACT_DISPOÑIBLE = shutil.which("tesseract") is not None


def _crear_pdf_escaneado(ruta: Path, texto: str) -> None:
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


@unittest.skipUnless(_TESSERACT_DISPOÑIBLE, "Tesseract non está instalado neste ordenador")
class TestSenObxectosOrfosTrasRedaccion(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_non_queda_ningun_obxecto_de_imaxe_sen_usar(self):
        """Un obxecto de imaxe considérase EN USO se (a) algunha páxina o
        referencia directamente, OU (b) algún outro obxecto do documento o
        referencia (ex. de "SMask"/máscara de transparencia doutra imaxe --
        caso real atopado nun documento real: a imaxe "orfa" resultou ser
        unha máscara lexítima, non o orixinal sen redactar; confirmalo esixe
        percorrer TÓDOLOS obxectos, non só as páxinas)."""
        entrada = self.dir / "escaneado.pdf"
        _crear_pdf_escaneado(entrada, "Manuel Ferrandiz Salcedo DNI 30014811Z")
        saida = self.dir / "escaneado.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        with fitz.open(str(saida)) as doc:
            todos_os_obxectos_de_imaxe = {
                xref for xref in range(1, doc.xref_length())
                if "Image" in str(doc.xref_get_key(xref, "Subtype") or "")
            }
            referenciadas = set()
            for pagina in doc:
                referenciadas |= {xref for xref, *_ in pagina.get_images()}
            for xref in range(1, doc.xref_length()):
                try:
                    contido = doc.xref_object(xref, compressed=False)
                except Exception:
                    continue
                for candidato in todos_os_obxectos_de_imaxe:
                    if xref != candidato and f"{candidato} 0 R" in contido:
                        referenciadas.add(candidato)

        orfas_reais = todos_os_obxectos_de_imaxe - referenciadas
        self.assertEqual(
            orfas_reais, set(),
            "hai obxectos de imaxe no PDF final que ningunha páxina nin outro "
            "obxecto usa -- poderían ser a imaxe orixinal SEN redactar, aínda "
            "recuperable do ficheiro",
        )

    def test_ningunha_imaxe_que_quede_ten_o_texto_orixinal(self):
        """Aínda que só quedase UNHA imaxe (a esperada), volve confirmar
        con OCR que é a redactada, non a orixinal."""
        import pytesseract
        from PIL import Image

        entrada = self.dir / "escaneado.pdf"
        _crear_pdf_escaneado(entrada, "Manuel Ferrandiz Salcedo DNI 30014811Z")
        saida = self.dir / "escaneado.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        with fitz.open(str(saida)) as doc:
            for xref in range(1, doc.xref_length()):
                if "Image" not in str(doc.xref_get_key(xref, "Subtype") or ""):
                    continue
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                imaxe = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                texto_ocr = pytesseract.image_to_string(imaxe, lang="spa")
                self.assertNotIn("Manuel", texto_ocr)
                self.assertNotIn("Ferrandiz", texto_ocr)
                self.assertNotIn("30014811", texto_ocr)

    def test_ficheiro_final_non_e_moito_maior_có_orixinal(self):
        """Síntoma doado de vixiar: sen garbage collection, o ficheiro
        medra desproporcionadamente (caso real: 6,8 MB -> 346 MB)."""
        entrada = self.dir / "escaneado.pdf"
        _crear_pdf_escaneado(entrada, "Manuel Ferrandiz Salcedo DNI 30014811Z")
        saida = self.dir / "escaneado.anonimizado.pdf"
        anonimizar_e_gardar(str(entrada), str(saida), self.rexistro)

        tamano_orixinal = entrada.stat().st_size
        tamano_final = saida.stat().st_size
        self.assertLess(
            tamano_final, tamano_orixinal * 3,
            f"o PDF final ({tamano_final} bytes) é desproporcionadamente maior "
            f"có orixinal ({tamano_orixinal} bytes) -- probable obxecto orfo sen limpar",
        )


if __name__ == "__main__":
    unittest.main()
