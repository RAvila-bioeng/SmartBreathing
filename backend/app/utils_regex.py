def block_regex_safe(block: str) -> str:
    """Helper for safe regex construction from block type"""
    if not block: return "Principal"
    # Escapar caracteres especiales si fuera necesario, o simplificar
    # Para este caso, usamos palabras clave simples
    if "Calentamiento" in block: return "Calentamiento"
    if "Principal" in block or "Núcleo" in block: return "Principal|Núcleo"
    if "Vuelta" in block: return "Vuelta"
    return "Principal"
