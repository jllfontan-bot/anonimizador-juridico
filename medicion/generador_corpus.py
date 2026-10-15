#!/usr/bin/env python3
"""Xera `corpus_generado.json`: moitas variantes por categoría, con verdade
calculada programaticamente (nunca tecleada a man) -- así o corpus pode medrar
a centos de casos sen perder fiabilidade na verdade de cada un.

Por que non 1000 casos calquera: nun recoñecedor por REGEX (DNI, IBAN...) o
resultado é determinista -- probalo 40 veces con díxitos distintos adoita dar
sempre o mesmo veredicto, e diminúe rápido o que se aprende. Onde si paga a
pena ter moito volume é nas categorías que dependen do modelo ESTATÍSTICO de
spaCy (nomes en contextos raros, categoría especial): aí a mesma persoa nunha
frase distinta pode dar resultados distintos. Por iso as contas por
categoría, abaixo, non son iguais.

Semente FIXA (reproducibilidade -- restrición 7 do plan: se o corpus cambia
sen control en cada execución, non se pode comparar unha sesión de medición
coa seguinte).

Uso:
    .venv/bin/python medicion/generador_corpus.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from anonimizador import ocr_dni

random.seed(2026)

NOMES = [
    "Xiana", "Manuel", "Ramón", "Leandro", "Covadonga", "Uxía", "Breixo", "Noa",
    "Antón", "Sabela", "Iago", "Mariña", "Xoel", "Carme", "Brais", "Olalla",
    "Roi", "Ledicia", "Xacobe", "Aldara",
]
APELIDOS = [
    "Ferrándiz Salcedo", "Fiolleda Outeiral", "Falcón Bande", "del Valle Resua",
    "Freire Lameiro", "Veiga Lucas", "Otero Campos", "Barroso Cordeiro",
    "Pazos Iglesias", "Seoane Cortizo", "Domínguez Rial", "Rivas Bahamonde",
    "Meixide Castro", "Suárez Pena", "Carballo Doval",
]


def nome_completo() -> str:
    return f"{random.choice(NOMES)} {random.choice(APELIDOS)}"


def xerar_dni() -> str:
    digitos = f"{random.randint(0, 99999999):08d}"
    return f"{digitos}{ocr_dni.letra_control(digitos)}"


def xerar_nie() -> str:
    pref = random.choice("XYZ")
    digitos7 = f"{random.randint(0, 9999999):07d}"
    digitos8 = ocr_dni._LETRA_INICIAL_NIE[pref] + digitos7
    return f"{pref}{digitos7}{ocr_dni.letra_control(digitos8)}"


def xerar_pasaporte() -> str:
    letras = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ", k=random.choice([2, 3])))
    digitos = "".join(random.choices("0123456789", k=random.choice([6, 7])))
    return f"{letras}{digitos}"


def xerar_telefono_3_3_3() -> str:
    return (
        random.choice("6789") + "".join(random.choices("0123456789", k=2)) + " "
        + "".join(random.choices("0123456789", k=3)) + " "
        + "".join(random.choices("0123456789", k=3))
    )


def xerar_telefono_3_2_2_2() -> str:
    return (
        random.choice("6789") + "".join(random.choices("0123456789", k=2)) + " "
        + "".join(random.choices("0123456789", k=2)) + " "
        + "".join(random.choices("0123456789", k=2)) + " "
        + "".join(random.choices("0123456789", k=2))
    )


def xerar_email() -> str:
    dominio = random.choice(["dominio-ficticio.gal", "correo-exemplo.es", "proba-anon.org"])
    return f"{random.choice(NOMES).lower()}.{random.choice(APELIDOS).split()[0].lower()}@{dominio}"


def xerar_enderezo() -> str:
    tipo = random.choice(["Rúa", "Calle", "Avenida", "Praza", "Camiño"])
    nome_rua = random.choice([
        "das Fontiñas", "do Castiñeiro", "Nova de Abaixo", "da Estrela", "do Home Santo",
        "das Hedras", "do Pombal", "de la Rosa", "del Progreso", "das Airas",
    ])
    numero = random.randint(1, 250)
    return f"{tipo} {nome_rua} {numero}"


def xerar_iban() -> str:
    grupos = [f"{random.randint(0, 9999):04d}" for _ in range(5)]
    return "ES" + f"{random.randint(0, 99):02d}" + " " + " ".join(grupos)


def xerar_colexiado() -> str:
    return str(random.randint(100, 99999))


def xerar_seguridade_social() -> str:
    provincia = f"{random.randint(1, 52):02d}"
    numero = f"{random.randint(0, 99999999):08d}"
    digitos_control = f"{random.randint(0, 99):02d}"
    return f"{provincia}/{numero}/{digitos_control}"


def xerar_matricula() -> str:
    numero = f"{random.randint(0, 9999):04d}"
    letras = "".join(random.choices("BCDFGHJKLMNPRSTVWXYZ", k=3))
    return f"{numero}{letras}"


def caso(id_, categoria, texto, debe_desaparecer=(), debe_permanecer=(), nota=""):
    return {
        "id": id_,
        "categoria": categoria,
        "texto": texto,
        "debe_desaparecer": list(debe_desaparecer),
        "debe_permanecer": list(debe_permanecer),
        "nota": nota,
    }


def xerar_identificadores_directos() -> list[dict]:
    casos = []

    for i in range(15):
        dni = xerar_dni()
        plantilla = random.choice([
            "El compareciente exhibe su DNI {v} para acreditar su identidad.",
            "Consta en el expediente el DNI {v} de la parte demandante.",
            "Identificado mediante DNI número {v} ante el letrado actuante.",
        ])
        casos.append(caso(f"gen_dni_{i}", "identificador_directo", plantilla.format(v=dni), [dni]))

    for i in range(10):
        nie = xerar_nie()
        plantilla = random.choice([
            "Presenta NIE {v} como documento de identidad válido en España.",
            "Consta NIE {v} en la solicitud de residencia.",
        ])
        casos.append(caso(f"gen_nie_{i}", "identificador_directo", plantilla.format(v=nie), [nie]))

    for i in range(10):
        pas = xerar_pasaporte()
        plantilla = random.choice([
            "Comparece con pasaporte número {v} al no disponer de DNI español.",
            "Se identifica mediante pasaporte {v} expedido en su país de origen.",
        ])
        casos.append(caso(f"gen_pasaporte_{i}", "identificador_directo", plantilla.format(v=pas), [pas]))

    for i in range(5):
        pas = xerar_pasaporte()
        texto = f"El código de referencia {pas} aparece en la tabla de expedientes internos."
        casos.append(caso(f"gen_pasaporte_sen_etiqueta_{i}", "control_negativo", texto, [], [pas],
                           "Sen a etiqueta 'pasaporte' preto non debe tocarse."))

    for i in range(8):
        tel = xerar_telefono_3_3_3()
        casos.append(caso(f"gen_tel333_{i}", "identificador_directo",
                           f"Puede contactar en el teléfono {tel} en horario de mañana.", [tel]))

    for i in range(8):
        tel = xerar_telefono_3_2_2_2()
        casos.append(caso(f"gen_tel3222_{i}", "identificador_directo",
                           f"Número de contacto facilitado: {tel}, disponible por las tardes.", [tel]))

    for i in range(10):
        email = xerar_email()
        casos.append(caso(f"gen_email_{i}", "identificador_directo",
                           f"Remite la documentación al correo {email} antes del viernes.", [email]))

    for i in range(10):
        end = xerar_enderezo()
        casos.append(caso(f"gen_enderezo_{i}", "identificador_directo",
                           f"Reside en la {end}, según consta en el padrón municipal.", [end]))

    for i in range(5):
        casos.append(caso(f"gen_enderezo_sen_numero_{i}", "control_negativo",
                           f"La sentencia menciona la Rúa Nova a modo de ejemplo de vía urbana.",
                           [], ["Rúa Nova a modo de ejemplo"],
                           "Sen número/s/n non hai enderezo completo -- control negativo."))

    for i in range(8):
        iban = xerar_iban()
        casos.append(caso(f"gen_iban_{i}", "identificador_directo",
                           f"El reintegro se realizará en la cuenta {iban} indicada por el interesado.", [iban]))

    for i in range(8):
        col = xerar_colexiado()
        casos.append(caso(f"gen_colexiado_{i}", "identificador_directo",
                           f"Informe suscrito por el letrado, colegiado número {col} del ICA correspondiente.",
                           [col], ["colegiado número"]))

    for i in range(8):
        ss = xerar_seguridade_social()
        casos.append(caso(f"gen_ss_{i}", "identificador_directo",
                           f"Consta número de afiliación a la Seguridad Social {ss} en el expediente laboral.",
                           [ss]))

    for i in range(5):
        ss = xerar_seguridade_social()
        casos.append(caso(f"gen_ss_sen_etiqueta_{i}", "control_negativo",
                           f"El expediente administrativo {ss} sigue pendiente de resolución.",
                           [], [ss], "Sen etiqueta preto pode ser un expediente calquera."))

    for i in range(8):
        mat = xerar_matricula()
        casos.append(caso(f"gen_matricula_{i}", "identificador_directo",
                           f"El vehículo con matrícula {mat} quedó estacionado en la vía pública.", [mat]))

    return casos


def xerar_nomes() -> list[dict]:
    plantillas = [
        "{nome} presentó el escrito de alegaciones en tiempo y forma.",
        "Firma el presente documento {nome}, en calidad de interesado.",
        "Interpone recurso de reposición {nome} contra la resolución dictada.",
        "Otorga poder de representación {nome} a favor de su letrado.",
    ]
    return [
        caso(f"gen_nome_{i}", "nome", plantilla.format(nome=(nome := nome_completo())), [nome])
        for i, plantilla in enumerate(plantillas * 10)
    ]


def xerar_nomes_dificiles() -> list[dict]:
    casos = []
    for i in range(15):
        nome = nome_completo()
        primeiro, resto = nome.split(" ", 1)
        invertido = f"{resto}, {primeiro}"
        texto = f"Listaxe de persoal: {invertido} - Turno de mañá."
        casos.append(caso(f"gen_invertido_{i}", "nome_formato_dificil", texto, [invertido],
                           ["Listaxe de persoal", "Turno de mañá"],
                           "Formato BOE, ver risco_residual.py."))

    profesions = ["arquitecto", "aparejador", "ingeniero técnico", "perito tasador"]
    for i in range(15):
        nome = nome_completo()
        prof = random.choice(profesions)
        texto = f"Firma el informe {nome} {prof} colegiado en la demarcación correspondiente."
        casos.append(caso(f"gen_sen_coma_{i}", "nome_formato_dificil", texto, [nome],
                           ["Firma el informe", "colegiado en la demarcación"]))

    roles = ["testigo", "denunciante", "acusado", "demandante"]
    for i in range(20):
        nome = nome_completo()
        rol = random.choice(roles)
        articulo = random.choice(["el", "la"])
        texto = f"En el acto del juicio declara {articulo} {rol} {nome}, quien manifiesta no haber presenciado los hechos."
        casos.append(caso(f"gen_contexto_rol_{i}", "nome_formato_dificil", texto, [nome],
                           [f"declara {articulo} {rol}", "no haber presenciado"]))

    return casos


def xerar_categoria_especial() -> list[dict]:
    casos = []
    saude = ["VIH", "esclerosis múltiple", "un trastorno bipolar", "cáncer de mama", "diabetes tipo 1"]
    relixions = ["musulmana", "evangélica", "budista", "testigo de Jehová", "judía"]
    orientacions = ["homosexual", "bisexual", "transexual"]
    sindicatos = ["CIG", "CCOO", "UGT", "CSIF", "USO"]

    for i in range(10):
        nome = nome_completo()
        texto = f"{nome} presenta un informe médico donde consta que padece {random.choice(saude)} desde hace años."
        casos.append(caso(f"gen_saude_{i}", "categoria_especial", texto, [nome], [],
                           "A v1 non marca isto coma categoría especial -- métrica informativa."))

    for i in range(10):
        nome = nome_completo()
        texto = f"{nome} declaró que profesa la religión {random.choice(relixions)} y acude a su lugar de culto cada semana."
        casos.append(caso(f"gen_relixion_{i}", "categoria_especial", texto, [nome], []))

    for i in range(10):
        nome = nome_completo()
        texto = f"{nome} manifestó que su despido se debió a conocerse su orientación {random.choice(orientacions)} en la empresa."
        casos.append(caso(f"gen_orientacion_{i}", "categoria_especial", texto, [nome], []))

    for i in range(10):
        nome = nome_completo()
        texto = f"Consta que {nome} es afiliado del sindicato {random.choice(sindicatos)} desde hace varios años."
        casos.append(caso(f"gen_sindical_{i}", "categoria_especial", texto, [nome], []))

    return casos


def xerar_papel_persoa() -> list[dict]:
    roles = [
        ("perito judicial", "para ratificar su informe"),
        ("testigo", "quien nada aportó de relevancia"),
        ("letrado de la parte contraria", "en el turno de intervenciones"),
        ("fiscal", "en representación del Ministerio Público"),
    ]
    casos = []
    for i in range(20):
        nome = nome_completo()
        rol, cola = random.choice(roles)
        tratamento = random.choice(["don", "doña"])
        texto = f"Comparece como {rol} {tratamento} {nome}, {cola}."
        casos.append(caso(f"gen_papel_{i}", "papel_persoa", texto, [nome], [rol],
                           "O papel non se marca hoxe coma tal -- métrica informativa."))
    return casos


def xerar_control_negativo_palabras_comuns() -> list[dict]:
    """Palabras comúns capitalizadas illadas (nunca nomes) que un heurístico
    de "apelido solto" podería confundir cun nome real -- ver o achado do
    27/09/2026 (spaCy etiquetando "Turno" coma PER)."""
    palabras = [
        "Turno", "Despois", "Ademais", "Considerando", "Antecedentes",
        "Resultando", "Visto", "Igualmente", "Finalmente", "Asimismo",
    ]
    casos = []
    for i, palabra in enumerate(palabras):
        texto = f"{palabra}, se procede a dar por finalizado el acto sin más incidencias que reseñar."
        casos.append(caso(f"gen_palabra_comun_{i}", "control_negativo", texto, [], [palabra],
                           "Palabra común de inicio de frase -- non é un apelido, control negativo."))
    return casos


def xerar_ocr_ruido() -> list[dict]:
    casos = []
    for i in range(10):
        dni = xerar_dni()
        # Simula ruído de OCR lixeiro arredor (0 por O), nunca DENTRO do propio DNI.
        texto = f"D0cumento de identidad n.0 {dni} presentado xunto coa s0licitude (dixitalizado por OCR)."
        casos.append(caso(f"gen_ocr_{i}", "ocr_ruido", texto, [dni], ["s0licitude"]))
    return casos


def main() -> None:
    casos = (
        xerar_identificadores_directos()
        + xerar_nomes()
        + xerar_nomes_dificiles()
        + xerar_categoria_especial()
        + xerar_papel_persoa()
        + xerar_control_negativo_palabras_comuns()
        + xerar_ocr_ruido()
    )
    destino = Path(__file__).parent / "corpus_generado.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(casos, f, ensure_ascii=False, indent=2)
    print(f"Xerados {len(casos)} casos en {destino}")

    por_categoria: dict[str, int] = {}
    for c in casos:
        por_categoria[c["categoria"]] = por_categoria.get(c["categoria"], 0) + 1
    for cat, n in sorted(por_categoria.items()):
        print(f"  {cat}: {n}")


if __name__ == "__main__":
    main()
