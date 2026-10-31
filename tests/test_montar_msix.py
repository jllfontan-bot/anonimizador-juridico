"""Montaxe do cartafol dos paquetes MSIX (`instalador/msix/montar_msix.py`):
o do anonimizador sae igual ca sempre e o do conversor co seu manifesto,
a súa versión e a súa icona."""

import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MONTAR = RAIZ / "instalador" / "msix" / "montar_msix.py"
_NS = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}
_PARAMETROS = "{http://schemas.microsoft.com/appx/manifest/uap/windows10/10}Parameters"


def _version_conversor() -> str:
    codigo = (RAIZ / "src" / "anonimizador" / "conversor.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "([^"]+)"$', codigo, re.M).group(1)


class TestMontarMsix(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.staging = Path(self._tmp.name) / "staging-windows"
        (self.staging / "runtime" / "python" / "Lib" / "site-packages").mkdir(parents=True)
        (self.staging / "runtime" / "python" / "pythonw.exe").write_bytes(b"MZ")
        (self.staging / "anonimizador-xuridico").mkdir()
        (self.staging / "Iniciar-Anonimizador.vbs").write_text("lanzador clasico", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def montar(self, *app) -> Path:
        destino = Path(self._tmp.name) / ("msix-" + (app[0] if app else "defecto"))
        subprocess.run([sys.executable, str(MONTAR), str(self.staging), str(destino), *app],
                       check=True, capture_output=True, text=True)
        return destino

    def test_anonimizador_sae_igual_ca_sempre(self):
        version = (RAIZ / "VERSION").read_text(encoding="utf-8").strip() + ".0"
        esperado = (RAIZ / "instalador" / "msix" / "AppxManifest.xml").read_text(encoding="utf-8")
        for destino in (self.montar(), self.montar("anonimizador")):
            self.assertEqual((destino / "AppxManifest.xml").read_text(encoding="utf-8"),
                             esperado.replace("{VERSION}", version))
            self.assertFalse((destino / "Iniciar-Anonimizador.vbs").exists())
            self.assertTrue((destino / "runtime" / "python" / "Lib" / "site-packages" / "anonimizador.pth").is_file())

    def test_conversor_co_seu_manifesto_version_e_icona(self):
        conversor, anonimizador = self.montar("conversor"), self.montar("anonimizador")
        paquete = ET.parse(conversor / "AppxManifest.xml").getroot()
        identidade = paquete.find("m:Identity", _NS)
        self.assertEqual(identidade.get("Version"), _version_conversor() + ".0")
        # O mesmo Publisher (a mesma conta) e outro Name: outra aplicación na Store.
        anon = ET.parse(anonimizador / "AppxManifest.xml").getroot().find("m:Identity", _NS)
        self.assertEqual(identidade.get("Publisher"), anon.get("Publisher"))
        self.assertNotEqual(identidade.get("Name"), anon.get("Name"))
        aplicacion = paquete.find("m:Applications/m:Application", _NS)
        self.assertEqual(aplicacion.get(_PARAMETROS), "-m anonimizador.arranque_conversor")
        self.assertEqual(paquete.find("m:Properties/m:DisplayName", _NS).text, "Conversor de archivos para IA")
        for nome in ("Square44x44Logo.png", "Square150x150Logo.png", "StoreLogo.png", "Wide310x150Logo.png"):
            self.assertTrue((conversor / "Assets" / nome).is_file())
        self.assertNotEqual((conversor / "Assets" / "StoreLogo.png").read_bytes(),
                            (anonimizador / "Assets" / "StoreLogo.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
