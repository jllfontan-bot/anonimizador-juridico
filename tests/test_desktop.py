import os

# Estas probas escribíronse coa interface e os códigos en galego (PERSOA_...).
os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import desktop


class TestDesktop(unittest.TestCase):
    """Non abre unha xanela real (`webview.start()` bloquearía e
    necesitaría un servidor de pantalla) -- mockea `webview` para
    comprobar só o que si depende deste módulo: que o servidor Flask
    arrinca nun fío á parte e que se agarda a que responda antes de
    intentar abrir a xanela."""

    def test_executar_agarda_o_servidor_e_abre_a_xanela(self):
        with mock.patch.object(desktop, "webview") as webview_falso, \
             mock.patch.object(desktop.web, "executar") as executar_falso, \
             mock.patch.object(desktop, "_agardar_servidor") as agardar_falso:
            desktop.executar(porto=5123, usar_chaveiro=True)

            agardar_falso.assert_called_once_with(5123)
            webview_falso.create_window.assert_called_once()
            args, kwargs = webview_falso.create_window.call_args
            self.assertIn("http://127.0.0.1:5123/", args)
            webview_falso.start.assert_called_once()

        # o servidor Flask real arrinca nun FÍO -- dáselle tempo a executarse
        import time
        time.sleep(0.2)
        executar_falso.assert_called_once_with(porto=5123, usar_chaveiro=True)

    def test_cae_ao_navegador_se_a_xanela_nativa_falla(self):
        """Caso Linux sen GTK+WebKit2 instalado: `webview.start()` falla en
        tempo de execución -- non ten que romper o programa, ten que abrir
        o navegador coma reserva (có servidor xa arrincado)."""
        with mock.patch.object(desktop, "webview") as webview_falso, \
             mock.patch.object(desktop.web, "executar"), \
             mock.patch.object(desktop, "_agardar_servidor"), \
             mock.patch.object(desktop, "webbrowser") as navegador_falso:
            webview_falso.start.side_effect = RuntimeError("sen backend GTK")
            desktop.executar(porto=5125)

            navegador_falso.open.assert_called_once_with("http://127.0.0.1:5125/")

    def test_agardar_servidor_devolve_en_canto_o_servidor_responde(self):
        import threading

        from anonimizador import web

        fio = threading.Thread(
            target=web.executar, kwargs={"porto": 5124}, daemon=True,
        )
        fio.start()
        try:
            desktop._agardar_servidor(5124, intentos=50, espera=0.05)
        finally:
            pass  # o fío é daemon, remata co proceso de test


if __name__ == "__main__":
    unittest.main()
