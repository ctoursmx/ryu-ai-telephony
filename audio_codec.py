# -*- coding: utf-8 -*-
"""
Modulo de Codecs de Audio G.711 y Procesamiento PCM (100% OS / Python 3.13+ Compliant)
Reemplaza por completo audioop con tablas vectorizadas NumPy y libsoxr.
"""
import base64
import zlib
import numpy as np
import soxr

_B64_A = "gOqA64DogOmA7oDvgOyA7YDigOOA4IDhgOaA54DkgOVA9cD1QPTA9ED3wPdA9sD2QPHA8UDwwPBA88DzQPLA8gCqAK4AogCmALoAvgCyALYAigCOAIIAhgCaAJ4AkgCWANUA1wDRANMA3QDfANkA2wDFAMcAwQDDAM0AzwDJAMuo/rj+iP6Y/uj++P7I/tj+KP44/gj+GP5o/nj+SP5Y/qj/uP+I/5j/6P/4/8j/2P8o/zj/CP8Y/2j/eP9I/1j/oPrg+iD6YPqg++D7IPtg+6D44Pgg+GD4oPng+SD5YPlQ/XD9EP0w/dD98P2Q/bD9UPxw/BD8MPzQ/PD8kPyw/IAVgBSAF4AWgBGAEIATgBKAHYAcgB+AHoAZgBiAG4AawApACsALQAvACEAIwAlACcAOQA7AD0APwAxADMANQA0AVgBSAF4AWgBGAEIATgBKAHYAcgB+AHoAZgBiAG4AagArACkALwAtACMAIQAnACUAOwA5AD8APQAzADEANwA1WAFIAXgBaAEYAQgBOAEoAdgByAH4AegBmAGIAbgBqAFYAEgAeABoABgACAA4ACgA2ADIAPgA6ACYAIgAuACoAGAFIAXgBaAFYAQgBOAEoARgByAH4AegB2AGIAbgBqAGsAKQAvAC0AIwAhACcAJQArADkAPwA9ADMAMQA3ADUAM="
_B64_U = "hIKEhoSKhI6EkoSWhJqEnoSihKaEqoSuhLKEtoS6hL6EwYTDhMWEx4TJhMuEzYTPhNGE04TVhNeE2YTbhN2E3wThBOIE4wTkBOUE5gTnBOgE6QTqBOsE7ATtBO4E7wTwxPBE8cTxRPLE8kTzxPNE9MT0RPXE9UT2xPZE98T3RPik+OT4JPlk+aT55Pkk+mT6pPrk+iT7ZPuk++T7JPxk/JT8tPzU/PT8FP00/VT9dP2U/bT91P30/RT+NP5U/nT+jP6c/qz+vP7M/tz+7P78/gz/HP8s/zz/TP9c/2z/fP+I/5D/mP+g/6j/sP+4/8D/yP/Q/9j/4P/o//D/+P8AAHx9fHl8dXxxfG18aXxlfGF8XXxZfFV8UXxNfEl8RXxBfD58PHw6fDh8Nnw0fDJ8MHwufCx8KnwofCZ8JHwifCD8Hvwd/Bz8G/wa/Bn8GPwX/Bb8FfwU/BP8EvwR/BD8DzwPvA48DrwNPA28DDwMvAs8C7wKPAq8CTwJvAg8CLwHXAccB9wGnAZcBhwG3AWcBVwFHAXcBJwEXAQcBNwDnANsA0wDLAMMA+wCzAKsAowCbAJMAiwCDALsAcwBrAGMAXQBZAFUAUQBNAEkARQBBAH0AOQA1ADEALQApACUAIQAeABwAGgAYABYAFAASABAADgAMAAoACAAGAAQAAgAAAA="
_B64_L = "eJztwTOgGAgQBNDYuti6i35sWxfbtm3btm3btm3bttFvs8UWW8y8FxBARKhSEhGs5EQEKwURwUpDRLDSEhGsVEQEKzURwUpMRLD+JSJYCYkIViIigpWUiGAlIyJY/xERrCREBCsHQctJ0LIRtOwELQ9By0vQchG03AQtA0HLSNDSEbT0BC0LQctK0DIRtMwELQy4sOBCgQsNLgK4iODCgQsPLgi4oOACgQsMLgS4kOCCgQsOLrazOM5iOovlLL6zBM7iOovnLLKzKM4iOfvHWXRnMZxFdRbNWXOjFkZNjZoZtTZqY9TSqJVRfaMGRnWN6hk1Nmpi1NCokVF3RQ9FV0U3RW9FH0VPRS9Fe0UHRVtFO0VnRRdFR0UnRXGhhPC/UEwoLZQRSgqlhAJCQSGfkF8oIhQVCgmFhepCDaGqUE2oLdQRagq1hPJCBaGsUE6oLFQRKgqVhEvCReGKcFk4J5wVLgjnhVvCTeGOcFu4JlwVbgjXhUPCQeGIcFjYJ+wVDgj7hVPCSeGMcFo4JhwVTgjHhU+Kj4ovis+Kd4q3ig+K94pfip+KP4rfim+Kr4ofiu+KR0YPjZ4YPTa6Z3TX6IHRfaNXRi+N3hi9Nnpm9NTohdFzo0nOJjqb4myys3HOxjqb4Gy8s1nOZjqb42y2s2nOpjqb4Wy6s0HgBoIbAm4wuH7g+oIbAK4/uFHgRoIbA240uGHghoIbAW44uE0EbSNB20LQNhO0dQRtLUHbQNDWE7RdBG0nQdtD0HYTtG0EbStB20HQthO0RUQEayERwVpCRLAWExGseUQEay4RwVpARLDmExGsVUQEayURwVpDRLBWExGsZUQEaykRwVpBRLCWExGsvyPcZjc="

_ALAW_TABLE = np.frombuffer(base64.b64decode(_B64_A), dtype=np.int16)
_ULAW_TABLE = np.frombuffer(base64.b64decode(_B64_U), dtype=np.int16)
_LIN2ALAW_TABLE = np.frombuffer(zlib.decompress(base64.b64decode(_B64_L)), dtype=np.uint8)

def alaw2pcm(payload: bytes) -> bytes:
    if not payload:
        return b""
    return _ALAW_TABLE[np.frombuffer(payload, dtype=np.uint8)].tobytes()

def ulaw2pcm(payload: bytes) -> bytes:
    if not payload:
        return b""
    return _ULAW_TABLE[np.frombuffer(payload, dtype=np.uint8)].tobytes()

def pcm2alaw(pcm_bytes: bytes) -> bytes:
    if not pcm_bytes:
        return b""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return _LIN2ALAW_TABLE[samples.astype(np.int32) + 32768].tobytes()

def calculate_pcm_rms(pcm_data: bytes) -> int:
    if not pcm_data or len(pcm_data) < 2:
        return 0
    samples = np.frombuffer(pcm_data, dtype=np.int16)
    if len(samples) == 0:
        return 0
    return int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

def resample_8k_to_16k(pcm8k_bytes: bytes) -> np.ndarray:
    if not pcm8k_bytes:
        return np.array([], dtype=np.float32)
    int16_arr = np.frombuffer(pcm8k_bytes, dtype=np.int16)
    float_8k = int16_arr.astype(np.float32) / 32768.0
    return soxr.resample(float_8k, 8000, 16000, quality='HQ')
