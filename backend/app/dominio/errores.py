"""Errores del dominio. La API los traduce a HTTP en un solo lugar."""


class ErrorDominio(Exception):
    codigo = "error"

    def __init__(self, detalle: str):
        super().__init__(detalle)
        self.detalle = detalle


class NoEncontrado(ErrorDominio):
    codigo = "no_encontrado"


class Conflicto(ErrorDominio):
    codigo = "conflicto"


class EntradaInvalida(ErrorDominio):
    codigo = "entrada_invalida"


class NoAutenticado(ErrorDominio):
    """Falta el access token, venció o no es de nuestro user pool."""
    codigo = "no_autenticado"


class SinPermiso(ErrorDominio):
    """El token es válido pero la cuenta no tiene el rol de esta acción (un publicador que
    consulta un estudio, una institución que publica un modelo)."""
    codigo = "sin_permiso"


class ServicioNoDisponible(ErrorDominio):
    """Fallo transitorio de un servicio externo (worker sin respuesta). Se reintenta."""
    codigo = "servicio_no_disponible"


class FalloDefinitivo(ErrorDominio):
    """El worker rechazó el pedido (imagen ilegible, contrato inaplicable). No se reintenta."""
    codigo = "fallo_definitivo"
