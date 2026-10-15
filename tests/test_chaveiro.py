"""Xestión da clave de cifrado no chaveiro do sistema operativo (informe,
sección 07, punto crítico: "en produción debe moverse a un chaveiro do
sistema operativo ou token de hardware").

IMPORTANTE: ningún test aquí toca o chaveiro REAL de macOS/Windows -- iso
podería abrir un diálogo de autorización do sistema que bloquease a suite
agardando a un humano que nunca chega. En vez diso, substitúese o módulo
`keyring` por un dobre de proba en memoria (`_ChaveiroFalso`).
"""
import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import registry as registry_mod
from anonimizador.pipeline import anonimizar_texto
from anonimizador.registry import RexistroCorrespondencias


class _ChaveiroFalso:
    def __init__(self):
        self.almacen = {}

    def get_password(self, servizo, id_):
        return self.almacen.get((servizo, id_))

    def set_password(self, servizo, id_, valor):
        self.almacen[(servizo, id_)] = valor


class _ChaveiroQueFalla:
    def get_password(self, servizo, id_):
        raise RuntimeError("chaveiro non dispoñible (simulado)")

    def set_password(self, servizo, id_, valor):
        raise RuntimeError("chaveiro non dispoñible (simulado)")


class TestChaveiroSistema(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_por_defecto_nunca_escribe_no_chaveiro(self):
        """`usar_chaveiro=False` (por defecto, coma en todos os demais
        tests da suite) non debe escribir no chaveiro en ningún caso --
        garante que os máis de 80 tests existentes nunca tocan o chaveiro
        real do sistema operativo."""
        chaveiro = mock.Mock()
        with mock.patch.object(registry_mod, "keyring", chaveiro), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            rexistro = RexistroCorrespondencias(self.dir)
        self.assertEqual(rexistro.orixe_clave, "ficheiro")
        chaveiro.set_password.assert_not_called()
        self.assertTrue((Path(self.dir) / "clave.key").exists())
        self.assertFalse((Path(self.dir) / "clave.chaveiro").exists())

    def test_sen_marcador_nin_flag_nunca_consulta_o_chaveiro(self):
        """Sen `usar_chaveiro=True` E sen un rexistro previo que xa o use
        (sen ficheiro marcador), o chaveiro NIN SEQUERA se consulta para
        ler -- así ningún test ou script "por defecto" bate contra o
        chaveiro real do sistema operativo."""
        chaveiro = mock.Mock()
        with mock.patch.object(registry_mod, "keyring", chaveiro), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            RexistroCorrespondencias(self.dir)
        chaveiro.get_password.assert_not_called()
        chaveiro.set_password.assert_not_called()

    def test_usar_chaveiro_garda_a_clave_ali_en_vez_de_en_ficheiro(self):
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            rexistro = RexistroCorrespondencias(self.dir, usar_chaveiro=True)
        self.assertEqual(rexistro.orixe_clave, "chaveiro_sistema")
        self.assertFalse((Path(self.dir) / "clave.key").exists())
        self.assertEqual(len(falso.almacen), 1)
        # o marcador (sen datos sensibles) SI queda no disco, para que
        # futuras aperturas saiban onde mirar sen ter que adiviñar
        self.assertTrue((Path(self.dir) / "clave.chaveiro").exists())

    def test_marcador_non_contén_a_clave_en_claro(self):
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            RexistroCorrespondencias(self.dir, usar_chaveiro=True)
        contido = (Path(self.dir) / "clave.chaveiro").read_text(encoding="utf-8")
        (clave_real,) = falso.almacen.values()
        self.assertNotIn(clave_real, contido)

    def test_recupera_a_mesma_clave_en_execucions_distintas(self):
        """Coma `test_consistencia_persiste_entre_execucions_distintas`
        (test_pipeline.py) pero coa clave no chaveiro: unha segunda
        apertura do rexistro (outro proceso CLI, a interface web), SEN
        pedir `usar_chaveiro=True` explicitamente, ten que atopar
        igualmente a clave xa gardada -- porque xa existe o marcador -- e
        poder descifrar o que gardou a primeira."""
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            rexistro1 = RexistroCorrespondencias(self.dir, usar_chaveiro=True)
            anonimizar_texto(
                "Manuel Ferrándiz Salcedo, con DNI 30014811-Z, declarou.", rexistro1
            )
            rexistro1.definir_contrasinal_reversion("contrasinal_proba_1234")

            rexistro2 = RexistroCorrespondencias(self.dir)  # sen usar_chaveiro=True
            self.assertEqual(rexistro2.orixe_clave, "chaveiro_sistema")
            dados = rexistro2.reverter("PERSOA_000001", "proba", "contrasinal_proba_1234")
            self.assertIn("Manuel Ferrándiz Salcedo", dados["nomes"])

    def test_fallo_do_chaveiro_ao_crear_recae_en_ficheiro(self):
        falla = _ChaveiroQueFalla()
        with mock.patch.object(registry_mod, "keyring", falla), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            rexistro = RexistroCorrespondencias(self.dir, usar_chaveiro=True)
        self.assertEqual(rexistro.orixe_clave, "ficheiro")
        self.assertTrue((Path(self.dir) / "clave.key").exists())
        self.assertFalse((Path(self.dir) / "clave.chaveiro").exists())

    def test_ficheiro_existente_ten_prioridade_sobre_o_chaveiro(self):
        """Compatibilidade cara atrás: un rexistro xa creado con clave en
        ficheiro segue a funcionar igual aínda que se abra despois con
        `usar_chaveiro=True`."""
        RexistroCorrespondencias(self.dir)  # crea clave.key
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            rexistro = RexistroCorrespondencias(self.dir, usar_chaveiro=True)
        self.assertEqual(rexistro.orixe_clave, "ficheiro")
        self.assertEqual(len(falso.almacen), 0)

    def test_marcador_sen_libraria_keyring_instalada_falla_con_claridade(self):
        """Se por algún motivo se move un rexistro (co seu marcador) a un
        ordenador sen a libraría 'keyring' instalada, non debe crear
        silenciosamente unha clave NOVA (que xa non podería descifrar
        nada) -- ten que fallar cun erro claro."""
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            RexistroCorrespondencias(self.dir, usar_chaveiro=True)

        with mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", False):
            with self.assertRaises(RuntimeError):
                RexistroCorrespondencias(self.dir)

    def test_marcador_sen_a_clave_no_chaveiro_falla_con_claridade(self):
        """Marcador presente pero a entrada xa non está no chaveiro (ex.
        borrada, ou copiado o cartafol a outro ordenador sen migrar a
        clave) -- fallar claramente en vez de xerar unha clave nova que
        xa non cadraría co contido cifrado existente."""
        falso = _ChaveiroFalso()
        with mock.patch.object(registry_mod, "keyring", falso), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            RexistroCorrespondencias(self.dir, usar_chaveiro=True)
            falso.almacen.clear()
            with self.assertRaises(RuntimeError):
                RexistroCorrespondencias(self.dir)


if __name__ == "__main__":
    unittest.main()


class TestRexistroMovidoDeCartafol(unittest.TestCase):
    """04/10/2026: en Mac/Linux o rexistro pasa a vivir fóra do cartafol do
    programa. O nome da clave no chaveiro era a RUTA do cartafol, así que
    mover ou copiar `datos_rexistro` deixábao sen poder abrirse. Agora lese o
    identificador gardado en `clave.chaveiro`."""

    def test_rexistro_movido_segue_abrindo(self):
        import shutil
        chaveiro = _ChaveiroFalso()
        with tempfile.TemporaryDirectory() as base, \
             mock.patch.object(registry_mod, "keyring", chaveiro), \
             mock.patch.object(registry_mod, "_KEYRING_DISPONIBLE", True):
            orixe = Path(base) / "programa" / "datos_rexistro"
            orixe.parent.mkdir()
            rexistro = RexistroCorrespondencias(str(orixe), usar_chaveiro=True)
            self.assertEqual(rexistro.orixe_clave, "chaveiro_sistema")
            anon, _ = anonimizar_texto("Comparece don Xoán Páez Veiga, con DNI 30014811H.", rexistro)
            rexistro.definir_contrasinal_reversion("proba-movido-1234")
            destino = Path(base) / "datos_fora" / "datos_rexistro"
            destino.parent.mkdir()
            shutil.move(str(orixe), str(destino))
            movido = RexistroCorrespondencias(str(destino), usar_chaveiro=True)
            datos = movido.reverter("PERSOA_000001", "proba", "proba-movido-1234")
            self.assertIn("Xoán Páez Veiga", str(datos))
