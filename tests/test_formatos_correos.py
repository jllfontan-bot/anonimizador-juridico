"""Correos gardados (.eml) a Markdown, SEN anonimizar
(`formatos/correos.py`, conversor a .md)."""

import os
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import formatos
from anonimizador.formatos import correos


def _correo(corpo="Bo día:\n\nEnvío a demanda.\n\nSaúdos", html=None, asunto="Demanda do caso 12/2026",
            **cabeceiras) -> EmailMessage:
    mensaxe = EmailMessage()
    mensaxe["Subject"] = asunto
    mensaxe["From"] = "Ana Pena <ana@despacho.example>"
    mensaxe["To"] = "Xan Souto <xan@cliente.example>"
    mensaxe["Cc"] = "Uxía Rey <uxia@despacho.example>"
    mensaxe["Date"] = "Sat, 31 Oct 2026 10:15:00 +0100"
    mensaxe["Message-ID"] = "<ID-SECRETO-123@despacho.example>"
    mensaxe["Received"] = "from mail.example (IP-ESCONDIDA 192.0.2.7) by mx.example"
    mensaxe["X-Originating-IP"] = "[198.51.100.9]"
    mensaxe["Return-Path"] = "<rebote-escondido@despacho.example>"
    for nome, valor in cabeceiras.items():
        mensaxe[nome.replace("_", "-")] = valor
    if corpo is not None:
        mensaxe.set_content(corpo)
    if html is not None:
        if corpo is None:
            mensaxe.set_content(html, subtype="html")
        else:
            mensaxe.add_alternative(html, subtype="html")
    return mensaxe


