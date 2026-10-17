"""Documentación dentro del dashboard — ¿cómo funciona todo esto?

Renderiza la documentación explicada fácil (ELI5) del repositorio para que
el dashboard sea autocontenido: quien entre por la app no tiene que saber
navegar el repo para entender qué mira ni cuánto confiarle.

  - docs/05-eli5.md  → el sistema en cinco ideas (español, estilo fukura)
  - README.en.md     → guía en inglés llano (B2), auditada con Étincel

La fuente de verdad sigue siendo el repositorio: esta página solo proyecta
los ficheros tal cual (mismo patrón que la bóveda: proyección read-only).
Página de Streamlit (se auto-registra en el sidebar junto a la app principal).
"""
from __future__ import annotations

import os

import streamlit as st

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="Documentación", page_icon="📖", layout="wide")

DOCS = [
    ("El analizador explicado fácil (ES)",
     os.path.join(RAIZ, "docs", "05-eli5.md"),
     "Cinco ideas con metáfora y el porqué de cada decisión — estilo fukura."),
    ("English guide (B2)",
     os.path.join(RAIZ, "README.en.md"),
     "Plain English, ELI5 section, audited with Étincel (linter de prosa)."),
]

st.title("📖 Documentación")
st.caption("Proyección read-only de los documentos del repositorio: si algo está "
           "mal, se corrige el fichero fuente y esta página lo refleja sola.")

pestañas = st.tabs([titulo for titulo, _, _ in DOCS])
for pestaña, (titulo, ruta, descripcion) in zip(pestañas, DOCS):
    with pestaña:
        st.caption("%s · fuente: `%s`" % (descripcion, os.path.relpath(ruta, RAIZ)))
        try:
            with open(ruta, encoding="utf-8") as f:
                st.markdown(f.read())
        except OSError:
            st.warning("No encuentro %s — ¿repo incompleto? (regla 101: no se "
                       "inventa el contenido)" % ruta)
