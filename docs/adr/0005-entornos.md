# 5. Tres entornos que se ejecutan, no que se configuran

**Estado:** aceptada (PRD #4, D7).

`local`, `demo` y `produccion`. Lo que un entorno no permite **no se registra como ruta** (el simulador no existe en producción; `/tick` exige secreto fuera de local; `reset`, `seed` e `importar` se niegan según el entorno) y el reloj de demostración se ignora en producción. Fuera de `local` la aplicación se niega a arrancar con la clave por defecto, sin https, sin TLS hacia la base o con un rol privilegiado.
