"""Trabajador: llama al ciclo de tareas cada pocos segundos."""
import time

from . import tasks


def main(interval: float = 3.0) -> None:
    print("Trabajador activo: ciclo cada", interval, "s")
    while True:
        try:
            tasks.cycle()
        except Exception as e:  # el trabajador no se cae: la falla queda visible en el panel
            print("Error en el ciclo:", e)
        time.sleep(interval)


if __name__ == "__main__":
    main()
