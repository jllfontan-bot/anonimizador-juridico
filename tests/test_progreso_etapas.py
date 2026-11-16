"""Progreso despois de ler as páxinas (15/11/2026): nun PDF de 351 páxinas o
contador chegaba ao final e o Reductor seguía minutos sen indicador. Agora
`conversor.converter(progreso_etapa=...)` informa da etapa (`etapas.ETAPAS`)
e, onde hai un bucle, do seu avance. Compróbase a orde, o límite de avisos,
que a saída é idéntica con e sen indicador, a pantalla e a liña de comandos."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import datetime
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import docx
import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import cli_conversor, conversor, etapas, idioma, pantalla_conversor
from anonimizador.registry import RexistroCorrespondencias

_DATA = datetime.date(2026, 11, 15)


def _docx(ruta: Path, n: int = 12) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    d = docx.Document()
    d.add_heading("Demanda", 1)
    for i in range(n):
        d.add_paragraph(f"Parágrafo {i}: comparece don Xoán Pérez Vázquez, con DNI 30014811Z, e dona Antía "
                        f"Varela Doval, con DNI 12345678Z. Referencia {34867800 + i} do expediente.")
    d.save(str(ruta))
    return ruta


def _pdf(ruta: Path, paxinas: int = 3) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    d = fitz.open()
    for i in range(paxinas):
        d.new_page().insert_text((72, 72), f"Páxina {i}: comparece Brais Castro Lema, con DNI 87654321X.")
    d.save(str(ruta))
    return ruta


def _sen_repetidas(claves: list) -> list:
    return [c for i, c in enumerate(claves) if i == 0 or claves[i - 1] != c]


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _rexistro(self, nome="rexistro"):
        return RexistroCorrespondencias(str(self.dir / nome))


class TestEtapas(_Base):
    def test_sen_aviso_etapa_non_fai_nada(self):
        etapas.etapa("detectar", 1, 2)  # sen `avisar`: nin erro nin efecto

    def test_sen_anonimizar_markdown_e_gardar_despois_das_paxinas(self):
        pdf = _pdf(self.dir / "escrito.pdf")
        eventos = []
        conversor.converter(str(pdf), progreso=lambda f, t, n: eventos.append(("doc", f)),
                            progreso_paxina=lambda f, t: eventos.append(("paxina", f)),
                            progreso_etapa=lambda c, f, t: eventos.append(("etapa", c)))
        self.assertEqual(eventos, [("doc", 0), ("paxina", 0), ("paxina", 1), ("paxina", 2),
                                   ("etapa", "markdown"), ("etapa", "gardar"), ("doc", 1)])

    def test_anonimizando_etapas_en_orde(self):
        ruta = _docx(self.dir / "demanda.docx")
        avisos = []
        conversor.converter(str(ruta), anonimizar=True, rexistro=self._rexistro(),
                            progreso_etapa=lambda c, f, t: avisos.append((c, f, t)))
        claves = _sen_repetidas([c for c, _, _ in avisos])
        self.assertEqual(claves, ["detectar", "axustar", "agrupar", "codigos", "riscos", "markdown", "gardar"])
        self.assertTrue(set(claves) <= set(etapas.ETAPAS))
        con_avance = [(f, t) for c, f, t in avisos if c == "detectar" and t]
        self.assertTrue(con_avance)  # os anacos do NER contan
        self.assertTrue(all(0 <= f < t for f, t in con_avance))
        agrupar = [(f, t) for c, f, t in avisos if c == "agrupar" and t]
        self.assertTrue(agrupar)  # as mencións ao asociar os DNI
        self.assertEqual([f for f, _ in agrupar], sorted(f for f, _ in agrupar))

    def test_como_moito_un_aviso_por_cada_1_por_cento(self):
        ruta = _docx(self.dir / "demanda.docx", n=150)
        avisos = []
        conversor.converter(str(ruta), anonimizar=True, rexistro=self._rexistro(),
                            progreso_etapa=lambda c, f, t: avisos.append((c, f, t)))
        agrupar = [(f, t) for c, f, t in avisos if c == "agrupar" and t]
        total = agrupar[0][1]
        self.assertGreater(total, 101)  # máis mencións ca avisos permitidos
        self.assertLessEqual(len(agrupar), 2 * 101)  # agrupar corre dúas veces (`_emparellar`)

    def test_cada_documento_volve_empezar(self):
        raiz = self.dir / "expediente"
        _pdf(raiz / "a.pdf", 1)
        _pdf(raiz / "b.pdf", 1)
        avisos = []
        conversor.converter(str(raiz), progreso_etapa=lambda c, f, t: avisos.append(c))
        self.assertEqual(avisos, ["markdown", "gardar", "markdown", "gardar"])

    def test_un_aviso_que_falla_non_para_a_conversion(self):
        ruta = _docx(self.dir / "demanda.docx")

        def roto(*_):
            raise RuntimeError("a pantalla pechouse")

        resultado = conversor.converter(str(ruta), anonimizar=True, rexistro=self._rexistro(), progreso_etapa=roto)
        self.assertEqual(len(resultado.saidas), 1)
        self.assertEqual(resultado.omitidos, [])


class TestSaidaIdentica(_Base):
    """O indicador só informa: a saída é byte a byte a mesma con e sen el."""

    def _converter(self, subcartafol: str, anonimizar: bool, un_so_md: bool, aviso):
        raiz = self.dir / subcartafol / "expediente"
        _docx(raiz / "demanda.docx")
        _pdf(raiz / "escrito.pdf")
        (raiz / "notas.txt").write_text("Nota de Uxía Rial Souto. Teléfono 600123456.\n", encoding="utf-8")
        saida = self.dir / subcartafol / "saida"
        rexistro = self._rexistro(subcartafol + "-rex") if anonimizar else None
        conversor.converter(str(raiz), anonimizar=anonimizar, rexistro=rexistro, un_so_md=un_so_md,
                            saida=str(saida), data=_DATA, progreso_etapa=aviso)
        return {p.relative_to(saida).as_posix(): p.read_bytes() for p in saida.rglob("*") if p.is_file()}

    def test_identica_con_e_sen_indicador(self):
        for anonimizar in (False, True):
            for un_so_md in (False, True):
                with self.subTest(anonimizar=anonimizar, un_so_md=un_so_md):
                    nome = f"{anonimizar}-{un_so_md}"
                    sen = self._converter("sen-" + nome, anonimizar, un_so_md, None)
                    con = self._converter("con-" + nome, anonimizar, un_so_md, lambda *a: None)
                    self.assertTrue(sen)
                    self.assertEqual(con, sen)


class TestLiñaDeComandos(_Base):
    def test_progreso_pola_saida_de_erros_e_a_saida_igual(self):
        ruta = _docx(self.dir / "demanda.docx")
        saida, erros = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erros):
            self.assertEqual(cli_conversor.main([str(ruta), "--anonimizar", "--rexistro", str(self.dir / "rex")]), 0)
        erros = erros.getvalue()
        self.assertIn("[1/1] demanda.docx\n", erros)
        self.assertIn("  · " + idioma.t("conversor.etapa.detectar") + "\n", erros)
        self.assertIn("  · " + idioma.t("conversor.etapa.gardar") + "\n", erros)
        self.assertNotIn(idioma.t("conversor.etapa.detectar"), saida.getvalue())

    def test_nun_terminal_reescribe_a_mesma_liña(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        progreso = cli_conversor._ProgresoCli(terminal)
        progreso.documento(0, 1, "a.pdf")
        progreso.etapa("agrupar", 0, 10)
        progreso.etapa("agrupar", 9, 10)
        progreso.etapa("gardar", None, None)
        progreso.rematar()
        texto = terminal.getvalue()
        self.assertTrue(texto.startswith("[1/1] a.pdf\n"))
        self.assertIn("\r  · " + idioma.t("conversor.etapa.agrupar") + ": 10 de 10", texto)
        self.assertTrue(texto.endswith("\n"))


class TestPantalla(_Base):
    def setUp(self):
        super().setUp()
        cwd = os.getcwd()
        os.chdir(self.dir)  # preferencias.json, se a pantalla o garda, vai no cartafol de traballo
        self.addCleanup(os.chdir, cwd)

    def test_a_pantalla_recibe_a_etapa_traducida(self):
        eventos = []
        api = pantalla_conversor.Api(emitir=lambda e, d: eventos.append((e, d)),
                                     rexistro_dir=str(self.dir / "rexistro"), usar_chaveiro=False)
        pdf = _pdf(self.dir / "escrito.pdf", 2)
        api.converter({"rutas": [str(pdf)]})
        api._fio.join(120)
        etapas_vistas = [d for e, d in eventos if e == "etapa"]
        self.assertEqual([d["clave"] for d in etapas_vistas], ["markdown", "gardar"])
        self.assertEqual(etapas_vistas[0]["texto"], idioma.t("conversor.etapa.markdown"))
        self.assertEqual(etapas_vistas[0]["entrada"], 0)

    def test_o_html_pinta_a_etapa_e_o_texto_existe_en_es_e_gl(self):
        html = (Path(pantalla_conversor.__file__).parent / "templates" / "conversor.html").read_text(encoding="utf-8")
        self.assertIn('evento === "etapa"', html)
        for lingua in ("es", "gl"):
            textos = pantalla_conversor.textos_da_pantalla(lingua)
            self.assertIn("{etapa}", textos["progreso_etapa"])
            for clave in etapas.ETAPAS:
                self.assertNotEqual(idioma.t("conversor.etapa." + clave, lingua), "conversor.etapa." + clave)


if __name__ == "__main__":
    unittest.main()
