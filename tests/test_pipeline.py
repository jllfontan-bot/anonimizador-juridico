import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rexistro = RexistroCorrespondencias(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_consistencia_entre_documentos(self):
        """A mesma persoa (mesmo DNI) recibe o mesmo codigo en dous documentos distintos."""
        doc1 = "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presentou a demanda."
        doc2 = "Segundo consta, Manuel Ferrándiz Salcedo (DNI 30014811-Z) reside en Cangas."

        anon1, informe1 = anonimizar_texto(doc1, self.rexistro)
        anon2, informe2 = anonimizar_texto(doc2, self.rexistro)

        codigo1 = informe1["persoas"][0]["codigo"]
        codigo2 = informe2["persoas"][0]["codigo"]
        self.assertEqual(codigo1, codigo2)
        self.assertIn(codigo1, anon1)
        self.assertIn(codigo1, anon2)

    def test_dous_mencions_do_mesmo_dni_non_corrompen_o_texto_veciño(self):
        """A16 (revisión 21/09/2026): cando a MESMA persoa se menciona dúas
        veces con textos distintos ("Xoán Páez Veiga" e, despois, só
        "Xoán Pérez") -- polo que quedan en DOUS grupos separados, non un
        só -- e o seu DNI se repite tal cal preto de cada mención, cada
        aparición física do DNI recibía DÚAS substitucións apiladas coas
        mesmas coordenadas (unha por grupo), corrompendo os caracteres
        veciños ao aplicalas ("comparece" quedaba en "omparece")."""
        texto = (
            "D. Xoán Páez Veiga, con DNI 12345678-Z, comparece. "
            "Despois D. Xoán Pérez, DNI 12345678-Z, asina."
        )
        anon, informe = anonimizar_texto(texto, self.rexistro)

        self.assertIn(", comparece.", anon)
        self.assertIn(", asina.", anon)
        self.assertNotIn("12345678", anon)
        self.assertEqual(anon.count("DNI PERSOA_"), 2)

    def test_consistencia_persiste_entre_execucions_distintas(self):
        """Coma `test_consistencia_entre_documentos`, pero recargando o
        rexistro desde disco entre chamadas (instancias novas), tal como
        ocorre realmente entre dúas execucións do CLI ou dúas peticións
        web independentes -- se o índice de DNI non quedase ben gardado,
        este test detectaríao aínda que o anterior non."""
        doc1 = "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, presentou a demanda."
        doc2 = "Segundo consta, Manuel Ferrándiz Salcedo (DNI 30014811-Z) reside en Cangas."

        anon1, informe1 = anonimizar_texto(doc1, self.rexistro)

        rexistro_recargado = RexistroCorrespondencias(self._tmp.name)
        anon2, informe2 = anonimizar_texto(doc2, rexistro_recargado)

        codigo1 = informe1["persoas"][0]["codigo"]
        codigo2 = informe2["persoas"][0]["codigo"]
        self.assertEqual(codigo1, codigo2)
        self.assertFalse(informe2["persoas"][0]["marcado_para_revision"])

    def test_homonimos_non_colapsan(self):
        """Dúas persoas co mesmo nome completo pero DNI distinto reciben códigos distintos."""
        texto = (
            "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou que coñecía a "
            "Manuel Ferrándiz Salcedo, con DNI 76211309-X, desde hai dez anos."
        )
        _, informe = anonimizar_texto(texto, self.rexistro)

        codigos = {p["codigo"] for p in informe["persoas"]}
        self.assertEqual(len(codigos), 2, "dous DNI distintos deben xerar dous códigos distintos")
        self.assertFalse(any(p["marcado_para_revision"] for p in informe["persoas"]))

    def test_mesmo_nome_sen_dni_marca_para_revision(self):
        """Sen DNI, un nome que xa existe no rexistro NUNCA se fusiona automaticamente."""
        doc1 = "Manuel Ferrándiz Salcedo acudiu á vista sinalada para o luns."
        doc2 = "Manuel Ferrándiz Salcedo volveu declarar na segunda sesión."

        _, informe1 = anonimizar_texto(doc1, self.rexistro)
        _, informe2 = anonimizar_texto(doc2, self.rexistro)

        codigo1 = informe1["persoas"][0]["codigo"]
        codigo2 = informe2["persoas"][0]["codigo"]

        self.assertNotEqual(codigo1, codigo2, "sen DNI, nunca se debe fusionar automaticamente")
        self.assertFalse(informe1["persoas"][0]["marcado_para_revision"])
        self.assertTrue(informe2["persoas"][0]["marcado_para_revision"])
        self.assertIn("homonimo", informe2["persoas"][0]["motivo"].lower())

    def test_efecto_mosaico_detectado(self):
        """Profesión moi específica + lugar + data/idade preto dunha da outra
        debe marcarse como risco de efecto mosaico, mesmo sen ningún nome."""
        texto = (
            "O único cirurxián cardiovascular do hospital de Cee, de 52 anos, "
            "foi intervido o 14 de marzo de 2021 tras un accidente de tráfico."
        )
        _, informe = anonimizar_texto(texto, self.rexistro)

        self.assertTrue(
            any(r["tipo"] == "combinacion_alta_especificidade" for r in informe["riscos_mosaico"]),
            f"non se detectou o risco de efecto mosaico; achados: {informe['riscos_mosaico']}",
        )

    def test_efecto_mosaico_detectado_en_castelan(self):
        """A24 (revision 21/09/2026): o mosaico so recoñecia meses, "anos"
        e profesions en galego, polo que un expediente en castelan (moi
        habitual) nunca amosaba ningun aviso -- falsa sensacion de
        seguridade. A mesma combinacion profesion + lugar + data/idade
        que xa se detecta en galego (test anterior) ten que detectarse
        tamen en castelan."""
        texto = (
            "El médico de Vilalba, de 45 años, presentó la denuncia "
            "el 15 de septiembre de 2020."
        )
        _, informe = anonimizar_texto(texto, self.rexistro)

        self.assertTrue(
            any(r["tipo"] == "combinacion_alta_especificidade" for r in informe["riscos_mosaico"]),
            f"non se detectou o risco de efecto mosaico en castelan; achados: {informe['riscos_mosaico']}",
        )

    def test_informe_inclue_risco_residual(self):
        """O informe ten que traer sempre a chave "risco_residual" (rede
        de seguridade final, ver `risco_residual.py`) -- baleira se o
        texto anonimizado non deixa ningún patrón sospeitoso."""
        texto = "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito."
        _, informe = anonimizar_texto(texto, self.rexistro)
        self.assertIn("risco_residual", informe)
        self.assertEqual(
            [r for r in informe["risco_residual"] if r["confianza"] == "alta"], []
        )

    def test_enderezo_con_numero_redactase_directamente(self):
        """Un enderezo con número é un identificador DIRECTO (recognizers.py)
        e redáctase, xa non queda só marcado coma risco de efecto mosaico."""
        texto = "A vítima reside na Rúa do Franco, número 12, segundo piso."
        anon, informe = anonimizar_texto(texto, self.rexistro)
        self.assertNotIn("Rúa do Franco", anon)
        self.assertIn("[ENDEREZO]", anon)
        self.assertTrue(any(d["tipo"] == "ENDEREZO" for d in informe["identificadores_directos"]))


if __name__ == "__main__":
    unittest.main()
