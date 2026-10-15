"""Caso real atopado nunha táboa densa dun documento escaneado (páxina 5
dun burofax): algunhas palabras tiñan un bounding box de OCR erróneo moito
maior có resto da liña, e o código de substitución inseríase con ese
tamaño de letra disparatado, solapando e facendo ilexibles as celas
veciñas.

O primeiro intento de arranxo (limitar ao tamaño "típico" de TODA a
páxina, mediana global) creou unha regresión nun documento distinto: unha
cabeceira grande LEXÍTIMA (un código de expediente en letra moi grande,
illado, nunha portada) quedaba encollida ao tamaño do corpo de texto,
porque a mediana global estaba dominada por texto pequeno.

`_altura_veciña` arranxa isto mirando só as palabras VECIÑAS (preto
verticalmente) da que se vai substituír: unha cabeceira illada non ten
veciñas abondas para comparar (non se limita), mentres que un bounding
box anómalo nunha táboa densa si as ten (e detéctase o anómalo).

O outro erro de tamaño de letra, atopado nunha auditoría (A23), vai
tamén aquí: na RESERVA de páxina completa (a que se usa cando o letrado
editou o texto a man) o texto reescribíase sempre a 11 puntos, e cando
non collía `insert_textbox` non escribía NADA -- a páxina, xa redactada,
quedaba en branco sen aviso ningún.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pdf_estrutura import (
    _PalabraPaxina,
    _altura_veciña,
    _TAMANO_RESERVA,
    _TAMANO_RESERVA_MINIMO,
    _tamano_que_cabe,
    cargar_pdf_estruturado,
    gardar_pdf_estruturado,
)
from anonimizador.pipeline import anonimizar_texto_detallado
from anonimizador.registry import RexistroCorrespondencias


def _palabra(x0, y0, x1, y1):
    return _PalabraPaxina(inicio=0, fin=0, rect=(x0, y0, x1, y1))


class TestAlturaVeciña(unittest.TestCase):
    def test_bbox_anomalo_en_taboa_densa_detectase_pola_veciñanza(self):
        """Moitas palabras normais (altura 10) preto en vertical dunha
        anómala (altura 80, o bug real de OCR) -- a veciñanza debe reportar
        o tamaño normal, non o anómalo."""
        veciñas = [_palabra(x, 100, x + 20, 110) for x in range(0, 400, 25)]
        anomala = _palabra(150, 60, 170, 140)  # altura 80, moito máis grande
        palabras = veciñas + [anomala]

        resultado = _altura_veciña(palabras, anomala.rect, excluir=frozenset({id(anomala)}))

        self.assertIsNotNone(resultado)
        self.assertAlmostEqual(resultado, 10.0, places=1)

    def test_cabeceira_illada_e_grande_non_se_limita(self):
        """Sen veciñas abondas preto (a cabeceira está soa nunha portada),
        non hai referencia fiable -- debe devolver None (non limitar)."""
        cabeceira = _palabra(50, 50, 300, 130)  # altura 80, ISOLADA
        # As únicas outras palabras da páxina están moi lonxe verticalmente.
        lonxanas = [_palabra(x, 600, x + 20, 610) for x in range(0, 200, 25)]
        palabras = [cabeceira] + lonxanas

        resultado = _altura_veciña(palabras, cabeceira.rect, excluir=frozenset({id(cabeceira)}))

        self.assertIsNone(resultado)

    def test_a_propia_palabra_non_contamina_a_súa_propia_mostra(self):
        """Bug atopado e arranxado: comparar por posición (`rect ==
        rect_alvo`) non exclúe a palabra propia cando `rect_alvo` é a caixa
        UNIÓN de varias palabras substituídas (case non coincide con
        ningún rect individual) -- hai que excluír por IDENTIDADE."""
        veciñas = [_palabra(x, 100, x + 20, 110) for x in range(0, 400, 25)]
        # Unha palabra propia que, por casualidade, comparte rect cunha veciña.
        propia = _palabra(0, 100, 20, 110)
        palabras = veciñas + [propia]

        sen_excluir = _altura_veciña(palabras, propia.rect)
        con_exclusion = _altura_veciña(palabras, propia.rect, excluir=frozenset({id(propia)}))

        # En ambos casos a mostra é maioritariamente veciñas normais, así
        # que aquí o resultado non cambia -- mais confirma que non falla.
        self.assertAlmostEqual(sen_excluir, 10.0, places=1)
        self.assertAlmostEqual(con_exclusion, 10.0, places=1)

    def test_menos_de_tres_veciñas_non_da_referencia_fiable(self):
        alvo = _palabra(100, 100, 120, 110)
        soamente_dúas = [_palabra(0, 100, 20, 110), _palabra(200, 100, 220, 110)]
        palabras = [alvo] + soamente_dúas

        resultado = _altura_veciña(palabras, alvo.rect, excluir=frozenset({id(alvo)}))

        self.assertIsNone(resultado)


class TestTamanoDaReservaDePaxinaCompleta(unittest.TestCase):
    """A23: a páxina rehecha tras editar o texto a man non pode quedar en
    branco porque o texto non colla no tamaño de letra de sempre."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def _pdf_denso(self, ruta: Path, liñas: int = 76) -> None:
        """A páxina que destapou o erro: moitas liñas a 8 puntos -- o
        mesmo texto a 11 xa non colle na caixa."""
        documento = fitz.open()
        pagina = documento.new_page()
        y = 20
        for i in range(liñas):
            if i == 3:
                texto = f"DEMANDANTE: Manuel Ferrandiz Salcedo, DNI 30014811Z."
            else:
                texto = f"Liña {i:02d}: actuacion do expediente con texto de recheo para encher."
            pagina.insert_text((20, y), texto, fontsize=8)
            y += 10
        documento.save(str(ruta))
        documento.close()

    def test_paxina_densa_editada_a_man_non_queda_en_branco(self):
        entrada = self.dir / "denso.pdf"
        self._pdf_denso(entrada)
        texto, contexto = cargar_pdf_estruturado(str(entrada))
        texto_anon, _informe, substitucions = anonimizar_texto_detallado(
            texto, self.rexistro, contexto=contexto
        )
        editado = texto_anon.replace("actuacion do expediente", "actuación do expediente (revisado)")
        self.assertNotEqual(editado, texto_anon)  # confirma que cae na reserva

        saida = self.dir / "denso.anonimizado.pdf"
        gardar_pdf_estruturado(contexto, editado, str(saida), substitucions)

        with fitz.open(str(saida)) as documento:
            texto_final = documento[0].get_text()
        self.assertIn("(revisado)", texto_final)
        self.assertIn("Liña 75", texto_final, "perdeuse o final da páxina")
        self.assertNotIn("Manuel", texto_final)
        self.assertNotIn("30014811", texto_final)

    def test_texto_imposible_avisa_en_vez_de_deixar_a_paxina_en_branco(self):
        """Se nin no tamaño mínimo cabe, hai que avisar: mellor un erro
        claro (e ningún ficheiro de saída) ca unha páxina baleira."""
        entrada = self.dir / "curto.pdf"
        documento = fitz.open()
        documento.new_page().insert_text((72, 100), "Escrito de Manuel Ferrandiz Salcedo.", fontsize=11)
        documento.save(str(entrada))
        documento.close()

        texto, contexto = cargar_pdf_estruturado(str(entrada))
        texto_anon, _informe, substitucions = anonimizar_texto_detallado(
            texto, self.rexistro, contexto=contexto
        )
        desmesurado = texto_anon + " " + ("parrafo engadido a man polo letrado. " * 2000)
        saida = self.dir / "curto.anonimizado.pdf"

        with self.assertRaises(ValueError) as erro:
            gardar_pdf_estruturado(contexto, desmesurado, str(saida), substitucions)

        self.assertIn("non colle", str(erro.exception))
        self.assertFalse(saida.exists(), "non se debe deixar un PDF a medias")

    def test_o_tamano_baixa_so_o_necesario(self):
        rect = fitz.Rect(0, 0, 400, 700)
        self.assertEqual(_tamano_que_cabe(rect, "Unha liña curta.", 0), _TAMANO_RESERVA)

        moito_texto = "palabra " * 1000  # non cabe a 11 puntos, si máis pequeno
        reducido = _tamano_que_cabe(rect, moito_texto, 0)
        self.assertIsNotNone(reducido)
        self.assertLess(reducido, _TAMANO_RESERVA)
        self.assertGreaterEqual(reducido, _TAMANO_RESERVA_MINIMO)

        self.assertIsNone(_tamano_que_cabe(rect, "palabra " * 100000, 0))


if __name__ == "__main__":
    unittest.main()
