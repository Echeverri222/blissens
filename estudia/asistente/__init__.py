"""Asistente: catálogo cerrado de herramientas, actor y despachador (docs/prd-asistente.md, docs/adr/0009).

Las puertas de entrada (el servidor MCP local y el bucle de la aplicación) usan solo esto:

    herramientas_de(perfil)      las herramientas del perfil
    definiciones_api(perfil)     esas herramientas como definiciones de la API de Claude
    ejecutar(actor, nombre, args)  la única manera de ejecutar una
"""
from .actor import Actor
from .base import CATALOGO, Herramienta
from .catalogo import definiciones_api, esquema_entrada, herramientas_de
from .conversacion import conversar
from .despachador import ejecutar

__all__ = ["Actor", "CATALOGO", "Herramienta", "definiciones_api", "conversar", "ejecutar", "esquema_entrada", "herramientas_de"]
