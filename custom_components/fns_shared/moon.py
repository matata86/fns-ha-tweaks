"""Východ a západ Měsíce.

Astral, který má HA po ruce, počítá ``moonrise`` chybně, když východ padne
těsně za půlnoc — vrátí ``None`` nebo vyhodí „Moon never rises on this date"
(ověřeno na astral 3.2, 6.–7. 9. 2026). Proto vlastní výpočet: zkrácená
Meeusova řada pro polohu Měsíce (kap. 47) a hledání průchodu obzorem
po minutách. Proti hodinkám Garmin sedí na dvě minuty.
"""
import math, datetime as dt

RAD = math.pi / 180.0

def _jd(when: dt.datetime) -> float:
    u = when.astimezone(dt.timezone.utc)
    y, m = u.year, u.month
    if m <= 2:
        y -= 1; m += 12
    a = y // 100
    b = 2 - a + a // 4
    day = u.day + (u.hour + (u.minute + (u.second + u.microsecond / 1e6) / 60) / 60) / 24
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5

def _moon_ra_dec(jd):
    """Rovníkové souřadnice Měsíce (Meeus, kap. 47, zkrácená řada) — přesnost ~1'."""
    t = (jd - 2451545.0) / 36525.0
    lp = 218.3164477 + 481267.88123421 * t - 0.0015786 * t * t
    d  = 297.8501921 + 445267.1114034 * t - 0.0018819 * t * t
    m  = 357.5291092 + 35999.0502909 * t
    mp = 134.9633964 + 477198.8675055 * t + 0.0087414 * t * t
    f  = 93.2720950 + 483202.0175233 * t - 0.0036539 * t * t
    d, m, mp, f = (x * RAD for x in (d, m, mp, f))
    lon = lp + (
        6.288774 * math.sin(mp) + 1.274027 * math.sin(2 * d - mp) + 0.658314 * math.sin(2 * d)
        + 0.213618 * math.sin(2 * mp) - 0.185116 * math.sin(m) - 0.114332 * math.sin(2 * f)
        + 0.058793 * math.sin(2 * d - 2 * mp) + 0.057066 * math.sin(2 * d - m - mp)
        + 0.053322 * math.sin(2 * d + mp) + 0.045758 * math.sin(2 * d - m)
        - 0.040923 * math.sin(m - mp) - 0.034720 * math.sin(d) - 0.030383 * math.sin(m + mp)
        + 0.015327 * math.sin(2 * d - 2 * f) - 0.012528 * math.sin(mp + 2 * f)
        + 0.010980 * math.sin(mp - 2 * f) + 0.010675 * math.sin(4 * d - mp)
        + 0.010034 * math.sin(3 * mp) + 0.008548 * math.sin(4 * d - 2 * mp)
    )
    lat = (
        5.128122 * math.sin(f) + 0.280602 * math.sin(mp + f) + 0.277693 * math.sin(mp - f)
        + 0.173237 * math.sin(2 * d - f) + 0.055413 * math.sin(2 * d - mp + f)
        + 0.046271 * math.sin(2 * d - mp - f) + 0.032573 * math.sin(2 * d + f)
        + 0.017198 * math.sin(2 * mp + f) + 0.009266 * math.sin(2 * d + mp - f)
        + 0.008822 * math.sin(2 * mp - f) + 0.008216 * math.sin(2 * d - m - f)
        + 0.004324 * math.sin(2 * d - 2 * mp - f) + 0.004200 * math.sin(2 * d + mp + f)
    )
    dist = 385000.56 - 20905.355 * math.cos(mp) - 3699.111 * math.cos(2 * d - mp) \
        - 2955.968 * math.cos(2 * d) - 569.925 * math.cos(2 * mp)
    eps = (23.439291 - 0.0130042 * t) * RAD
    lon, lat = lon * RAD, lat * RAD
    ra = math.atan2(math.sin(lon) * math.cos(eps) - math.tan(lat) * math.sin(eps), math.cos(lon))
    dec = math.asin(math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon))
    return ra, dec, dist

def _gmst(jd):
    t = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t
    return (g % 360.0) * RAD

def altitude(when, lat, lon):
    """Výška středu Měsíce nad obzorem ve stupních, opravená o paralaxu a refrakci."""
    jd = _jd(when)
    ra, dec, dist = _moon_ra_dec(jd)
    h = _gmst(jd) + lon * RAD - ra
    la = lat * RAD
    sin_alt = math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(h)
    alt = math.asin(sin_alt) / RAD
    parallax = math.asin(6378.14 / dist) / RAD          # obzorová paralaxa
    return alt - parallax * math.cos(alt * RAD) + 0.5667 + 0.25    # refrakce + poloměr kotouče

def events(day, lat, lon, tz):
    """Vrátí (východ, západ) pro daný místní den; None, když událost ten den není."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=tz)
    rise = setting = None
    prev = altitude(start, lat, lon)
    for minute in range(1, 24 * 60 + 1):
        t = start + dt.timedelta(minutes=minute)
        cur = altitude(t, lat, lon)
        if prev < 0 <= cur and rise is None:
            rise = t
        if prev >= 0 > cur and setting is None:
            setting = t
        prev = cur
    return rise, setting

def _sun_lon(jd):
    """Zdánlivá ekliptikální délka Slunce ve stupních (Meeus, kap. 25, zkráceně)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t
    m = (357.52911 + 35999.05029 * t) * RAD
    c = (1.914602 - 0.004817 * t) * math.sin(m) + 0.019993 * math.sin(2 * m) \
        + 0.000289 * math.sin(3 * m)
    return (l0 + c) % 360.0


def illumination(when: dt.datetime) -> float:
    """Osvětlená část kotouče v procentech (0–100)."""
    jd = _jd(when)
    t = (jd - 2451545.0) / 36525.0
    lp = 218.3164477 + 481267.88123421 * t
    d = (297.8501921 + 445267.1114034 * t) * RAD
    m = (357.5291092 + 35999.0502909 * t) * RAD
    mp = (134.9633964 + 477198.8675055 * t) * RAD
    f = (93.2720950 + 483202.0175233 * t) * RAD
    lon = lp + (6.288774 * math.sin(mp) + 1.274027 * math.sin(2 * d - mp)
                + 0.658314 * math.sin(2 * d) + 0.213618 * math.sin(2 * mp)
                - 0.185116 * math.sin(m) - 0.114332 * math.sin(2 * f))
    elong = (lon - _sun_lon(jd)) % 360.0
    return (1 - math.cos(elong * RAD)) / 2 * 100