class TestCorreos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def gardar(self, mensaxe, nome="correo.eml") -> str:
        ruta = self.dir / nome
        ruta.write_bytes(bytes(mensaxe) if not isinstance(mensaxe, bytes) else mensaxe)
        return str(ruta)

    def md(self, mensaxe, nome="correo.eml") -> str:
        return correos.a_markdown(self.gardar(mensaxe, nome))

    def test_asunto_cabeceiras_visibles_e_corpo(self):
        md = self.md(_correo())
        self.assertTrue(md.startswith("# Demanda do caso 12/2026\n"), md)
        self.assertIn("- De: Ana Pena <ana@despacho.example>", md)
        self.assertIn("- Para: Xan Souto <xan@cliente.example>", md)
        self.assertIn("- Cc: Uxía Rey <uxia@despacho.example>", md)
        self.assertIn("- Data: 2026-10-31 10:15", md)
        self.assertIn("Bo día:\n\nEnvío a demanda.\n\nSaúdos", md)

    def test_cabeceiras_tecnicas_quedan_fora(self):
        md = self.md(_correo())
        for escondido in ("ID-SECRETO", "IP-ESCONDIDA", "192.0.2.7", "198.51.100.9", "rebote-escondido"):
            self.assertNotIn(escondido, md)

    def test_codificacions_rfc2047_e_quoted_printable_en_latin1(self):
        crú = (
            "Subject: =?iso-8859-1?q?Notificaci=F3n_de_sentencia?=\n"
            "From: =?iso-8859-1?q?Mar=EDa_Iba=F1ez?= <maria@example.org>\n"
            "To: xulgado@example.org\n"
            "Date: Fri, 30 Oct 2026 09:00:00 +0100\n"
            "MIME-Version: 1.0\n"
            "Content-Type: text/plain; charset=iso-8859-1\n"
            "Content-Transfer-Encoding: quoted-printable\n\n"
            "Adjunto la resoluci=F3n de la Audiencia.\n"
        ).encode("ascii")
        md = self.md(crú)
        self.assertIn("# Notificación de sentencia", md)
        self.assertIn("- De: María Ibañez <maria@example.org>", md)
        self.assertIn("Adjunto la resolución de la Audiencia.", md)

    def test_prefire_o_texto_plano_cando_hai_alternativa_html(self):
        md = self.md(_correo(corpo="Texto plano do corpo.", html="<p>VERSION-HTML</p>"))
        self.assertIn("Texto plano do corpo.", md)
        self.assertNotIn("VERSION-HTML", md)

    def test_so_html_pasa_polo_lector_de_paxinas(self):
        html = ("<html><head><title>TITULO-HTML</title><script>var x='SCRIPT-HTML'</script></head><body>"
                "<h2>Prazos</h2><p>Ver o <a href=\"https://www.boe.es/x\">texto oficial</a>.</p>"
                "<!-- COMENTARIO-HTML --><div style=\"display:none\">AGOCHADO-HTML</div></body></html>")
        md = self.md(_correo(corpo=None, html=html))
        self.assertIn("## Prazos", md)
        self.assertIn("[texto oficial](https://www.boe.es/x)", md)
        for escondido in ("TITULO-HTML", "SCRIPT-HTML", "COMENTARIO-HTML", "AGOCHADO-HTML"):
            self.assertNotIn(escondido, md)

    def test_html_maquetado_con_taboas_conserva_os_titulos(self):
        html = "<table><tr><td><h1>Novidades</h1><p>Real Decreto 1/2026</p></td></tr></table>"
        self.assertIn("# Novidades\n\nReal Decreto 1/2026", self.md(_correo(corpo=None, html=html)))

    def test_anexos_listados_sen_o_seu_contido_e_con_aviso(self):
        mensaxe = _correo()
        mensaxe.add_attachment(b"%PDF-1.4 CONTIDO-PDF" * 100, maintype="application", subtype="pdf",
                               filename="demanda.pdf")
        mensaxe.add_attachment("CONTIDO-TXT-ANEXO", filename="notas.txt")
        ruta = self.gardar(mensaxe)
        conversion = correos.convertir(ruta)
        md = conversion.markdown
        self.assertIn("Anexos:", md)
        self.assertIn("- demanda.pdf (2 KB)", md)
        self.assertIn("- notas.txt", md)
        self.assertNotIn("CONTIDO-PDF", md)
        self.assertNotIn("CONTIDO-TXT-ANEXO", md)
        self.assertEqual(len(conversion.avisos), 1)
        self.assertIn("2", conversion.avisos[0])

    def test_imaxes_incrustadas_omitidas_con_aviso(self):
        mensaxe = _correo(corpo=None, html='<p>Asinado</p><img src="cid:sinatura" alt="">')
        mensaxe.get_body(("html",)).add_related(b"\x89PNG FALSA", maintype="image", subtype="png",
                                                cid="<sinatura>")
        conversion = correos.convertir(self.gardar(mensaxe))
        self.assertIn("Asinado", conversion.markdown)
        self.assertNotIn("Anexos:", conversion.markdown)
        self.assertNotIn("PNG FALSA", conversion.markdown)
        self.assertEqual(len(conversion.avisos), 1)
        self.assertIn("imaxe", conversion.avisos[0])

    def test_mensaxe_reenviada_coma_anexo_lista_o_seu_asunto(self):
        mensaxe = _correo()
        reenviada = _correo(corpo="CORPO-REENVIADO", asunto="Escrito anterior")
        mensaxe.add_attachment(reenviada)
        md = self.md(mensaxe)
        self.assertIn("- Escrito anterior", md)
        self.assertNotIn("CORPO-REENVIADO", md)

    def test_escapado_markdown_e_citas(self):
        corpo = "# Non é título\n---\n> Citado\n>> Citado dúas veces: # tampouco título\n<b>non HTML</b>"
        md = self.md(_correo(corpo=corpo))
        self.assertIn("\\# Non é título", md)
        self.assertIn("\\---", md)
        self.assertIn("> Citado", md)
        self.assertIn("> > Citado dúas veces: # tampouco título", md)
        self.assertIn("\\<b>non HTML</b>", md)

    def test_sen_asunto_nin_cabeceiras(self):
        md = self.md(b"\n\nSo corpo.\n")
        self.assertEqual(md, "So corpo.\n")

    def test_cco_e_responder_a_entran_se_estan(self):
        md = self.md(_correo(Bcc="Oculta <oculta@example.org>", Reply_To="xestion@example.org"))
        self.assertIn("- Cco: Oculta <oculta@example.org>", md)
        self.assertIn("- Responder a: xestion@example.org", md)

    def test_enganchado_en_formatos_e_so_sen_anonimizar(self):
        self.assertIs(formatos.LECTORES[".eml"], correos)
        self.assertIn(".eml", formatos.EXTENSIONS_SO_SEN_ANONIMIZAR)


if __name__ == "__main__":
    unittest.main()
