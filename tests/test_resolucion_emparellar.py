"""`resolution._emparellar` comproba a distancia ANTES de buscar un "ANEXO"
entre a persoa e o DNI (15/11/2026, rendemento: a busca sobre o texto entre
cada persoa e cada DNI do documento enteiro era cúbica). Este test garda a
versión ANTERIOR coma referencia e comproba, en moitos casos aleatorios con
datos inventados e nos bordos, que o resultado é exactamente o mesmo (os
mesmos pares, na mesma orde): no orixinal o par só se engadía se distancia
<= _DISTANCIA_DNI E sen anexo entre ambos, e a busca non ten efectos."""
import os

os.environ.setdefault("ANONIMIZADOR_IDIOMA", "gl")

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from anonimizador import resolution
from anonimizador.recognizers import Entidade
from anonimizador.resolution import (_ANEXO_ENTRE_RE, _DISTANCIA_DNI, _DNI_DA_PERSOA_ANTERIOR_RE,
                                     _FRONTEIRA_FRASE_RE, _PENALIZACION_FRONTEIRA)


def _emparellar_referencia(persoas: list, dnis: list, texto: str) -> list:
    """Copia literal da versión anterior (06b5bc1), sen o aviso de progreso."""
    pares = []
    for m in persoas:
        for d in dnis:
            distancia = min(abs(d.inicio - m.fin), abs(m.inicio - d.fin))
            if _ANEXO_ENTRE_RE.search(texto, min(m.fin, d.fin), max(m.inicio, d.inicio)):
                continue
            if distancia <= _DISTANCIA_DNI:
                orde = distancia
                if m.inicio >= d.fin and _FRONTEIRA_FRASE_RE.search(texto, d.fin, m.inicio):
                    orde += _PENALIZACION_FRONTEIRA
                if m.fin <= d.inicio and _DNI_DA_PERSOA_ANTERIOR_RE.fullmatch(texto, m.fin, d.inicio):
                    orde = -1
                pares.append((orde, m, d))
    pares.sort(key=lambda p: p[0])

    mencions_asignadas, dnis_asignados = set(), set()
    resultado = []
    for _, m, d in pares:
        if id(m) in mencions_asignadas or id(d) in dnis_asignados:
            continue
        resultado.append((m, d))
        mencions_asignadas.add(id(m))
        dnis_asignados.add(id(d))
    return resultado


_NOMES = ["Xoán Pérez Vázquez", "Antía Varela Doval", "Brais Castro Lema", "Uxía Rial Souto"]
_DNIS = ["30014811Z", "12345678Z", "87654321X", "11111111H"]
_RECHEO = ["comparece", "e", "declarou", "ante o xulgado.", ". Despois", "\n", "\nANEXO\n", "\nAnexo II\n",
           ", con DNI", "provisto del DNI", "titular del NIF", "respectivamente", "no expediente", "  "]


def _caso(r: random.Random, pezas: int) -> tuple:
    """Texto inventado e as súas entidades (persoas e DNI) con posicións exactas."""
    texto, persoas, dnis = "", [], []
    for _ in range(pezas):
        tipo = r.random()
        if tipo < 0.3:
            nome = r.choice(_NOMES)
            persoas.append(Entidade(len(texto), len(texto) + len(nome), nome, "PERSOA"))
            texto += nome
        elif tipo < 0.55:
            dni = r.choice(_DNIS)
            dnis.append(Entidade(len(texto), len(texto) + len(dni), dni, "DNI_NIE"))
            texto += dni
        else:
            texto += r.choice(_RECHEO)
        texto += r.choice([" ", " ", "", "\n", " " * r.randrange(1, 140)])  # ás veces, máis lonxe ca a xanela
    return texto, persoas, dnis


def _ids(pares: list) -> list:
    return [(id(m), id(d)) for m, d in pares]


class TestEmparellarEquivalente(unittest.TestCase):
    def _comparar(self, texto, persoas, dnis):
        self.assertEqual(_ids(resolution._emparellar(persoas, dnis, texto)),
                         _ids(_emparellar_referencia(persoas, dnis, texto)), repr(texto[:200]))

    def test_casos_aleatorios(self):
        r = random.Random(20261115)
        for _ in range(3000):
            self._comparar(*_caso(r, r.randrange(1, 40)))

    def test_distancia_exactamente_120_e_121(self):
        for oco in (_DISTANCIA_DNI - 1, _DISTANCIA_DNI, _DISTANCIA_DNI + 1, _DISTANCIA_DNI + 2):
            for orde in ("persoa_primeiro", "dni_primeiro"):
                with self.subTest(oco=oco, orde=orde):
                    nome, dni = _NOMES[0], _DNIS[0]
                    if orde == "persoa_primeiro":
                        texto = nome + " " * oco + dni
                        m = Entidade(0, len(nome), nome, "PERSOA")
                        d = Entidade(len(nome) + oco, len(texto), dni, "DNI_NIE")
                    else:
                        texto = dni + " " * oco + nome
                        d = Entidade(0, len(dni), dni, "DNI_NIE")
                        m = Entidade(len(dni) + oco, len(texto), nome, "PERSOA")
                    self._comparar(texto, [m], [d])
                    self.assertEqual(len(resolution._emparellar([m], [d], texto)), 1 if oco <= _DISTANCIA_DNI else 0)

    def test_anexo_entre_ambos(self):
        texto = f"{_NOMES[0]}\nANEXO\n{_DNIS[0]}"
        m = Entidade(0, len(_NOMES[0]), _NOMES[0], "PERSOA")
        d = Entidade(texto.index(_DNIS[0]), len(texto), _DNIS[0], "DNI_NIE")
        self._comparar(texto, [m], [d])
        self.assertEqual(resolution._emparellar([m], [d], texto), [])

    def test_solapados_repetidos_e_varios(self):
        nome, dni = _NOMES[1], _DNIS[1]
        texto = f"{nome}, con DNI {dni}, e {nome}, con DNI {dni}. {nome}"
        persoas = [Entidade(i, i + len(nome), nome, "PERSOA") for i in
                   [j for j in range(len(texto)) if texto.startswith(nome, j)]]
        dnis = [Entidade(i, i + len(dni), dni, "DNI_NIE") for i in
                [j for j in range(len(texto)) if texto.startswith(dni, j)]]
        # Un DNI solapado coa persoa (posicións que se cruzan) tamén ten que dar o mesmo.
        dnis.append(Entidade(persoas[0].inicio + 2, persoas[0].inicio + 11, dni, "DNI_NIE"))
        self._comparar(texto, persoas, dnis)
        self._comparar(texto, persoas, [])
        self._comparar(texto, [], dnis)


if __name__ == "__main__":
    unittest.main()
