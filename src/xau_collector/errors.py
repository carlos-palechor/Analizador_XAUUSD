# Agrupa los errores controlados que la interfaz puede presentar sin traceback.
class CollectorError(Exception):
    """Error esperado que puede presentarse al usuario sin traceback."""


# Señala una configuración inválida, incompleta o insegura para ejecutar el programa.
class ConfigurationError(CollectorError):
    """La configuración es inválida o insegura."""


# Señala la ausencia de una dependencia externa requerida por una operación.
class DependencyUnavailableError(CollectorError):
    """Una dependencia externa necesaria no está disponible."""


# Señala un fallo al conectar o consultar una fuente externa como MT5.
class ConnectionFailureError(CollectorError):
    """No fue posible establecer o verificar la conexión externa."""


# Señala que no se pudo elegir un símbolo de mercado de forma inequívoca.
# Señala que no hay suficientes velas cerradas para calcular estructura confiable.
class InsufficientHistoricalDataError(CollectorError):
    """El período solicitado no contiene el contexto técnico mínimo."""


class SymbolResolutionError(CollectorError):
    """No fue posible resolver de forma inequívoca el símbolo solicitado."""
