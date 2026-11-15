"""Escritura incremental do Reductor (15/11/2026): cada .md escríbese en canto
se converte o seu documento, non ao final do lote. Caso real: un lote longo
(.zip e centos de folios) fallou ao final e a carpeta de saída quedou baleira.

Compróbase, con e sen anonimizar: que cada .md está en disco antes de converter
o seguinte, que un fallo a media execución deixa o anterior, o .md único
(`.parcial` ata pechar), os .zip, as colisións, as partes, cancelar, a parada
manual (`revisar`) e a revisión posterior sobre ficheiros xa escritos."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import re
import shutil
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

import docx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import conversor
from anonimizador.registry import RexistroCorrespondencias

_NOME = "Xoán Pérez Vázquez"
_DNI = "30014811Z"
_DATOS = ("Xoán", "Pérez", "Vázquez", _DNI)
_RISCO = "Comparece don Xoán Páez Veiga. Referencia 34867809 do expediente."


def _docx(ruta: Path, texto: str = f"Comparece don {_NOME}, con DNI {_DNI}, ante o xulgado de Lugo.") -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    d = docx.Document()
    for paragrafo in texto.split("\n\n"):
        d.add_paragraph(paragrafo)
    d.save(str(ruta))
    return ruta


def _txt(ruta: Path, texto: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def _longo() -> str:
    """Parágrafos distintos (o aforro quita os repetidos) que pasan dunhas partes de 1500 caracteres."""
    return "\n\n".join(f"Parágrafo {i} de proba sen datos persoais. " * 20 for i in range(8))


class _Fallo(RuntimeError):
    pass


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rexistro = RexistroCorrespondencias(str(self.dir / "rexistro"))
        self.raiz = self.dir / "expediente"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _tres_txt(self):
        for n in "abc":
            _txt(self.raiz / f"{n}.txt", f"Texto do documento {n}.")

    def _tres_docx(self):
        for n in "abc":
            _docx(self.raiz / f"{n}.docx")

    def _sen_datos(self, texto: str):
        for dato in _DATOS:
            self.assertNotIn(dato, texto)

    def _nomes(self, cartafol: Path):
        return sorted(p.relative_to(cartafol).as_posix() for p in cartafol.rglob("*") if p.is_file())

    def _converter_vixiando(self, entrada, vixiar, fallar_en=None, **opcions):
        """`vixiar(feito)` corre antes de converter cada documento (o que xa
        debería estar en disco). `fallar_en`: nese `feito` a execución rebenta."""
        def progreso(feito, total, nome):
            vixiar(feito)
            if fallar_en is not None and feito == fallar_en:
                raise _Fallo("fallo simulado")
        return conversor.converter(str(entrada), progreso=progreso, **opcions)


class TestCadaMdAoConverterse(_Base):
    def test_sen_anonimizar_o_md_xa_esta_en_disco_antes_do_seguinte(self):
        self._tres_txt()
        vistos = {}
        self._converter_vixiando(self.raiz, lambda f: vistos.update({f: self._nomes(self.raiz)}))
        self.assertEqual(vistos[0], ["a.txt", "b.txt", "c.txt"])
        self.assertEqual(vistos[1], ["a.txt", "a.txt.md", "b.txt", "c.txt"])
        self.assertEqual(vistos[2], ["a.txt", "a.txt.md", "b.txt", "b.txt.md", "c.txt"])
        self.assertEqual(vistos[3], self._nomes(self.raiz))  # e ao final non sobra ningún .tmp
        self.assertFalse([n for n in vistos[3] if n.endswith(".tmp")])

    def test_anonimizando_o_md_xa_esta_en_disco_antes_do_seguinte(self):
        self._tres_docx()
        vistos = {}
        self._converter_vixiando(self.raiz, lambda f: vistos.update({f: self._nomes(self.raiz)}),
                                 anonimizar=True, rexistro=self.rexistro)
        for feito, n_md in ((0, 0), (1, 1), (2, 2), (3, 3)):
            self.assertEqual(len([n for n in vistos[feito] if n.endswith(".md")]), n_md, vistos[feito])
        for md in self.raiz.glob("*.md"):
            self._sen_datos(md.read_text(encoding="utf-8"))

    def test_fallo_a_metade_sen_anonimizar_deixa_os_anteriores(self):
        self._tres_txt()
        with self.assertRaises(_Fallo) as c:
            self._converter_vixiando(self.raiz, lambda f: None, fallar_en=2)
        self.assertEqual(self._nomes(self.raiz), ["a.txt", "a.txt.md", "b.txt", "b.txt.md", "c.txt"])
        parcial = c.exception.resultado_parcial
        self.assertEqual(sorted(Path(s).name for s in parcial.saidas), ["a.txt.md", "b.txt.md"])
        self.assertIn("Texto do documento b.", (self.raiz / "b.txt.md").read_text(encoding="utf-8"))

    def test_fallo_a_metade_anonimizando_deixa_os_anteriores(self):
        self._tres_docx()
        with self.assertRaises(_Fallo) as c:
            self._converter_vixiando(self.raiz, lambda f: None, fallar_en=2, anonimizar=True,
                                     rexistro=self.rexistro)
        mds = sorted(self.raiz.glob("*.md"))
        self.assertEqual(len(mds), 2)
        for md in mds:
            texto = md.read_text(encoding="utf-8")
            self._sen_datos(texto)
            self.assertIn("anonimizado: si\n", texto)
        parcial = c.exception.resultado_parcial
        self.assertEqual(len(parcial.saidas), 2)
        self.assertEqual(len(parcial.informes), 2)
        self.assertEqual(len(parcial.documentos), 2)

    def test_documento_roto_non_para_o_lote_e_o_resto_xa_esta_escrito(self):
        self._tres_txt()
        orixinal = conversor._converter_documento

        def roto(doc, *args, **kwargs):
            if doc.nome.name == "b.txt":
                raise ValueError("ficheiro roto")
            return orixinal(doc, *args, **kwargs)

        with mock.patch.object(conversor, "_converter_documento", roto):
            resultado = conversor.converter(str(self.raiz))
        self.assertEqual(self._nomes(self.raiz), ["a.txt", "a.txt.md", "b.txt", "c.txt", "c.txt.md"])
        self.assertEqual(resultado.omitidos, [("b.txt", "erro")])
        self.assertIn("ValueError", resultado.erros["b.txt"])

    def test_md_que_non_se_pode_gardar_vai_a_erros_e_o_lote_segue(self):
        self._tres_txt()
        orixinal = conversor._escribir

        def escribir(ruta, *args, **kwargs):
            if ruta.name.startswith("b."):
                raise OSError("disco cheo")
            return orixinal(ruta, *args, **kwargs)

        with mock.patch.object(conversor, "_escribir", escribir):
            resultado = conversor.converter(str(self.raiz))
        self.assertEqual(self._nomes(self.raiz), ["a.txt", "a.txt.md", "b.txt", "c.txt", "c.txt.md"])
        self.assertEqual(resultado.omitidos, [("b.txt", "erro_escritura")])
        self.assertNotIn("b.txt", {Path(d).name for d in resultado.documentos})
        self.assertEqual(len(resultado.saidas), 2)

    def test_tres_erros_de_escritura_seguidos_paran_o_lote(self):
        for n in "abcde":
            _txt(self.raiz / f"{n}.txt", n)
        orixinal = conversor._escribir

        def escribir(ruta, *args, **kwargs):
            if ruta.name != "a.txt.md":
                raise OSError("disco cheo")
            return orixinal(ruta, *args, **kwargs)

        with mock.patch.object(conversor, "_escribir", escribir):
            with self.assertRaises(OSError) as c:
                conversor.converter(str(self.raiz))
        self.assertEqual(self._nomes(self.raiz), ["a.txt", "a.txt.md", "b.txt", "c.txt", "d.txt", "e.txt"])
        self.assertEqual(len(c.exception.resultado_parcial.erros), 3)

    def test_escritura_atomica_non_deixa_un_md_a_medias(self):
        self._tres_txt()
        antes = _txt(self.raiz / "a.txt.md", "conversión anterior")

        def morrer(*args, **kwargs):
            raise OSError("morre a media escritura")

        with mock.patch.object(conversor.os, "replace", morrer):
            resultado = conversor.converter(str(self.raiz / "a.txt"))
        # O .md anterior non se tocou (o novo ía nun .tmp): un erro de escritura, non un .md a medias.
        self.assertEqual(antes.read_text(encoding="utf-8"), "conversión anterior")
        self.assertEqual(resultado.omitidos, [("a.txt", "erro_escritura")])
        self.assertEqual(resultado.saidas, [])
        self.assertFalse([n for n in self._nomes(self.raiz) if n.endswith(".tmp")])


class TestUnSoMd(_Base):
    def _md_unico(self):
        return self.dir / "expediente.md"

    def test_durante_o_lote_so_hai_o_parcial_e_ao_final_o_definitivo(self):
        self._tres_txt()
        vistos = {}

        def vixiar(feito):
            parcial = self.dir / "expediente.md.parcial"
            vistos[feito] = (self._md_unico().exists(),
                             parcial.read_text(encoding="utf-8") if parcial.exists() else None)

        resultado = self._converter_vixiando(self.raiz, vixiar, un_so_md=True)
        self.assertEqual(vistos[0], (False, None))
        for feito in (1, 2):
            existe_md, parcial = vistos[feito]
            self.assertFalse(existe_md)  # o definitivo só existe cando está completo
            self.assertIn("conversión: incompleta\n", parcial)
            self.assertIn("# a.txt\n", parcial)
        self.assertNotIn("# b.txt", vistos[1][1])
        self.assertIn("# b.txt\n", vistos[2][1])
        self.assertNotIn("# c.txt", vistos[2][1])
        md = self._md_unico().read_text(encoding="utf-8")
        self.assertFalse((self.dir / "expediente.md.parcial").exists())
        self.assertNotIn("conversión", md)
        self.assertIn("ficheiros: 3\n", md)
        self.assertIn("1. a.txt\n2. b.txt\n3. c.txt\n", md)
        self.assertEqual(resultado.saidas, [str(self._md_unico())])
        self.assertTrue(all(d.saidas == resultado.saidas for d in resultado.documentos.values()))

    def test_igual_ca_antes_cando_remata_o_texto_do_md_unico(self):
        """O .md definitivo é o de sempre (índice, seccións, omitidos), non o do .parcial."""
        self._tres_txt()
        _txt(self.raiz / "x.dwg", "?")
        conversor.converter(str(self.raiz), un_so_md=True)
        md = self._md_unico().read_text(encoding="utf-8")
        corpo = md.split("\n---\n", 1)[1]
        self.assertTrue(corpo.lstrip().startswith("# Índice"))
        self.assertIn("- x.dwg (", corpo)
        self.assertEqual(md.count("\n# a.txt\n"), 1)

    def test_fallo_fatal_pecha_o_md_unico_coma_incompleto(self):
        self._tres_txt()
        with self.assertRaises(_Fallo) as c:
            self._converter_vixiando(self.raiz, lambda f: None, fallar_en=2, un_so_md=True)
        md = self._md_unico().read_text(encoding="utf-8")
        self.assertIn("conversión: incompleta\n", md)
        self.assertIn("ficheiros: 2\n", md)
        self.assertIn("1. a.txt\n2. b.txt\n", md)
        self.assertNotIn("c.txt", md)
        self.assertFalse((self.dir / "expediente.md.parcial").exists())
        self.assertEqual(c.exception.resultado_parcial.saidas, [str(self._md_unico())])

    def test_se_o_proceso_morre_queda_so_o_parcial_e_ningun_md_definitivo(self):
        """Un kill ou un apagado: non hai ocasión de pechar. Non debe quedar
        un `expediente.md` que pareza completo, pero si o convertido ata aí."""
        self._tres_txt()
        _txt(self.dir / "expediente.md", "OUTRA EXECUCIÓN ANTERIOR")
        with mock.patch.object(conversor._Escritor, "pechar_incompleto", lambda self: None):
            with self.assertRaises(_Fallo):
                self._converter_vixiando(self.raiz, lambda f: None, fallar_en=2, un_so_md=True)
        self.assertEqual(self._md_unico().read_text(encoding="utf-8"), "OUTRA EXECUCIÓN ANTERIOR")
        parcial = (self.dir / "expediente.md.parcial").read_text(encoding="utf-8")
        self.assertIn("conversión: incompleta\n", parcial)
        self.assertIn("# a.txt\n", parcial)
        self.assertIn("# b.txt\n", parcial)

    def test_cancelar_pecha_o_md_unico_cos_documentos_convertidos(self):
        self._tres_txt()
        chamadas = []
        with self.assertRaises(conversor.Cancelado) as c:
            conversor.converter(str(self.raiz), un_so_md=True, progreso=lambda *a: chamadas.append(a),
                                cancelar=lambda: len(chamadas) > 1)
        md = self._md_unico().read_text(encoding="utf-8")
        self.assertIn("conversión: incompleta\n", md)
        self.assertIn("ficheiros: 2\n", md)
        self.assertEqual(c.exception.resultado_parcial.saidas, [str(self._md_unico())])

    def test_cancelar_sen_ningun_documento_non_escribe_nada(self):
        self._tres_txt()
        with self.assertRaises(conversor.Cancelado):
            conversor.converter(str(self.raiz), un_so_md=True, cancelar=lambda: True)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["expediente", "rexistro"])

    def test_un_so_md_troceado_garda_as_partes_ao_pechar(self):
        for n in "ab":
            _txt(self.raiz / f"{n}.txt", ("Parágrafo longo de proba. " * 40 + "\n\n") * 6)
        resultado = conversor.converter(str(self.raiz), un_so_md=True, caracteres_por_parte=1500)
        nomes = sorted(Path(s).name for s in resultado.saidas)
        self.assertTrue(any(".parte-01." in n for n in nomes), nomes)
        self.assertTrue(any(".indice." in n for n in nomes), nomes)
        self.assertFalse((self.dir / "expediente.md.parcial").exists())
        for s in resultado.saidas:
            self.assertTrue(Path(s).read_text(encoding="utf-8").startswith("---\n"))

    def test_csv_aparte_colocase_ao_converter_e_homonimos_levan_contador(self):
        for sub in "ab":
            ruta = self.raiz / sub / "libro.csv"
            _txt(ruta, "id;importe\n" + "".join(f"{i};{i * 2}\n" for i in range(600)))
        vistos = {}
        self._converter_vixiando(self.raiz, lambda f: vistos.update({f: self._nomes(self.dir)}), un_so_md=True)
        self.assertIn("libro.datos.csv", vistos[1])  # o do primeiro xa está aló antes de converter o segundo
        self.assertNotIn("libro.datos-2.csv", vistos[1])
        self.assertIn("libro.datos-2.csv", vistos[2])
        md = self._md_unico().read_text(encoding="utf-8")
        self.assertIn("libro.datos-2.csv", md)


class TestUnSoMdAnonimizando(_Base):
    def test_zip_con_nome_de_persoa_nome_estable_desde_o_primeiro_documento(self):
        ruta_zip = self.dir / f"Expediente {_NOME}.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            for n in "abc":
                z.write(_docx(self.dir / "orixe" / f"{n}.docx"), f"{n}.docx")
        saida = self.dir / "saida"
        vistos = {}
        resultado = self._converter_vixiando(
            ruta_zip, lambda f: vistos.update({f: self._nomes(saida) if saida.exists() else []}),
            un_so_md=True, anonimizar=True, rexistro=self.rexistro, saida=str(saida))
        parcial = vistos[1]
        self.assertEqual(len(parcial), 1)
        self.assertTrue(parcial[0].endswith(".anonimizado.zip.md.parcial"), parcial)
        self._sen_datos(parcial[0])
        self.assertEqual(vistos[2], parcial)  # o mesmo nome, sen cambiar
        final = Path(resultado.saidas[0])
        self.assertEqual(final.name + ".parcial", parcial[0])
        self.assertEqual(self._nomes(saida), [final.name])
        self._sen_datos(final.read_text(encoding="utf-8"))

    def test_cancelar_a_media_leva_o_informe_ata_alí(self):
        self._tres_docx()
        chamadas = []
        with self.assertRaises(conversor.Cancelado) as c:
            conversor.converter(str(self.raiz), un_so_md=True, anonimizar=True, rexistro=self.rexistro,
                                progreso=lambda *a: chamadas.append(a), cancelar=lambda: len(chamadas) > 1)
        parcial = c.exception.resultado_parcial
        self.assertEqual(len(parcial.informes), 2)
        md = Path(parcial.saidas[0]).read_text(encoding="utf-8")
        self.assertIn("conversión: incompleta\n", md)
        self._sen_datos(md)


class TestZips(_Base):
    def _zip(self, ruta: Path, entradas: dict) -> Path:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ruta, "w") as z:
            for nome, texto in entradas.items():
                z.writestr(nome, texto)
        return ruta

    def test_zip_dentro_de_cartafol_escribe_cada_md_no_seu_subcartafol_segundo_converte(self):
        _txt(self.raiz / "a.txt", "primeiro")
        self._zip(self.raiz / "caso.zip", {"x.txt": "equis", "y.txt": "ye"})
        vistos = {}
        resultado = self._converter_vixiando(self.raiz, lambda f: vistos.update({f: self._nomes(self.raiz)}))
        self.assertNotIn("caso-md/x.txt.md", " ".join(vistos[1]))
        self.assertIn("a.txt.md", vistos[1])
        self.assertIn(str(Path("caso-md") / "x.txt.md"), vistos[2])
        self.assertNotIn(str(Path("caso-md") / "y.txt.md"), vistos[2])
        self.assertEqual(len(resultado.saidas), 3)
        self.assertTrue((self.raiz / "caso-md" / "y.txt.md").is_file())

    def test_zip_dentro_de_cartafol_anonimizando_carpeta_estable_e_sen_datos(self):
        self.raiz.mkdir()
        with zipfile.ZipFile(self.raiz / f"Poder {_NOME}.zip", "w") as z:
            for n in "ab":
                z.write(_docx(self.dir / "orixe" / f"{n}.docx"), f"{n}.docx")
        vistos = {}
        resultado = self._converter_vixiando(
            self.raiz, lambda f: vistos.update({f: [n for n in self._nomes(self.raiz) if n.endswith(".md")]}),
            anonimizar=True, rexistro=self.rexistro)
        self.assertEqual(len(vistos[1]), 1)
        for ruta in resultado.saidas:
            self._sen_datos(str(Path(ruta).relative_to(self.raiz)))
            self.assertEqual(Path(ruta).parent, Path(resultado.saidas[0]).parent)  # mesma carpeta
        self.assertEqual(vistos[1][0], str(Path(resultado.saidas[0]).relative_to(self.raiz)))

    def test_zip_de_entrada_anonimizando_carpeta_md_fixa_desde_o_primeiro(self):
        ruta_zip = self.dir / f"Expediente {_NOME}.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            for n in "abc":
                z.write(_docx(self.dir / "orixe" / f"{n}.docx"), f"{n}.docx")
        vistos = {}

        def vixiar(feito):
            vistos[feito] = sorted(p.name for p in self.dir.glob("*-md"))

        resultado = self._converter_vixiando(ruta_zip, vixiar, anonimizar=True, rexistro=self.rexistro)
        self.assertEqual(vistos[0], [])
        self.assertEqual(len(vistos[1]), 1)
        self.assertEqual(vistos[2], vistos[1])
        self.assertEqual(vistos[3], vistos[1])
        self.assertTrue(vistos[1][0].endswith(".anonimizado-md"), vistos[1])
        self._sen_datos(vistos[1][0])
        self.assertEqual({Path(s).parent.name for s in resultado.saidas}, {vistos[1][0]})
        self.assertEqual(len(resultado.saidas), 3)

    def test_colisions_de_nome_levan_contador_segundo_se_escriben(self):
        ruta_zip = self.dir / "caso.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z, warnings.catch_warnings():
            warnings.simplefilter("ignore")  # nome duplicado: o que se quere probar
            for texto in ("primeiro", "segundo", "terceiro"):
                z.writestr("nota.txt", texto)
        vistos = {}
        resultado = self._converter_vixiando(
            ruta_zip, lambda f: vistos.update({f: self._nomes(self.dir / "caso-md")}))
        self.assertEqual(vistos[1], ["nota.txt.md"])
        self.assertEqual(vistos[2], ["nota-2.txt.md", "nota.txt.md"])
        self.assertEqual(self._nomes(self.dir / "caso-md"), ["nota-2.txt.md", "nota-3.txt.md", "nota.txt.md"])
        self.assertEqual(len(resultado.saidas), 3)
        self.assertIn("primeiro", (self.dir / "caso-md" / "nota.txt.md").read_text(encoding="utf-8"))
        self.assertIn("terceiro", (self.dir / "caso-md" / "nota-3.txt.md").read_text(encoding="utf-8"))

    def test_colisions_anonimizando(self):
        ruta_zip = self.dir / "caso.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z, warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(2):
                z.write(_docx(self.dir / "orixe" / "nota.docx"), "nota.docx")
        resultado = conversor.converter(str(ruta_zip), anonimizar=True, rexistro=self.rexistro)
        self.assertEqual(sorted(Path(s).name for s in resultado.saidas),
                         ["nota-2.anonimizado.docx.md", "nota.anonimizado.docx.md"])
        for s in resultado.saidas:
            self._sen_datos(Path(s).read_text(encoding="utf-8"))


class TestPartes(_Base):
    def test_o_md_troceado_xa_esta_en_disco_con_cabeceira_en_cada_parte(self):
        _txt(self.raiz / "a.txt", ("Parágrafo longo de proba. " * 40 + "\n\n") * 6)
        _txt(self.raiz / "b.txt", "curto")
        vistos = {}
        self._converter_vixiando(self.raiz, lambda f: vistos.update({f: self._nomes(self.raiz)}),
                                 caracteres_por_parte=1500)
        self.assertIn("a.txt.parte-01.md", vistos[1])
        self.assertIn("a.txt.indice.md", vistos[1])
        self.assertNotIn("a.txt.md", vistos[1])
        for n in vistos[1]:
            if n.endswith(".md"):
                self.assertTrue((self.raiz / n).read_text(encoding="utf-8").startswith("---\norixe: a.txt\n"), n)

    def test_posibles_fugas_vai_en_todas_as_partes(self):
        _docx(self.raiz / "a.docx", _RISCO + "\n\n" + _longo())
        conversor.converter(str(self.raiz), anonimizar=True, rexistro=self.rexistro, caracteres_por_parte=1500)
        partes = sorted(self.raiz.glob("*.parte-*.md"))
        self.assertGreaterEqual(len(partes), 2)
        for p in partes:
            self.assertRegex(p.read_text(encoding="utf-8").split("\n---\n")[0], r"posibles_fugas: \d+")


class TestCancelarEParadaManual(_Base):
    def test_cancelar_conserva_o_escrito_e_di_o_que_e(self):
        self._tres_txt()
        chamadas = []
        with self.assertRaises(conversor.Cancelado) as c:
            conversor.converter(str(self.raiz), progreso=lambda *a: chamadas.append(a),
                                cancelar=lambda: len(chamadas) > 1)
        parcial = c.exception.resultado_parcial
        self.assertEqual(sorted(Path(s).name for s in parcial.saidas), ["a.txt.md", "b.txt.md"])
        self.assertEqual(self._nomes(self.raiz), ["a.txt", "a.txt.md", "b.txt", "b.txt.md", "c.txt"])
        self.assertEqual(parcial.tokens_antes > 0, True)

    def test_cancelar_na_parada_manual_deixa_os_anteriores_revisados(self):
        self._tres_docx()

        def revisar(nome, texto, contexto, texto_anon, informe, substitucions):
            if nome == "c.docx":
                raise conversor.Cancelado
            return texto_anon, substitucions

        with self.assertRaises(conversor.Cancelado) as c:
            conversor.converter(str(self.raiz), anonimizar=True, rexistro=self.rexistro, revisar=revisar)
        mds = sorted(self.raiz.glob("*.md"))
        self.assertEqual(len(mds), 2)
        for md in mds:
            texto = md.read_text(encoding="utf-8")
            self.assertIn("revisado: si\n", texto)
            self._sen_datos(texto)
        self.assertEqual(len(c.exception.resultado_parcial.revisados), 2)

    def test_parada_manual_escribe_o_documento_ao_devolver_a_revision(self):
        self._tres_docx()
        vistos = []

        def revisar(nome, texto, contexto, texto_anon, informe, substitucions):
            vistos.append((nome, len(list(self.raiz.glob("*.md")))))
            return texto_anon, substitucions

        conversor.converter(str(self.raiz), anonimizar=True, rexistro=self.rexistro, revisar=revisar)
        self.assertEqual(vistos, [("a.docx", 0), ("b.docx", 1), ("c.docx", 2)])
        self.assertEqual(len(list(self.raiz.glob("*.md"))), 3)


class TestRevisionPosteriorSobreMdEscritos(_Base):
    """En automático o lote remata, os .md xa están en disco, e a persoa revisa
    despois: `substituir_revisado` reescríbeos e quita `posibles_fugas`."""

    def _automatico(self, **opcions):
        _docx(self.raiz / "con_risco.docx", _RISCO)
        _docx(self.raiz / "limpo.docx", "O xulgado de Lugo cita ás partes para o día dez.")
        capturas = {}

        def revisar(nome, texto, contexto, texto_anon, informe, substitucions):
            capturas[nome] = (texto, contexto, texto_anon, informe, substitucions)
            return None  # automático

        resultado = conversor.converter(str(self.raiz), anonimizar=True, rexistro=self.rexistro,
                                        revisar=revisar, **opcions)
        return resultado, capturas

    def _revisar_con_risco(self, resultado, capturas):
        _, contexto, texto_anon, informe, substitucions = capturas["con_risco.docx"]
        return conversor.substituir_revisado(
            resultado, "con_risco.docx", texto_anon.replace("34867809", "[NÚMERO]"), substitucions, contexto)

    def test_ccada_md_xa_escrito_e_a_marca_de_fugas(self):
        resultado, _ = self._automatico()
        md = next(self.raiz.glob("con_risco*.md")).read_text(encoding="utf-8")
        self.assertRegex(md.split("\n---\n")[0], r"revisado: non\nposibles_fugas: \d+")
        self.assertIn("34867809", md)
        limpo = next(self.raiz.glob("limpo*.md")).read_text(encoding="utf-8")
        self.assertNotIn("posibles_fugas", limpo)

    def test_revisar_reescribe_o_md_xa_escrito_e_quita_posibles_fugas(self):
        resultado, capturas = self._automatico()
        ruta = next(self.raiz.glob("con_risco*.md"))
        antes = self._nomes(self.raiz)
        antigas, novas = self._revisar_con_risco(resultado, capturas)
        self.assertEqual(antigas, [str(ruta)])
        self.assertEqual(novas, [str(ruta)])
        md = ruta.read_text(encoding="utf-8")
        self.assertIn("revisado: si\n", md)
        self.assertNotIn("posibles_fugas", md)
        self.assertNotIn("34867809", md)
        self.assertIn("[NÚMERO]", md)
        self._sen_datos(md)
        self.assertEqual(self._nomes(self.raiz), antes)  # nin ficheiros novos nin .tmp
        limpo = next(self.raiz.glob("limpo*.md")).read_text(encoding="utf-8")
        self.assertIn("revisado: non\n", limpo)
        self.assertEqual(sorted(resultado.saidas), sorted(str(p) for p in self.raiz.glob("*.md")))
        self.assertEqual(len(resultado.revisados), 1)

    def test_revisar_con_partes_cambia_as_partes_sen_perder_ningunha_antes_de_tempo(self):
        _docx(self.raiz / "con_risco.docx", _RISCO + "\n\n" + _longo())
        capturas = {}
        resultado = conversor.converter(
            str(self.raiz), anonimizar=True, rexistro=self.rexistro, caracteres_por_parte=1500,
            revisar=lambda nome, t, ctx, ta, inf, sub: capturas.update({nome: (t, ctx, ta, inf, sub)}))
        antes = {Path(s).name for s in resultado.saidas}
        self.assertTrue(any(".parte-01." in n for n in antes))
        _, contexto, texto_anon, _, substitucions = capturas["con_risco.docx"]
        antigas, novas = conversor.substituir_revisado(
            resultado, "con_risco.docx", texto_anon.replace("34867809", "[NÚMERO]"), substitucions, contexto)
        despois = {p.name for p in self.raiz.glob("*.md")}
        self.assertEqual(despois, {Path(s).name for s in novas})
        for p in self.raiz.glob("*.md"):
            md = p.read_text(encoding="utf-8")
            self.assertNotIn("posibles_fugas", md)
            self.assertNotIn("34867809", md)

    def test_revisar_con_un_so_md_rescribe_o_md_unico_sen_perder_o_resto(self):
        resultado, capturas = self._automatico(un_so_md=True)
        ruta = Path(resultado.saidas[0])
        antes = ruta.read_text(encoding="utf-8")
        cab = antes.split("\n---\n")[0]
        self.assertRegex(cab, r"posibles_fugas: \d+")
        self.assertEqual(len(re.findall(r"posibles_fugas: \d+", antes)), 2)
        self.assertFalse(list(self.dir.glob("*.parcial")))
        self._revisar_con_risco(resultado, capturas)
        md = ruta.read_text(encoding="utf-8")
        self.assertNotIn("posibles_fugas", md)
        self.assertNotIn("34867809", md)
        self.assertIn("Lugo", md)
        self.assertIn("ficheiros: 2\n", md)
        self.assertEqual(sorted(p.name for p in self.dir.glob("*.md*")), [ruta.name])

    def test_revisar_despois_de_cancelar_un_so_md_mantén_a_marca_incompleta(self):
        _docx(self.raiz / "con_risco.docx", _RISCO)
        _docx(self.raiz / "limpo.docx", "O xulgado de Lugo cita ás partes.")
        capturas, chamadas = {}, []
        with self.assertRaises(conversor.Cancelado) as c:
            conversor.converter(
                str(self.raiz), anonimizar=True, un_so_md=True, rexistro=self.rexistro,
                revisar=lambda nome, t, ctx, ta, inf, sub: capturas.update({nome: (t, ctx, ta, inf, sub)}),
                progreso=lambda *a: chamadas.append(a), cancelar=lambda: len(chamadas) > 0)
        parcial = c.exception.resultado_parcial
        self.assertEqual(list(parcial.documentos), ["con_risco.docx"])
        _, contexto, texto_anon, _, substitucions = capturas["con_risco.docx"]
        conversor.substituir_revisado(parcial, "con_risco.docx",
                                      texto_anon.replace("34867809", "[NÚMERO]"), substitucions, contexto)
        md = Path(parcial.saidas[0]).read_text(encoding="utf-8")
        self.assertIn("conversión: incompleta\n", md)
        self.assertNotIn("posibles_fugas", md)
        self.assertNotIn("34867809", md)


class TestNomeDoZipSenAlterarOContido(_Base):
    def test_o_nome_do_zip_non_se_rexistra_antes_do_contido(self):
        """O nome do .zip anonimízase DESPOIS do primeiro documento: a persoa non
        queda rexistrada antes do contido (non cambia o seu código nin o seu
        aviso de posible homónimo)."""
        ruta_zip = self.dir / f"Expediente {_NOME}.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            z.write(_docx(self.dir / "orixe" / "a.docx"), "a.docx")
        rexistro_visto = []

        def revisar(nome, texto, contexto, texto_anon, informe, substitucions):
            rexistro_visto.append(len(self.rexistro._estado["persoas"]))
            return None

        conversor.converter(str(ruta_zip), anonimizar=True, rexistro=self.rexistro, revisar=revisar)
        # Ao anonimizar o contido só está a súa persoa (con DNI): a do nome do .zip aínda non se rexistrou.
        self.assertEqual(rexistro_visto, [1])


if __name__ == "__main__":
    unittest.main()
