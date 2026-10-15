import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ocr_dni
from anonimizador.recognizers import detectar


class TestCorreccionDni(unittest.TestCase):
    def test_letra_control_coñecida(self):
        # 00000001 -> resto 1 -> "R" (T=0, R=1 na secuencia oficial)
        self.assertEqual(ocr_dni.letra_control("00000001"), "R")

    def test_recoñece_dni_correcto(self):
        self.assertEqual(ocr_dni.recoñecer_dni_ocr("00000001R"), "00000001R")

    def test_recalcula_letra_final_mal_lida_polo_ocr(self):
        """Caso real: o OCR confunde a letra final (aquí un '2' onde o
        DNI correcto remataría noutra letra); a letra recalcúlase sempre
        a partir dos 8 díxitos, así que o resultado é correcto igualmente."""
        letra_correcta = ocr_dni.letra_control("00000001")
        self.assertEqual(ocr_dni.recoñecer_dni_ocr("000000012"), f"00000001{letra_correcta}")

    def test_recoñece_nie(self):
        # X0000001 -> mesmo calculo que un DNI "00000001" -> letra "R"
        self.assertEqual(ocr_dni.recoñecer_dni_ocr("X0000001R"), "X0000001R")

    def test_candidato_non_numerico_devolve_none(self):
        self.assertIsNone(ocr_dni.recoñecer_dni_ocr("ISTO NON"))

    def test_deteccion_por_contexto_en_texto_con_erro_ocr(self):
        """Sen esta corrección, "300148112" non casa co patrón estrito de
        DNI (9 díxitos, sen letra) e quedaba SEN detectar nin redactar."""
        texto = "O declarante, con DNI 300148112, sinala que..."
        entidades = detectar(texto)
        dnis = [e for e in entidades if e.etiqueta == "DNI_NIE"]
        self.assertEqual(len(dnis), 1)
        self.assertTrue(dnis[0].texto.startswith("30014811"))
        self.assertEqual(len(dnis[0].texto), 9)

    def test_deteccion_tras_abreviatura_de_numero_con_erro_ocr(self):
        """Caso real de revisión (A19): "DNI nº 30O14811Z" (coa
        abreviatura de "número" entre a etiqueta e o documento, e unha
        "O" onde debería haber un "0", erro típico do OCR) non casaba --
        o patrón antigo esixía o número XUSTO despois da etiqueta, sen
        "nº" polo medio."""
        texto = "O interesado, DNI nº 30O14811Z, presentou o escrito."
        entidades = detectar(texto)
        dnis = [e for e in entidades if e.etiqueta == "DNI_NIE"]
        self.assertEqual(len(dnis), 1)
        self.assertEqual(dnis[0].texto, "30014811" + ocr_dni.letra_control("30014811"))

    def test_deteccion_con_etiqueta_con_puntos_e_erro_ocr(self):
        """Caso real de revisión (A19): "D.N.I." (con puntos entre cada
        letra, moi habitual en escritos xudiciais) non casaba co patrón
        antigo, que só recoñecía "DNI" sen puntos -- mesmo motivo có
        "C.S.V." de `recognizers._CSV_ETIQUETA`."""
        texto = "Identifícase mediante D.N.I. 30O14811Z ante o xulgado."
        entidades = detectar(texto)
        dnis = [e for e in entidades if e.etiqueta == "DNI_NIE"]
        self.assertEqual(len(dnis), 1)
        self.assertEqual(dnis[0].texto, "30014811" + ocr_dni.letra_control("30014811"))


if __name__ == "__main__":
    unittest.main()


class TestNifDeEntidadNonEDni(unittest.TestCase):
    """BOE-A-2026-16914 (lectura de Claude, 30/09/2026): "NIF Q2876002C" do
    ICO líase coma o DNI 02876002J ("Q" tomado coma "0" do OCR)."""

    def test_cif_valido_non_se_toma_por_dni(self):
        from anonimizador import ocr_dni, recognizers
        self.assertTrue(ocr_dni.e_cif_valido("Q2876002C"))
        self.assertFalse(ocr_dni.e_cif_valido("Q2876002D"))
        self.assertEqual(recognizers.detectar("titular del NIF Q2876002C, con domicilio"), [])
        self.assertTrue(recognizers.detectar("DNI O1234567L"))
