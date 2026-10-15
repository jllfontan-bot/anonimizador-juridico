"""Caso real atopado revisando expedientes reais: o propio NOME DO
FICHEIRO ás veces menciona a persoa ou o seu DNI ("Certificado poder Jose
Luis Lopez Rabadan.pdf") -- deixalo así deixaría a identidade real á vista
aínda que o contido do documento quedase ben anonimizado. Informe do
usuario: "a veces os nomes dos arquivos teñen nomes de persoas ou DNI ou
DOI... hai que poñer o código de persoa correspondente"."""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador.pipeline import (
    anonimizar_e_gardar,
    anonimizar_zip,
    nome_ficheiro_anonimizado,
    ruta_saida_por_defecto,
)
from anonimizador.registry import RexistroCorrespondencias


class TestNomeFicheiroAnonimizado(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_nome_de_persoa_no_ficheiro_substituese_polo_codigo(self):
        novo = nome_ficheiro_anonimizado(
            "Certificado poder Jose Luis Lopez Rabadan.pdf", self.rexistro
        )
        self.assertTrue(novo.endswith(".pdf"))
        self.assertNotIn("Jose", novo)
        self.assertNotIn("Rabadan", novo)
        self.assertIn("PERSOA_", novo)
        self.assertTrue(novo.startswith("Certificado poder "))

    def test_separadores_habituais_en_nomes_de_ficheiro(self):
        """"_" e "-" son os separadores máis habituais en nomes de
        ficheiro real (en vez de espazos) -- teñen que detectarse igual."""
        con_barra_baixa = nome_ficheiro_anonimizado(
            "Certificado_Jose_Luis_Lopez_Rabadan.pdf", self.rexistro
        )
        self.assertNotIn("Jose", con_barra_baixa)
        self.assertIn("PERSOA_", con_barra_baixa)

    def test_dni_no_ficheiro_substituese(self):
        novo = nome_ficheiro_anonimizado("DNI 30014811Z escaneado.pdf", self.rexistro)
        self.assertNotIn("30014811", novo)
        self.assertTrue(novo.endswith(" escaneado.pdf"))

    def test_nome_sen_datos_persoais_non_se_toca(self):
        orixinal = "Licencia obra 13-10-2020.pdf"
        self.assertEqual(nome_ficheiro_anonimizado(orixinal, self.rexistro), orixinal)

    def test_dni_no_nome_reutiliza_o_codigo_xa_creado_polo_contido(self):
        """Se o NOME de ficheiro trae o DNI (non só o nome propio), e o
        contido xa creou un código para ese DNI, o nome de ficheiro ten
        que REUTILIZAR ese mesmo código -- para iso o CONTIDO ten que
        procesarse primeiro (así o rexistro xa coñece a asociación
        DNI<->código cando se anonimiza o nome do ficheiro). Bug real
        atopado escribindo este mesmo arranxo: procesando na orde
        contraria, o nome de ficheiro creaba un código propio distinto do
        que despois recibía o contido."""
        entrada = self.dir / "Certificado 30014811Z.txt"
        entrada.write_text(
            "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito.",
            encoding="utf-8",
        )
        # mesmo patrón có das chamadoras reais (`web._procesar_automatico`,
        # `cli.main`): garda primeiro cun nome provisional (contido xa
        # anonimizado, rexistro xa actualizado) e só despois calcula o
        # nome de ficheiro definitivo e renomea.
        saida_provisional = ruta_saida_por_defecto(str(entrada))
        texto_anon, informe = anonimizar_e_gardar(str(entrada), saida_provisional, self.rexistro)
        saida = ruta_saida_por_defecto(str(entrada), rexistro=self.rexistro)
        if saida != saida_provisional:
            Path(saida_provisional).rename(saida)

        codigo_persoa = informe["persoas"][0]["codigo"]
        # o DNI solto do nome de ficheiro leva o código da persoa (o mesmo
        # ca o nome e ca o DNI no contido) -- sen o DNI real.
        self.assertNotIn("30014811", Path(saida).name)
        self.assertIn(codigo_persoa, Path(saida).name)
        self.assertNotIn("30014811", texto_anon)
        self.assertEqual(texto_anon.count(codigo_persoa), 2)  # o nome e o DNI

    def test_so_o_nome_sen_dni_marca_para_revision_se_non_se_pasa_o_contido(self):
        """Chamando `ruta_saida_por_defecto` SEN `persoas_do_documento`
        (é dicir, sen dicirlle cales son as persoas xa resoltas no
        contido deste mesmo ficheiro), non hai proba abonda para asumir
        que é a mesma persoa -- créase un código NOVO marcado para
        revisión, coma calquera homónimo. É o comportamento de reserva
        cando non hai contido de referencia á man (por exemplo, chamando
        a función illada, fóra do fluxo normal). **As chamadoras reais
        (`web._procesar_automatico`, `web.confirmar`, `cli.main`) SI
        pasan `persoas_do_documento`** -- ver
        `test_reutiliza_o_codigo_do_contido_sen_dni_no_nome_ficheiro`
        (A17) para o comportamento real da aplicación."""
        entrada = self.dir / "Certificado Manuel Ferrandiz Salcedo.txt"
        entrada.write_text(
            "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito.",
            encoding="utf-8",
        )
        saida_provisional = ruta_saida_por_defecto(str(entrada))
        texto_anon, informe = anonimizar_e_gardar(str(entrada), saida_provisional, self.rexistro)
        codigo_contido = informe["persoas"][0]["codigo"]
        saida = ruta_saida_por_defecto(str(entrada), rexistro=self.rexistro)
        if saida != saida_provisional:
            Path(saida_provisional).rename(saida)

        self.assertNotIn("Manuel", Path(saida).name)
        self.assertNotIn("Ferrandiz", Path(saida).name)
        self.assertIn("PERSOA_", Path(saida).name)
        self.assertNotIn(codigo_contido, Path(saida).name)

    def test_reutiliza_o_codigo_do_contido_sen_dni_no_nome_ficheiro(self):
        """A17 (revisión 21/09/2026): o nome de ficheiro non trae DNI, só
        o nome de pía -- pero esa MESMA persoa xa apareceu no contido
        (con DNI), así que o contido xa lle asignou un código. Bug real:
        "Informe Xosé Manuel Carballo Portela.txt" -- o contido daba
        PERSOA_000005, pero o nome de ficheiro creaba un código NOVO
        (PERSOA_000006), e cada chamada adicional daba aínda outro
        (PERSOA_000007), porque `nome_ficheiro_anonimizado` resolvía o
        nome do ficheiro coma un texto illado, sen relación ningunha co
        contido xa procesado. Correcto: reutilizar directamente o código
        xa asignado no contido, coma fan agora as chamadoras reais."""
        entrada = self.dir / "Informe Xosé Manuel Carballo Portela.txt"
        entrada.write_text(
            "Informe elaborado por Xosé Manuel Carballo Portela, con DNI 30014811Z.",
            encoding="utf-8",
        )
        saida_provisional = ruta_saida_por_defecto(str(entrada))
        texto_anon, informe = anonimizar_e_gardar(str(entrada), saida_provisional, self.rexistro)
        codigo_contido = informe["persoas"][0]["codigo"]

        saida = ruta_saida_por_defecto(str(entrada), rexistro=self.rexistro, persoas_do_documento=informe["persoas"])
        if saida != saida_provisional:
            Path(saida_provisional).rename(saida)

        self.assertNotIn("Xosé", Path(saida).name)
        self.assertNotIn("Carballo", Path(saida).name)
        self.assertIn(codigo_contido, Path(saida).name)

        # Idempotente: chamar outra vez (coma faille `anonimizar_zip` para
        # cada entrada) ten que dar SEMPRE o mesmo código, non un novo.
        outra_vez = nome_ficheiro_anonimizado(entrada.name, self.rexistro, informe["persoas"])
        self.assertEqual(outra_vez, nome_ficheiro_anonimizado(entrada.name, self.rexistro, informe["persoas"]))
        self.assertIn(codigo_contido, outra_vez)

    def test_ruta_saida_por_defecto_sen_rexistro_mantén_comportamento_previo(self):
        """Sen pasar `rexistro` (chamadores existentes, tests previos), o
        nome do ficheiro NON se toca -- cambio compatible cara atrás."""
        self.assertEqual(
            ruta_saida_por_defecto("/casos/Jose Luis Lopez Rabadan.txt"),
            "/casos/Jose Luis Lopez Rabadan.anonimizado.txt",
        )

    def test_entradas_do_zip_anonimizan_tamén_o_nome(self):
        entrada = self.dir / "expediente.zip"
        with zipfile.ZipFile(entrada, "w") as zf:
            zf.writestr(
                "carpeta/Manuel Ferrandiz Salcedo.txt",
                "Manuel Ferrándiz Salcedo, con DNI 30014811Z, presentou o escrito.",
            )
        saida = self.dir / "expediente.anonimizado.zip"
        anonimizar_zip(str(entrada), str(saida), self.rexistro)

        with zipfile.ZipFile(saida) as zf:
            nomes = zf.namelist()
        self.assertEqual(len(nomes), 1)
        self.assertTrue(nomes[0].startswith("carpeta/"))
        self.assertNotIn("Manuel", nomes[0])
        self.assertNotIn("Ferrandiz", nomes[0])
        self.assertIn("PERSOA_", nomes[0])


if __name__ == "__main__":
    unittest.main()
