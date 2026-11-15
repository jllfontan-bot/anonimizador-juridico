"""Un só motor Markdown para o Reductor e a copia .md do Anonimizador (fase 1b).

`markdown_ia.xerar` (estrutura -> títulos do PDF -> aforro para IA) é a única
porta: compróbase que a usan todos os camiños (Reductor nos dous modos,
`anonimizar_e_gardar`, `anonimizar_zip`, a web e, por `pipeline`, a liña de
comandos), que os dous programas dan o MESMO Markdown dun mesmo documento, e
que ningún paso devolve texto orixinal cando recibe o texto xa anonimizado.

Todos os nomes, DNI e enderezos son sintéticos.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import fitz  # PyMuPDF

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import (  # noqa: E402
    aforro_ia, cli, conversor, copia_md, idioma, lectura, markdown_ia, pipeline, titulos_pdf, web,
)
from anonimizador.registry import RexistroCorrespondencias  # noqa: E402

_ORIXINAIS = ("Xoán", "Pérez", "Vázquez", "XOÁN", "PÉREZ", "VÁZQUEZ", "ANTÍA", "VARELA", "DOVAL",
              "Uxía", "Rial", "Novo", "30014811Z", "Progreso", "Avenida da Coruña")
_CABECEIRA = "Xulgado de Primeira Instancia n.º 2 de Lugo. Autos de XOÁN PÉREZ VÁZQUEZ"
_PERSOAIS = [
    "Comparece don Xoán Pérez Vázquez, con DNI 30014811Z, e actuando no seu",
    "nome, con domicilio na Rúa do Progreso, 14, 2.º A, 27001 Lugo, expón",
    "que a demandada, dona ANTÍA VARELA DOVAL, vive na Avenida da Coruña, 25,",
    "de Lugo, e que non pagou as rendas vencidas desde o mes de xaneiro pasado.",
    "Así o declarou a testemuña dona Uxía Rial Novo, veciña do mesmo inmoble.",
]
_RECHEO = [
    "A parte demandada contestou á demanda alegando a falta de proba dos feitos",
    "e solicitou a desestimación íntegra das pretensións da parte contraria.",
    "Practicada a proba, quedaron os autos conclusos para ditar a sentenza.",
    "Os feitos probados resultan dos documentos achegados polas dúas partes.",
    "Non consta que a parte demandante cumprise os requisitos esixidos na lei.",
    "En consecuencia, procede estimar parcialmente a demanda presentada.",
]


def _pdf_sintetico(ruta: Path) -> Path:
    """Catro páxinas cunha cabeceira repetida co nome en maiúsculas, un título
    grande co nome, o contador de páxina ao pé e, nas páxinas 1 e 3, nome,
    DNI e enderezos en liñas partidas: cada paso da cadea ten algo que facer."""
    documento = fitz.open()
    for n in range(4):
        paxina = documento.new_page()
        paxina.insert_text((72, 40), _CABECEIRA, fontsize=9)
        if n == 0:
            paxina.insert_text((72, 110), "DEMANDA DE XOÁN PÉREZ VÁZQUEZ", fontsize=16)
        recheo = [f"{l[:-1]}, apartado {n + 1}.{k + 1}." for k, l in enumerate(_RECHEO * 2)]
        liñas = recheo[:6] + (_PERSOAIS if n in (0, 2) else []) + recheo[6:]
        for i, liña in enumerate(liñas):
            paxina.insert_text((72, 160 + 16 * i), liña, fontsize=11)
        paxina.insert_text((72, 800), f"Páxina {n + 1} de 4", fontsize=9)
    documento.save(str(ruta))
    return ruta


def _palabras(texto: str) -> set:
    return set(re.findall(r"\w+", texto))


def _sen_comentarios(md: str) -> str:
    """O Markdown sen as liñas `<!-- ... -->` (marcas de páxina e do bloque de
    cabeceiras, que poñen os módulos, non o documento)."""
    return "\n".join(l for l in md.split("\n") if not l.startswith("<!--"))


def _corpo_do_reductor(ruta: Path) -> str:
    """O .md do Reductor sen a súa cabeceira (`---` ... `---`)."""
    texto = ruta.read_text(encoding="utf-8")
    return texto.split("\n---\n", 1)[1]


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _sen_orixinais(self, md: str):
        for dato in _ORIXINAIS:
            self.assertNotIn(dato, md, f"{dato!r} á vista no Markdown")


class TestMesmaFuncion(_Base):
    """Todos os camiños pasan por `markdown_ia.xerar`, cada un co seu `aforro`."""

    def _txt(self, nome: str = "escrito.txt") -> Path:
        ruta = self.dir / nome
        ruta.write_text("Comparece don Xoán Pérez Vázquez ante o xulgado.\n", encoding="utf-8")
        return ruta

    def _chamadas(self, accion) -> list:
        with mock.patch.object(markdown_ia, "xerar", wraps=markdown_ia.xerar) as espia:
            accion()
        self.assertTrue(espia.called, "non pasou por markdown_ia.xerar")
        return [c.kwargs["aforro"] for c in espia.call_args_list]

    def test_reductor_sen_anonimizar(self):
        self.assertEqual(self._chamadas(lambda: conversor.converter(str(self._txt()))), [markdown_ia.AFORRO])
        self.assertEqual(self._chamadas(lambda: conversor.converter(str(self._txt("b.txt")), aforro=False)),
                         [markdown_ia.SEN_AFORRO])

    def test_reductor_anonimizando(self):
        aforros = self._chamadas(lambda: conversor.converter(str(self._txt()), anonimizar=True, rexistro=self.rexistro))
        self.assertEqual(aforros, [markdown_ia.AFORRO])

    def test_anonimizador_documento(self):
        ruta = self._txt()
        saida = pipeline.ruta_saida_por_defecto(str(ruta))
        aforros = self._chamadas(lambda: pipeline.anonimizar_e_gardar(str(ruta), saida, self.rexistro, copia_md=True))
        self.assertEqual(aforros, [markdown_ia.AFORRO_ANONIMIZADOR])

    def test_anonimizador_zip(self):
        entrada = self.dir / "lote.zip"
        with zipfile.ZipFile(entrada, "w") as z:
            z.write(self._txt(), "escrito.txt")
        aforros = self._chamadas(lambda: pipeline.anonimizar_zip(
            str(entrada), str(self.dir / "lote.anonimizado.zip"), self.rexistro, copia_md=True))
        self.assertEqual(aforros, [markdown_ia.AFORRO_ANONIMIZADOR])

    def test_anonimizador_cli(self):
        ruta = self._txt()
        argv = ["anonimizador", "anonimizar", str(ruta), "--rexistro", str(self.dir / "rexistro_cli"), "--markdown"]
        with mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
            aforros = self._chamadas(cli.main)
        self.assertEqual(aforros, [markdown_ia.AFORRO_ANONIMIZADOR])

    def test_anonimizador_web(self):
        web.SESIONS.clear()
        parche = mock.patch.object(idioma, "ficheiro_preferencias", lambda: self.dir / "preferencias.json")
        parche.start()
        self.addCleanup(parche.stop)
        cliente = web.app.test_client()
        datos = {"rexistro": str(self.dir / "rexistro_web"), "copia_md": "1"}
        aforros = self._chamadas(lambda: cliente.post(
            "/procesar", data={"ruta": str(self._txt()), "modo": "automatico", **datos}))
        self.assertEqual(aforros, [markdown_ia.AFORRO_ANONIMIZADOR])
        r = cliente.post("/procesar", data={"ruta": str(self._txt("b.txt")), "modo": "revisar", **datos})
        sid = re.search(r"/revisar/([0-9a-f]+)", r.headers["Location"]).group(1)
        aforros = self._chamadas(lambda: cliente.post(
            f"/revisar/{sid}/confirmar", data={"rexistro_dir": datos["rexistro"]}))
        self.assertEqual(aforros, [markdown_ia.AFORRO_ANONIMIZADOR])

    def test_o_anonimizador_usa_as_opcions_por_defecto_do_reductor(self):
        """Hoxe a única diferenza posible é a casa «aforro» do Reductor; ver o
        docstring de `markdown_ia`."""
        self.assertEqual(markdown_ia.AFORRO_ANONIMIZADOR, markdown_ia.opcions_do_reductor(True))
        self.assertEqual(markdown_ia.AFORRO_ANONIMIZADOR, aforro_ia.Opcions())

    def test_ningun_modulo_chama_os_pasos_soltos(self):
        """Fóra de `markdown_ia` ninguén xera Markdown cos pasos por separado
        (o Reductor só chama a `aforro_ia.aforrar` para TROCEAR ao escribir)."""
        src = Path(__file__).resolve().parents[1] / "src" / "anonimizador"
        pasos = re.compile(r"copia_md\.xerar\(|marcar_titulos_md\(|aforro_ia\.aforrar\(")
        usos = {}
        for ruta in src.rglob("*.py"):
            for liña in ruta.read_text(encoding="utf-8").split("\n"):
                if pasos.search(liña) and not liña.lstrip().startswith(("#", '"""', "`")):
                    usos.setdefault(ruta.name, []).append(liña.strip())
        fora = {nome: l for nome, l in usos.items() if nome not in ("markdown_ia.py", "titulos_pdf.py")}
        self.assertEqual(list(fora), ["conversor.py"], fora)
        self.assertEqual(len(fora["conversor.py"]), 1)
        self.assertIn("so_trocear", fora["conversor.py"][0])

    def test_o_troceado_non_e_desta_cadea(self):
        with self.assertRaises(ValueError):
            markdown_ia.xerar(None, "texto", aforro=aforro_ia.Opcions(caracteres_por_parte=100))


