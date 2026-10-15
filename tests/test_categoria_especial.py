import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.categoria_especial import escanear_categoria_especial


def _categorias(texto):
    return [a.categoria for a in escanear_categoria_especial(texto)]


class TestDeteccion(unittest.TestCase):
    def test_saude(self):
        self.assertEqual(_categorias("PERSOA_000001 padece esclerosis múltiple desde 2015."), ["saude"])
        self.assertEqual(_categorias("Aporta certificado de discapacidad del 45%."), ["saude"])
        self.assertEqual(_categorias("O recorrente padeceu un infarto o pasado ano."), ["saude"])

    def test_relixion(self):
        self.assertEqual(_categorias("PERSOA_000001 profesa la religión musulmana."), ["relixion"])
        self.assertEqual(_categorias("É membro da comunidade xudía de Galicia."), ["relixion"])

    def test_orientacion_sexual(self):
        self.assertEqual(_categorias("PERSOA_000001 es lesbiana."), ["orientacion_sexual"])
        self.assertEqual(_categorias("Casou coa súa parella do mesmo sexo."), ["orientacion_sexual"])

    def test_sindical(self):
        self.assertEqual(_categorias("Está afiliada á CIG desde 2015."), ["sindical"])
        self.assertEqual(_categorias("Es delegado sindical de CCOO en la empresa."), ["sindical"])

    def test_vocabulario_institucional_non_avisa(self):
        """Os documentos xurídicos están cheos destas palabras sen que
        falen do dato sensible de ninguén -- un aviso en cada un deles
        enterraría os avisos reais."""
        for texto in (
            "El centro de salud cierra a las ocho.",
            "Consta afiliado a la Seguridad Social desde 2010.",
            "El Juzgado de lo Social número 2 dictó sentencia.",
            "La vivienda tiene orientación sur.",
            "La baja del vehículo se tramitó en Tráfico.",
            "El artículo 16 garantiza la libertad religiosa.",
            "A finca sitúase na parroquia de San Xoán de Poio.",
            "Comparece CCOO como parte demandante.",
            "Se incautaron dos kilos de cocaína en el registro.",
            "Un diagnóstico de la situación financiera de la empresa.",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_categorias(texto), [])

    def test_contexto_e_termo(self):
        avisos = escanear_categoria_especial("Segundo o informe, PERSOA_000001 é seropositivo desde hai anos.")
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].termo, "seropositivo")
        self.assertIn("PERSOA_000001", avisos[0].contexto)


class TestPipeline(unittest.TestCase):
    def test_so_avisa_non_redacta(self):
        """Decisión do 27/09/2026: o dato sensible queda no texto e só se
        avisa no informe -- a persoa xa vai co seu código."""
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias

        with tempfile.TemporaryDirectory() as d:
            anon, informe = anonimizar_texto(
                "Manuel Ferrándiz Salcedo padece esclerosis múltiple desde hace años.",
                RexistroCorrespondencias(d),
            )
        self.assertNotIn("Manuel Ferrándiz Salcedo", anon)
        self.assertIn("esclerosis múltiple", anon)
        self.assertEqual([a["categoria"] for a in informe["categoria_especial"]], ["saude"])

    def test_sen_datos_sensibles_lista_baleira(self):
        from anonimizador.pipeline import anonimizar_texto
        from anonimizador.registry import RexistroCorrespondencias

        with tempfile.TemporaryDirectory() as d:
            _, informe = anonimizar_texto("Manuel Ferrándiz Salcedo presentó el escrito.", RexistroCorrespondencias(d))
        self.assertEqual(informe["categoria_especial"], [])


class TestWeb(unittest.TestCase):
    TEXTO = (
        "Consta que Manuel Ferrándiz Salcedo padece esclerosis múltiple desde 2015.\n"
        "El centro de salud cierra a las ocho.\n"
    )

    def setUp(self):
        from anonimizador import web
        self.web = web
        web.SESIONS.clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro_dir = str(self.dir / "rexistro")
        self.client = web.app.test_client()
        self.doc = self.dir / "doc.txt"
        self.doc.write_text(self.TEXTO, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_revisar_amosa_a_seccion(self):
        resposta = self.client.post(
            "/procesar", data={"ruta": str(self.doc), "rexistro": self.rexistro_dir}, follow_redirects=True
        )
        html = resposta.get_data(as_text=True)
        self.assertIn("1 dato(s) de categoría especial", html)
        self.assertIn("Datos de categoría especial (art. 9 RGPD)", html)
        self.assertIn("<strong>Saúde</strong>", html)
        self.assertIn("«esclerosis»", html)
        self.assertIn("PERSOA_000001 padece esclerosis múltiple", html)
        # O contexto do aviso vai anonimizado. (O nome real si aparece na lista
        # de persoas detectadas, para poder decidir se é persoa -- só en local.)
        self.assertNotIn("Manuel Ferrándiz Salcedo padece", html)

    def test_modo_automatico_amosa_o_conto(self):
        resposta = self.client.post(
            "/procesar", data={"ruta": str(self.doc), "rexistro": self.rexistro_dir, "modo": "automatico"}
        )
        self.assertIn("1 dato(s) de categoría especial", resposta.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
