"""Límite por clave (IP) en una ventana de tiempo, en memoria. Suficiente para frenar el abuso de un formulario público."""
import threading
import time
from collections import defaultdict


class LimiteVentana:
    def __init__(self, maximo: int, segundos: int, reloj=time.monotonic):
        self.maximo, self.segundos, self.reloj = maximo, segundos, reloj
        self._golpes: dict[str, list[float]] = defaultdict(list)
        self._cerrojo = threading.Lock()

    def _vigentes(self, clave: str) -> list[float]:
        corte = self.reloj() - self.segundos
        self._golpes[clave] = [t for t in self._golpes[clave] if t > corte]
        if not self._golpes[clave]:
            del self._golpes[clave]
            return []
        return self._golpes[clave]

    def disponible(self, clave: str) -> bool:
        with self._cerrojo:
            return len(self._vigentes(clave)) < self.maximo

    def registrar(self, clave: str) -> None:
        with self._cerrojo:
            self._vigentes(clave)
            self._golpes[clave].append(self.reloj())

    def reiniciar(self) -> None:
        with self._cerrojo:
            self._golpes.clear()