class TestFugasPdfSintetico(_Base):
    """Nome en maiúsculas na cabeceira repetida e nun título, DNI e enderezos."""

    def setUp(self):
        super().setUp()
        self.ruta = _pdf_sintetico(self.dir / "demanda.pdf")

    def _copia_do_anonimizador(self) -> tuple:
        saida = pipeline.ruta_saida_por_defecto(str(self.ruta))
        texto_anon, _ = pipeline.anonimizar_e_gardar(str(self.ruta), saida, self.rexistro, copia_md=True)
        return texto_anon, Path(saida + ".md").read_text(encoding="utf-8")

    def test_copia_do_anonimizador_pasa_por_toda_a_cadea_sen_fugas(self):
        texto_anon, md = self._copia_do_anonimizador()
        self._sen_orixinais(md)
        # cada paso fixo o seu traballo...
        self.assertRegex(md, r"(?m)^# DEMANDA DE PERSOA_\d+$")  # títulos do PDF
        self.assertTrue(md.startswith(f"<!-- {idioma.t('copia_md.cabeceiras')} -->"), md[:200])  # repetidas
        self.assertEqual(md.count("Xulgado de Primeira Instancia"), 1)
        self.assertNotIn("Páxina 2 de 4", md)  # contador fóra (a marca de páxina queda)
        self.assertIn("<!-- páxina 2 -->", md)
        self.assertIn("no seu nome, con domicilio", md)  # liñas partidas unidas
        # ...e ningunha palabra do Markdown falta no texto anonimizado
        self.assertLessEqual(_palabras(_sen_comentarios(md)), _palabras(texto_anon))

    def test_reductor_anonimizando_dá_o_mesmo_markdown_co_anonimizador(self):
        _, md_anonimizador = self._copia_do_anonimizador()
        # Un rexistro novo e baleiro coma o do anonimizador: os mesmos códigos na mesma orde.
        rexistro = RexistroCorrespondencias(str(self.dir / "rexistro_reductor"))
        resultado = conversor.converter(str(self.ruta), anonimizar=True, rexistro=rexistro,
                                        saida=str(self.dir / "reductor"))
        self.assertEqual(len(resultado.saidas), 1)
        md_reductor = _corpo_do_reductor(Path(resultado.saidas[0]))
        self._sen_orixinais(md_reductor)
        self.assertEqual(md_reductor.strip("\n"), md_anonimizador.strip("\n"))

    def test_ningun_paso_engade_texto_que_non_estea_no_anonimizado(self):
        texto, contexto = lectura.cargar_documento_estruturado(str(self.ruta))
        texto_anon, _, subs = pipeline.anonimizar_texto_detallado(texto, self.rexistro, contexto=contexto)
        permitidas = _palabras(texto_anon)
        for aforro in (markdown_ia.AFORRO, markdown_ia.SEN_AFORRO, markdown_ia.AFORRO_ANONIMIZADOR):
            md = markdown_ia.xerar(contexto, texto_anon, subs, aforro=aforro).texto
            self._sen_orixinais(md)
            self.assertLessEqual(_palabras(_sen_comentarios(md)), permitidas, aforro)
        # paso a paso: os títulos e o aforro non engaden palabras ao que dá `copia_md`
        base = copia_md.xerar(contexto, texto_anon, subs)
        con_titulos = titulos_pdf.marcar_titulos_md(base, contexto, texto_anon, subs)
        self.assertNotEqual(base, con_titulos)
        self.assertLessEqual(_palabras(con_titulos), _palabras(base))
        aforrado = aforro_ia.aforrar(con_titulos).texto
        self.assertLessEqual(_palabras(_sen_comentarios(aforrado)), _palabras(con_titulos))

    def test_titulos_sen_substitucions_so_co_texto_orixinal(self):
        """Sen substitucións, `marcar_titulos_md` só mapea se o texto é o
        orixinal: un texto anonimizado (ou editado) sen elas queda sen títulos."""
        texto, contexto = lectura.cargar_documento_estruturado(str(self.ruta))
        self.assertRegex(markdown_ia.xerar(contexto, texto, aforro=markdown_ia.SEN_AFORRO).texto,
                         r"(?m)^# DEMANDA DE XOÁN PÉREZ VÁZQUEZ$")
        texto_anon, _, _ = pipeline.anonimizar_texto_detallado(texto, self.rexistro, contexto=contexto)
        md = copia_md.xerar(contexto, texto_anon)
        self.assertEqual(titulos_pdf.marcar_titulos_md(md, contexto, texto_anon, None), md)


if __name__ == "__main__":
    unittest.main()
