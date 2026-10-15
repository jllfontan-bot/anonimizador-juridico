"""Concorrencia no rexistro de correspondencias (erro A1).

Fallo real: cada instancia de `RexistroCorrespondencias` cargaba o estado
ao crearse e despois reescribía o estado COMPLETO en disco. Con dúas
instancias sobre o mesmo cartafol (a interface web abre unha no fío do
lote e outra ao confirmar unha revisión; ou CLI e aplicación á vez), a
última en gardar pisaba á outra e o contador `seguinte_numero` repetíase:
DÚAS PERSOAS DISTINTAS co MESMO código -- ao reverter, un código
apuntaba á persoa equivocada.

Todos os nomes e DNI son sintéticos.
"""

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))

from anonimizador.registry import RexistroCorrespondencias
from anonimizador.resolution import Grupo

_CONTRASINAL = "contrasinal_proba_1234"


def _nomes_por_codigo(rexistro: RexistroCorrespondencias) -> dict:
    return {c: d["nomes"] for c, d in rexistro._estado["persoas"].items()}


class TestDuasInstancias(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_dúas_instancias_non_repiten_codigo(self):
        r1 = RexistroCorrespondencias(self.dir)
        r2 = RexistroCorrespondencias(self.dir)
        c1, *_ = r1.resolver_ou_crear(Grupo(representante="Ana Pérez Gil"))
        c2, *_ = r2.resolver_ou_crear(Grupo(representante="Luis Mato Rey"))
        self.assertNotEqual(c1, c2)

        recargado = RexistroCorrespondencias(self.dir)
        nomes = _nomes_por_codigo(recargado)
        self.assertEqual(nomes.get(c1), ["Ana Pérez Gil"])
        self.assertEqual(nomes.get(c2), ["Luis Mato Rey"])

    def test_dni_rexistrado_por_outra_instancia_recupérase(self):
        r1 = RexistroCorrespondencias(self.dir)
        r2 = RexistroCorrespondencias(self.dir)
        c1, *_ = r1.resolver_ou_crear(Grupo(representante="Ana Pérez Gil", dni="11111111H"))
        c2, *_ = r2.resolver_ou_crear(Grupo(representante="Ana Pérez", dni="11111111H"))
        self.assertEqual(c1, c2)
        self.assertEqual(r2.codigo_por_dni("11111111H"), c1)
        self.assertEqual(c1, "PERSOA_000001")

    def test_lecturas_ven_persoas_creadas_por_outra_instancia(self):
        r1 = RexistroCorrespondencias(self.dir)
        r2 = RexistroCorrespondencias(self.dir)
        r1.definir_contrasinal_reversion(_CONTRASINAL)
        codigo, *_ = r1.resolver_ou_crear(Grupo(representante="Ana Pérez Gil", dni="22222222J"))
        self.assertTrue(r2.ten_contrasinal_reversion())
        self.assertEqual(r2.codigo_por_dni("22222222J"), codigo)
        dados = r2.reverter(codigo, "proba de concorrencia", _CONTRASINAL)
        self.assertEqual(dados["nomes"], ["Ana Pérez Gil"])

    def test_fusion_non_se_perde_por_outra_instancia(self):
        r1 = RexistroCorrespondencias(self.dir)
        r2 = RexistroCorrespondencias(self.dir)
        a, *_ = r1.resolver_ou_crear(Grupo(representante="Ana Pérez Gil"))
        b, *_ = r1.resolver_ou_crear(Grupo(representante="Ana Pérez Gil"))
        r2.fusionar(a, b)
        c, *_ = r1.resolver_ou_crear(Grupo(representante="Luis Mato Rey"))
        recargado = RexistroCorrespondencias(self.dir)
        self.assertNotIn(b, recargado._estado["persoas"])
        self.assertEqual(recargado._estado["alias"].get(b), a)
        self.assertIn(c, recargado._estado["persoas"])
        self.assertNotIn(c, (a, b))

    def test_sesions_de_dúas_instancias_consérvanse(self):
        r1 = RexistroCorrespondencias(self.dir)
        r2 = RexistroCorrespondencias(self.dir)
        r1.gardar_sesion("s1", {"confirmado": False})
        r2.gardar_sesion("s2", {"confirmado": False})
        self.assertEqual(set(RexistroCorrespondencias(self.dir).ler_sesions_pendentes()), {"s1", "s2"})


class TestFíosConcorrentes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_fíos_con_instancias_propias_non_repiten_codigos(self):
        n_fíos, por_fío = 6, 15
        resultados: dict = {}
        erros: list = []
        barreira = threading.Barrier(n_fíos)

        def traballo(i):
            try:
                rexistro = RexistroCorrespondencias(self.dir)
                barreira.wait()
                for j in range(por_fío):
                    nome = f"Persoa Sintética F{i} N{j}"
                    codigo, *_ = rexistro.resolver_ou_crear(Grupo(representante=nome))
                    resultados[nome] = codigo
                    rexistro.gardar_sesion(f"f{i}_{j}", {"confirmado": False})
            except Exception as e:  # pragma: no cover - só para diagnóstico
                erros.append(e)

        fíos = [threading.Thread(target=traballo, args=(i,)) for i in range(n_fíos)]
        for f in fíos:
            f.start()
        for f in fíos:
            f.join()

        self.assertEqual(erros, [])
        total = n_fíos * por_fío
        self.assertEqual(len(set(resultados.values())), total, "códigos repetidos entre persoas distintas")

        recargado = RexistroCorrespondencias(self.dir)
        nomes = _nomes_por_codigo(recargado)
        self.assertEqual(len(nomes), total)
        for nome, codigo in resultados.items():
            self.assertEqual(nomes[codigo], [nome])
        self.assertEqual(recargado._estado["seguinte_numero"], total + 1)
        self.assertEqual(len(recargado.ler_sesions_pendentes()), total)
        self.assertEqual(
            sum(1 for e in recargado.ler_auditoria() if e["accion"] == "crear_novo"), total
        )


_SCRIPT_PROCESO = """
import sys
sys.path.insert(0, sys.argv[1])
from anonimizador.registry import RexistroCorrespondencias
from anonimizador.resolution import Grupo
r = RexistroCorrespondencias(sys.argv[2])
for j in range(int(sys.argv[4])):
    codigo, *_ = r.resolver_ou_crear(Grupo(representante=f"Persoa Sintética P{sys.argv[3]} N{j}"))
    print(codigo, flush=True)
"""


class TestProcesosConcorrentes(unittest.TestCase):
    def test_varios_procesos_non_repiten_codigos(self):
        with tempfile.TemporaryDirectory() as d:
            # crear a clave antes, para que todos os procesos a compartan
            RexistroCorrespondencias(d)
            n_procesos, por_proceso = 4, 15
            procesos = [
                subprocess.Popen(
                    [sys.executable, "-c", _SCRIPT_PROCESO, str(_SRC), d, str(i), str(por_proceso)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                for i in range(n_procesos)
            ]
            codigos = []
            for p in procesos:
                saida, erro = p.communicate(timeout=180)
                self.assertEqual(p.returncode, 0, erro)
                codigos.extend(saida.split())

            total = n_procesos * por_proceso
            self.assertEqual(len(codigos), total)
            self.assertEqual(len(set(codigos)), total, "códigos repetidos entre procesos")
            recargado = RexistroCorrespondencias(d)
            self.assertEqual(len(recargado._estado["persoas"]), total)
            self.assertEqual(recargado._estado["seguinte_numero"], total + 1)

    def test_clave_nova_creada_a_vez_por_varios_procesos_é_unha_soa(self):
        with tempfile.TemporaryDirectory() as d:
            procesos = [
                subprocess.Popen(
                    [sys.executable, "-c", _SCRIPT_PROCESO, str(_SRC), d, str(i), "3"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                for i in range(4)
            ]
            for p in procesos:
                _, erro = p.communicate(timeout=180)
                self.assertEqual(p.returncode, 0, erro)
            recargado = RexistroCorrespondencias(d)
            self.assertEqual(len(recargado._estado["persoas"]), 12)


if __name__ == "__main__":
    unittest.main()
