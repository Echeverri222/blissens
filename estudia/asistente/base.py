"""Piezas del catálogo: la herramienta, su registro y el error que el modelo puede leer."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

LECTURA = "lectura"
PROPUESTA = "propuesta"


class Entrada(BaseModel):
    """Base de las entradas: ningún campo de más (un `negocio_id` inventado por el modelo es un dato inválido)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorHerramienta(Exception):
    """Un fallo que el modelo puede leer. Códigos estables: `sin_permiso`, `no_existe`, `datos_invalidos`,
    `espacio_ocupado` y `accion_no_permitida`."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo, self.mensaje = codigo, mensaje


@dataclass(frozen=True)
class Herramienta:
    """Una operación con nombre y tipos en el catálogo. Su manejador es `(conn, actor, args) -> dict`."""
    nombre: str
    descripcion: str
    modelo: type[BaseModel]
    perfiles: tuple[str, ...]
    tipo: Literal["lectura", "propuesta"]
    manejador: Callable
    auditoria: str | None = None
    modelos: dict[str, type[BaseModel]] = field(default_factory=dict)  # entrada distinta para algunos perfiles

    def modelo_de(self, perfil: str) -> type[BaseModel]:
        return self.modelos.get(perfil, self.modelo)


CATALOGO: dict[str, Herramienta] = {}


def herramienta(nombre: str, descripcion: str, modelo: type[BaseModel], perfiles: tuple[str, ...], tipo: str,
                auditoria: str | None = None, modelos: dict[str, type[BaseModel]] | None = None):
    """Registra el manejador decorado como una herramienta del catálogo."""
    def registrar(fn):
        assert nombre not in CATALOGO, f"Herramienta repetida: {nombre}"
        assert tipo in (LECTURA, PROPUESTA)
        assert set(modelos or {}) <= set(perfiles), f"{nombre}: modelo para un perfil que no la usa"
        CATALOGO[nombre] = Herramienta(nombre, descripcion, modelo, tuple(perfiles), tipo, fn, auditoria, dict(modelos or {}))
        return fn
    return registrar
