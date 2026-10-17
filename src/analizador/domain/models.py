"""Modelos de dominio del Analizador (reglas 5-6, 9, 13-14, 17-19, 41-42, 58-61, 75-76, 86-87).

Identificadores en inglés, vocabulario financiero de cara al usuario en español
(regla 99). Todo stdlib: dataclasses + json, sin dependencias externas.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# ── Regla 9: categorías de exposición ────────────────────────────────────────

CATEGORIAS = [
    "ETF_SECTORIAL", "ETF_TEMATICO", "ETF_REGIONAL", "ETF_GLOBAL",
    "FONDO_ACTIVO", "FONDO_INDEXADO", "SMART_BETA", "FACTOR_VALUE",
    "FACTOR_GROWTH", "FACTOR_DIVIDEND", "FACTOR_QUALITY", "FACTOR_MOMENTUM",
    "FACTOR_LOW_VOL", "EQUAL_WEIGHT", "ETF_MATERIAS_PRIMAS", "ETC", "ETN",
    "ETP", "APALANCADO", "INVERSO", "FONDO_MIXTO", "RENTA_FIJA", "REIT",
    "EXPOSICION_INDIRECTA",
]

# Regla 17: naturaleza del producto (qué posee realmente el inversor)
NATURALEZAS = [
    "ETF_ACCIONES", "ETF_BONOS", "ETF_MATERIAS_PRIMAS", "FONDO_ACTIVO",
    "FONDO_INDEXADO", "ETC_FISICO", "ETC_FUTUROS", "ETN", "SINTETICO",
    "ETF_APALANCADO", "ETF_INVERSO", "FONDO_INMOBILIARIO", "FONDO_MULTIACTIVO",
]


# ── Regla 75: etiquetas de calidad de dato ──────────────────────────────────

class DataLabel:
    VERIFICADO = "VERIFICADO"
    CALCULADO = "CALCULADO"
    ESTIMADO = "ESTIMADO"
    INFERIDO = "INFERIDO"
    NO_DISPONIBLE = "NO_DISPONIBLE"

    # Peso de cada etiqueta para el confidence score (regla 76).
    PESO = {
        VERIFICADO: 1.0,
        CALCULADO: 0.85,
        ESTIMADO: 0.55,
        INFERIDO: 0.35,
        NO_DISPONIBLE: 0.0,
    }


@dataclass
class Dato:
    """Un dato con fuente, fecha y etiqueta de calidad (reglas 72, 75)."""
    valor: Any = None
    etiqueta: str = DataLabel.NO_DISPONIBLE
    fuente: str = ""          # id de fuente, p.ej. "emisor", "yahoo"
    fecha: Optional[date] = None
    nota: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["fecha"] = self.fecha.isoformat() if self.fecha else None
        return d

    @staticmethod
    def no_disponible(nota: str = "") -> "Dato":
        return Dato(etiqueta=DataLabel.NO_DISPONIBLE, nota=nota)


# ── Producto (reglas 17-18, 22, 26-28) ──────────────────────────────────────

@dataclass
class Producto:
    """Vehículo de inversión. El ISIN/ticker solo se afirma si está verificado (regla 101)."""
    nombre: str
    ticker: str = ""
    isin: Optional[str] = None          # None = no verificado, nunca inventar
    emisor: str = ""
    categoria: str = "ETF_GLOBAL"       # CATEGORIAS
    naturaleza: str = "ETF_ACCIONES"    # NATURALEZAS
    replica: str = "fisica"             # fisica | sintetica | activa | futuros
    ucits: bool = True
    domicilio: str = ""
    divisa_cotizacion: str = "EUR"
    divisa_activos: str = "USD"
    acumulacion: bool = True
    ter: Dato = field(default_factory=lambda: Dato.no_disponible("TER sin verificar"))
    aum: Dato = field(default_factory=lambda: Dato.no_disponible("AUM sin verificar"))
    spread: Dato = field(default_factory=lambda: Dato.no_disponible())
    antiguedad_anios: Optional[float] = None
    n_posiciones: Optional[int] = None
    concentracion_top10: Dato = field(default_factory=Dato.no_disponible)
    coste_total_estimado: Dato = field(default_factory=lambda: Dato.no_disponible())
    notas: str = ""

    @property
    def id(self) -> str:
        base = self.isin or self.ticker or self.nombre
        return "product:%s" % base.lower().replace(" ", "-")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nombre": self.nombre, "ticker": self.ticker, "isin": self.isin,
            "emisor": self.emisor, "categoria": self.categoria,
            "naturaleza": self.naturaleza, "replica": self.replica,
            "ucits": self.ucits, "domicilio": self.domicilio,
            "divisa_cotizacion": self.divisa_cotizacion,
            "divisa_activos": self.divisa_activos, "acumulacion": self.acumulacion,
            "ter": self.ter.to_dict(), "aum": self.aum.to_dict(),
            "spread": self.spread.to_dict(),
            "antiguedad_anios": self.antiguedad_anios, "n_posiciones": self.n_posiciones,
            "concentracion_top10": self.concentracion_top10.to_dict(),
            "coste_total_estimado": self.coste_total_estimado.to_dict(),
            "notas": self.notas,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Producto":
        def _dato(x: Any) -> Dato:
            if x is None:
                return Dato.no_disponible()
            if isinstance(x, Dato):
                return x
            return Dato(
                valor=x.get("valor"), etiqueta=x.get("etiqueta", DataLabel.NO_DISPONIBLE),
                fuente=x.get("fuente", ""), nota=x.get("nota", ""),
                fecha=date.fromisoformat(x["fecha"]) if x.get("fecha") else None,
            )
        return Producto(
            nombre=d["nombre"], ticker=d.get("ticker", ""), isin=d.get("isin"),
            emisor=d.get("emisor", ""), categoria=d.get("categoria", "ETF_GLOBAL"),
            naturaleza=d.get("naturaleza", "ETF_ACCIONES"),
            replica=d.get("replica", "fisica"), ucits=d.get("ucits", True),
            domicilio=d.get("domicilio", ""),
            divisa_cotizacion=d.get("divisa_cotizacion", "EUR"),
            divisa_activos=d.get("divisa_activos", "USD"),
            acumulacion=d.get("acumulacion", True),
            ter=_dato(d.get("ter")), aum=_dato(d.get("aum")), spread=_dato(d.get("spread")),
            antiguedad_anios=d.get("antiguedad_anios"), n_posiciones=d.get("n_posiciones"),
            concentracion_top10=_dato(d.get("concentracion_top10")),
            coste_total_estimado=_dato(d.get("coste_total_estimado")),
            notas=d.get("notas", ""),
        )


# ── Tesis, catalizadores y escenarios (reglas 19, 38, 41-42) ────────────────

@dataclass
class Catalizador:
    evento: str
    probabilidad: str = "media"      # baja | media | alta (regla 41: sin falsa precisión)
    impacto: str = "medio"           # bajo | medio | alto
    horizonte: str = ""              # p.ej. "6-18 meses"


@dataclass
class Escenario:
    nombre: str                      # BEAR | BASE | BULL | EXTREMO_BULL | EXTREMO_BEAR
    retorno_estimado: Optional[float] = None   # p.ej. -0.25 = -25%
    probabilidad: Optional[float] = None       # 0-1, None si no hay fundamento
    supuestos: str = ""


@dataclass
class Tesis:
    positiva: str = ""
    negativa: str = ""
    catalizadores: List[Catalizador] = field(default_factory=list)
    invalidadores: List[str] = field(default_factory=list)
    escenarios: List[Escenario] = field(default_factory=list)

    def valor_esperado(self) -> Optional[float]:
        """Regla 42: EV = Σ(probabilidad × resultado). None si faltan supuestos."""
        pares = [(e.probabilidad, e.retorno_estimado) for e in self.escenarios]
        if not pares or any(p is None or r is None for p, r in pares):
            return None
        total = sum(p for p, _ in pares)
        if not (0.99 <= total <= 1.01):
            return None
        return sum(p * r for p, r in pares)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "positiva": self.positiva, "negativa": self.negativa,
            "catalizadores": [asdict(c) for c in self.catalizadores],
            "invalidadores": self.invalidadores,
            "escenarios": [asdict(e) for e in self.escenarios],
        }


# ── Scores (reglas 5-6, 58-61, 76) ──────────────────────────────────────────

def etiqueta_score(score: float) -> str:
    """Regla 6: significado cualitativo del score."""
    s = round(score)
    if s >= 90: return "Oportunidad excepcional"
    if s >= 80: return "Muy atractiva"
    if s >= 70: return "Atractiva"
    if s >= 60: return "Interesante pero con limitaciones"
    if s >= 50: return "Neutral"
    if s >= 40: return "Poco atractiva"
    if s >= 30: return "Desfavorable"
    return "Muy desfavorable"


@dataclass
class Scores:
    """Regla 5: tres scores independientes + vehículo + confianza. Nunca se fusionan."""
    potencial: Optional[float] = None        # A. 0-100 (regla 58)
    rentabilidad_riesgo: Optional[float] = None  # B. 0-100 (regla 59)
    personalizado: Optional[float] = None    # C. 0-100 (regla 61), solo con perfil
    vehiculo: Optional[float] = None         # Regla 60
    confianza: float = 0.0                   # Regla 76: 0-100, independiente del score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "potencial": self.potencial, "rentabilidad_riesgo": self.rentabilidad_riesgo,
            "personalizado": self.personalizado, "vehiculo": self.vehiculo,
            "confianza": self.confianza,
            "etiqueta_potencial": etiqueta_score(self.potencial)
            if self.potencial is not None else None,
            "etiqueta_rr": etiqueta_score(self.rentabilidad_riesgo)
            if self.rentabilidad_riesgo is not None else None,
        }


# ── Buyability y precios de entrada (reglas 86-87) ─────────────────────────

class Buyability:
    COMPRA_ATRACTIVA = "COMPRA_ATRACTIVA"
    COMPRA_SELECTIVA = "COMPRA_SELECTIVA"
    MANTENER_ESPERAR = "MANTENER / ESPERAR"
    ESPERAR_MEJOR_PRECIO = "ESPERAR_MEJOR_PRECIO"
    EVITAR = "EVITAR"

    TODOS = [COMPRA_ATRACTIVA, COMPRA_SELECTIVA, MANTENER_ESPERAR,
             ESPERAR_MEJOR_PRECIO, EVITAR]


@dataclass
class NivelesEntrada:
    """Regla 87: nunca presentar como exacto lo que depende de supuestos."""
    precio_actual: Optional[float] = None
    fair_value: Optional[float] = None
    precio_atractivo: Optional[float] = None
    precio_muy_atractivo: Optional[float] = None
    nivel_invalidacion: Optional[float] = None
    etiqueta_fair_value: str = DataLabel.ESTIMADO   # regla 33: observado/estimado/...

    def margen_seguridad(self) -> Optional[float]:
        """Regla 34: Fair Value / Precio − 1."""
        if self.fair_value and self.precio_actual:
            return self.fair_value / self.precio_actual - 1
        return None


# ── Perfil y cartera (reglas 13-14) ─────────────────────────────────────────

@dataclass
class PerfilInversor:
    """Regla 13. No inventar información ausente: campos opcionales."""
    residencia_fiscal: str = "ES"
    edad: Optional[int] = None
    patrimonio_eur: Optional[float] = None
    ingresos_anuales_eur: Optional[float] = None
    capital_disponible_eur: Optional[float] = None
    aportacion_mensual_eur: Optional[float] = None
    horizonte_anios: float = 1.5              # regla 16: por defecto 1-2 años
    tolerancia_riesgo: Optional[int] = None   # 1-5
    capacidad_perdida: Optional[int] = None   # 1-5
    experiencia: Optional[str] = None         # principiante | media | alta
    objetivos: List[str] = field(default_factory=list)
    estrategia: str = ""
    broker: Optional[str] = None
    moneda_base: str = "EUR"
    preferencias: List[str] = field(default_factory=list)
    restricciones: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PerfilInversor":
        valid = {f for f in PerfilInversor.__dataclass_fields__}
        return PerfilInversor(**{k: v for k, v in d.items() if k in valid})


@dataclass
class Posicion:
    producto: str                    # nombre o ticker
    peso: float                      # 0-1
    categoria: str = ""
    isin: Optional[str] = None


@dataclass
class Cartera:
    posiciones: List[Posicion] = field(default_factory=list)

    def concentracion_maxima(self) -> Optional[float]:
        return max((p.peso for p in self.posiciones), default=None)


# ── Análisis (reglas 18, 91, 125) ───────────────────────────────────────────

@dataclass
class AnalisisProducto:
    producto: Producto
    explicacion_sencilla: str = ""     # regla 98: 1-3 frases para principiante
    calidad_subyacente: str = ""       # regla 18: separado de la calidad del vehículo
    tesis: Tesis = field(default_factory=Tesis)
    scores: Scores = field(default_factory=Scores)
    niveles: NivelesEntrada = field(default_factory=NivelesEntrada)
    buyability: str = Buyability.MANTENER_ESPERAR
    riesgos: List[str] = field(default_factory=list)          # regla 39
    coste_total_nota: str = ""          # regla 23
    accesibilidad: str = "pendiente de conocer el broker"     # regla 71
    fiscalidad_nota: str = ""           # regla 29
    red_team: List[str] = field(default_factory=list)         # regla 118-119
    vigilar: List[str] = field(default_factory=list)          # regla 106
    # id de métrica → Dato.to_dict() CALCULADO (regla 75), p.ej. volatilidad_anual
    metricas_riesgo: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "producto": self.producto.to_dict(),
            "explicacion_sencilla": self.explicacion_sencilla,
            "calidad_subyacente": self.calidad_subyacente,
            "tesis": self.tesis.to_dict(),
            "scores": self.scores.to_dict(),
            "niveles": asdict(self.niveles),
            "buyability": self.buyability,
            "riesgos": self.riesgos,
            "coste_total_nota": self.coste_total_nota,
            "accesibilidad": self.accesibilidad,
            "fiscalidad_nota": self.fiscalidad_nota,
            "red_team": self.red_team,
            "vigilar": self.vigilar,
            "metricas_riesgo": self.metricas_riesgo,
        }


@dataclass
class Descartado:
    producto: str
    motivo: str


@dataclass
class AnalisisCompleto:
    """Regla 155: resultado ejecutivo completo de una temática."""
    tema: str
    fecha: str                                  # ISO (regla 122: fecha de corte)
    conclusion: str = ""
    top5: List[AnalisisProducto] = field(default_factory=list)
    descartados: List[Descartado] = field(default_factory=list)
    ganadores: Dict[str, str] = field(default_factory=dict)     # regla 84/127
    recomendacion: str = ""                                     # regla 128
    confianza_analisis: str = "media"                          # regla 129
    advertencia_sin_perfil: str = ""                           # regla 12
    robustez: str = ""                                          # regla 116
    control_top5: str = ""                                      # regla 80: control final
    seguimiento: List[str] = field(default_factory=list)        # regla 105

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tema": self.tema, "fecha": self.fecha, "conclusion": self.conclusion,
            "top5": [a.to_dict() for a in self.top5],
            "descartados": [asdict(d) for d in self.descartados],
            "ganadores": self.ganadores, "recomendacion": self.recomendacion,
            "confianza_analisis": self.confianza_analisis,
            "advertencia_sin_perfil": self.advertencia_sin_perfil,
            "robustez": self.robustez,
            "_control": self.control_top5,
            "seguimiento": self.seguimiento,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
