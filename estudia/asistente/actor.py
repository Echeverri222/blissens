"""Actor: quién pregunta. Lo construye el servidor (sesión o enlace firmado); el modelo nunca lo elige (PRD asistente, P3)."""
from dataclasses import dataclass

PERFILES = ("paciente", "especialista", "auxiliar", "operador", "visitante")


@dataclass(frozen=True)
class Actor:
    """Un usuario con su acceso (`usuario`), o un paciente identificado por su enlace personal (`paciente_id`).

    `usuario` es el diccionario de `usuarios.usuario_de_sesion` (`id`, `rol`, `profesional_id`, `administrador`).
    El perfil `operador` es la sesión local del desarrollador: ve lo mismo que la auxiliar, solo lectura, y no tiene usuario.
    El perfil `visitante` es quien escribe desde el sitio público: no tiene usuario ni paciente, solo un id al azar (`visitante`)
    que el servidor guarda en una cookie firmada.
    """
    perfil: str
    negocio_id: int
    usuario: dict | None = None
    paciente_id: int | None = None
    visitante: str | None = None

    def __post_init__(self):
        if self.perfil not in PERFILES:
            raise ValueError(f"Perfil desconocido: {self.perfil}")
        if self.perfil == "paciente":
            if self.paciente_id is None or self.usuario is not None:
                raise ValueError("Un actor paciente lleva su paciente_id y ningún usuario")
        elif self.paciente_id is not None:
            raise ValueError("Solo el actor paciente lleva paciente_id")
        if self.perfil == "visitante":
            if not self.visitante or self.usuario is not None:
                raise ValueError("Un actor visitante lleva su id de visitante y ningún usuario")
        elif self.visitante is not None:
            raise ValueError("Solo el actor visitante lleva visitante")
        if self.perfil in ("auxiliar", "especialista") and self.usuario is None:
            raise ValueError("Un actor de la clínica lleva su usuario")

    @classmethod
    def de_usuario(cls, u: dict) -> "Actor":
        """Actor de un usuario con un negocio activo; su rol (`auxiliar` o `especialista`) es el perfil."""
        if u.get("negocio_id") is None:
            raise ValueError("El usuario no tiene un negocio activo")
        if u["rol"] not in ("auxiliar", "especialista"):
            raise ValueError(f"El rol {u['rol']!r} no tiene perfil en el asistente")
        return cls(u["rol"], u["negocio_id"], usuario=dict(u))

    @classmethod
    def de_paciente(cls, negocio_id: int, paciente_id: int) -> "Actor":
        """Actor de quien abrió su enlace personal. `paciente_id` es el de la persona del enlace."""
        return cls("paciente", negocio_id, paciente_id=paciente_id)

    @classmethod
    def de_visitante(cls, negocio_id: int, visitante: str) -> "Actor":
        """Actor de quien escribe desde el sitio público. `visitante` es el id al azar de su cookie firmada."""
        return cls("visitante", negocio_id, visitante=visitante)

    @classmethod
    def de_operador(cls, negocio_id: int) -> "Actor":
        return cls("operador", negocio_id)

    @property
    def usuario_id(self) -> int | None:
        return self.usuario["id"] if self.usuario else None

    @property
    def usuario_de_alcance(self) -> dict:
        """El usuario con el que se aplican `permisos.*`. El operador se comporta como una auxiliar."""
        if self.usuario is not None:
            return self.usuario
        if self.perfil == "operador":
            return {"id": None, "rol": "auxiliar", "profesional_id": None, "administrador": False}
        raise PermissionError("Un paciente o un visitante no tiene usuario")
