"""`ner._detectar` calcula `doc.text` e `doc.ents` unha vez por doc (16/11/2026,
rendemento: spaCy reconstrúeos enteiros en cada acceso e chamábanse por cada
entidade, cuadrático; 84,6 s de tempo propio nun PDF real de 351 páxinas).
Este test garda as versións ANTERIORES de `_estender_entidade_persoa` e
`_estender_cara_atras` e comproba con textos inventados que dan o mesmo,
entidade a entidade e no resultado enteiro de `ner.detectar`."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import random
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import ner
from anonimizador.ner import (_CARGOS_EXENTOS_RE, _CONTINUACION_NOME_PERSOA, _MAX_PALABRAS_CARA_ATRAS, _NOMES_PIA,
                              _PALABRA_ANTERIOR_RE, _PALABRAS_FUNCIONAIS, _PALABRAS_NON_NOME, _POS_NON_NOME)


def _estender_entidade_persoa_ref(ent, texto_doc=None):
    doc = ent.doc
    match = _CONTINUACION_NOME_PERSOA.match(doc.text, ent.end_char)
    if not match:
        return ent
    span = doc.char_span(ent.start_char, match.end(), alignment_mode="expand")
    return span if span is not None else ent


def _estender_cara_atras_ref(doc, inicio, texto_ignorado=None, ents_ignoradas=None):
    texto = doc.text
    for _ in range(_MAX_PALABRAS_CARA_ATRAS):
        m = _PALABRA_ANTERIOR_RE.search(texto, max(0, inicio - 80), inicio)
        if m is None:
            break
        palabra = m.group(1)
        baixa = palabra.lower()
        if baixa in _PALABRAS_FUNCIONAIS or baixa in _PALABRAS_NON_NOME:
            break
        if re.fullmatch(_CARGOS_EXENTOS_RE, palabra, re.IGNORECASE):
            break
        w_inicio = m.start(1)
        span = doc.char_span(w_inicio, m.end(1), alignment_mode="expand")
        if span is None or any(t.pos_ in _POS_NON_NOME for t in span):
            break
        anterior = texto[:w_inicio].rstrip(" \t")
        inicio_frase = anterior == "" or anterior[-1] in ".!?:;\n"
        noutra_entidade = any(
            e.start_char <= w_inicio < e.end_char and e.label_ != "PER" for e in doc.ents
        )
        if (inicio_frase or noutra_entidade) and baixa not in _NOMES_PIA:
            break
        inicio = w_inicio
        if inicio_frase:
            break
    return inicio


_NOMES = ["Xoán Pérez Vázquez", "Xosé Manuel Carballo Portela", "Antía Varela Doval", "María Lozano Duarte",
          "Leandro del Valle Resua", "Brais Castro Lema", "Uxía Rial Souto", "D. Iago Novoa Barral"]
_PEZAS = ["Comparece", "don", "dona", "a testemuña", "o letrado", "Vigo", "Lugo", "ante o xulgado.", "Asina:",
          "\n", "\t", "  ", ". ", "; ", "Sr.", "Sra.", "en representación de", "veciño de Ourense", "e",
          "AVOGADA", "Firma la LAJ a", "SEGUNDO.-", "Presidente da Xunta"]


def _texto(r: random.Random, pezas: int) -> str:
    return " ".join(r.choice(_NOMES) if r.random() < 0.35 else r.choice(_PEZAS) for _ in range(pezas))


class TestTextoDoDocEquivalente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = ner.cargar_modelo()
        r = random.Random(20261116)
        cls.textos = [_texto(r, r.randrange(20, 160)) for _ in range(60)]
        cls.textos.append("Xosé\tManuel Carballo Portela comparece.\nAntía Varela Doval, veciña de Lugo, asina.")

    def test_entidade_a_entidade(self):
        comparadas = 0
        for texto in self.textos:
            doc = self.nlp(texto)
            texto_doc, ents = doc.text, doc.ents
            for ent in ents:
                if ent.label_ != "PER":
                    continue
                vello, novo = _estender_entidade_persoa_ref(ent), ner._estender_entidade_persoa(ent, texto_doc)
                self.assertEqual((vello.start_char, vello.end_char), (novo.start_char, novo.end_char), texto)
                for inicio in {ent.start_char, novo.start_char, *[t.idx for t in ent]}:
                    self.assertEqual(_estender_cara_atras_ref(doc, inicio),
                                     ner._estender_cara_atras(doc, inicio, texto_doc, ents), texto)
                    self.assertEqual(ner._estender_cara_atras(doc, inicio), ner._estender_cara_atras(doc, inicio, texto_doc, ents))
                comparadas += 1
        self.assertGreater(comparadas, 100)

    def test_detectar_igual_ca_coas_funcions_anteriores(self):
        for texto in self.textos[:25]:
            novo = [(e.inicio, e.fin, e.texto, e.etiqueta) for e in ner.detectar(texto)[0]]
            with mock.patch.object(ner, "_estender_entidade_persoa", _estender_entidade_persoa_ref), \
                    mock.patch.object(ner, "_estender_cara_atras", _estender_cara_atras_ref):
                vello = [(e.inicio, e.fin, e.texto, e.etiqueta) for e in ner.detectar(texto)[0]]
            self.assertEqual(novo, vello, texto)


if __name__ == "__main__":
    unittest.main()
