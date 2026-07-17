#!/usr/bin/env python3
"""
Vedic Astrology (Jyotiṣa) compute engine.

This is the calculation core extracted from the original command-line script.
All astronomy / astrology math is unchanged. The terminal (ANSI) rendering and
interactive input have been removed so the same logic can drive a web UI.

Accuracy tiers - tried automatically in order:
  1. pyswisseph   Swiss Ephemeris DE431, < 0.001°   pip install pyswisseph
  2. JPL Horizons Same DE431 via REST API, < 0.001° internet required
  3. Built-in     Meeus + JPL Keplerian,  ~0.5°     always available
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import json, math, re, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing   import Dict, List, Optional, Tuple

# ── optional path to Swiss Ephemeris .se1 ephemeris files ─────────────────────
EPHE_PATH = ""

# ── Swiss Ephemeris (pyswisseph) ──────────────────────────────────────────────
try:
    import swisseph as swe
    swe.set_ephe_path(EPHE_PATH or None)
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    _SWE = True
except ImportError:
    _SWE = False

# ── zoneinfo - historically correct DST (Python 3.9+) ────────────────────────
try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    _ZONEINFO = True
except ImportError:
    _ZONEINFO = False
    ZoneInfo = None                    # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# ASTROLOGY DATA
# ══════════════════════════════════════════════════════════════════════════════

SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces",
]
SIGN_ABR = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

SIGN_LORDS = {
    "Aries":"Mars",     "Taurus":"Venus",   "Gemini":"Mercury",
    "Cancer":"Moon",    "Leo":"Sun",         "Virgo":"Mercury",
    "Libra":"Venus",    "Scorpio":"Mars",    "Sagittarius":"Jupiter",
    "Capricorn":"Saturn","Aquarius":"Saturn","Pisces":"Jupiter",
}

NAKSHATRAS: List[Tuple[str,str]] = [
    ("Ashwini","Ketu"),          ("Bharani","Venus"),       ("Krittika","Sun"),
    ("Rohini","Moon"),           ("Mrigashira","Mars"),     ("Ardra","Rahu"),
    ("Punarvasu","Jupiter"),     ("Pushya","Saturn"),       ("Ashlesha","Mercury"),
    ("Magha","Ketu"),            ("Purva Phalguni","Venus"),("Uttara Phalguni","Sun"),
    ("Hasta","Moon"),            ("Chitra","Mars"),         ("Swati","Rahu"),
    ("Vishakha","Jupiter"),      ("Anuradha","Saturn"),     ("Jyeshtha","Mercury"),
    ("Mula","Ketu"),             ("Purva Ashadha","Venus"), ("Uttara Ashadha","Sun"),
    ("Shravana","Moon"),         ("Dhanishtha","Mars"),     ("Shatabhisha","Rahu"),
    ("Purva Bhadrapada","Jupiter"),("Uttara Bhadrapada","Saturn"),("Revati","Mercury"),
]

NAK_ABR = [
    "Asw","Bha","Kri","Roh","Mri","Ard","Pun","Pus","Ash",
    "Mag","PPh","UPh","Has","Chi","Swa","Vis","Anu","Jye",
    "Mul","PAs","UAs","Shr","Dha","Sha","PBh","UBh","Rev",
]

# Namakṣara — the name-syllable of each of the 108 padas (Swara Siddhānta).
# 27 nakshatras × 4 padas, in nakshatra order. Used for the traditional first
# syllable of the given name. Interpretation aid only — never affects calculation.
NAMAKSHARA = [
    ["Chu","Che","Cho","La"],        # Ashwini
    ["Li","Lu","Le","Lo"],           # Bharani
    ["A","I","U","E"],               # Krittika
    ["O","Va","Vi","Vu"],            # Rohini
    ["Ve","Vo","Ka","Ki"],           # Mrigashira
    ["Ku","Gha","Ng","Chha"],        # Ardra
    ["Ke","Ko","Ha","Hi"],           # Punarvasu
    ["Hu","He","Ho","Da"],           # Pushya
    ["Di","Du","De","Do"],           # Ashlesha
    ["Ma","Mi","Mu","Me"],           # Magha
    ["Mo","Ta","Ti","Tu"],           # Purva Phalguni
    ["Te","To","Pa","Pi"],           # Uttara Phalguni
    ["Pu","Sha","Na","Tha"],         # Hasta
    ["Pe","Po","Ra","Ri"],           # Chitra
    ["Ru","Re","Ro","Ta"],           # Swati
    ["Ti","Tu","Te","To"],           # Vishakha
    ["Na","Ni","Nu","Ne"],           # Anuradha
    ["No","Ya","Yi","Yu"],           # Jyeshtha
    ["Ye","Yo","Bha","Bhi"],         # Mula
    ["Bhu","Dha","Pha","Dha"],       # Purva Ashadha
    ["Bhe","Bho","Ja","Ji"],         # Uttara Ashadha
    ["Ju","Je","Jo","Gha"],          # Shravana
    ["Ga","Gi","Gu","Ge"],           # Dhanishtha
    ["Go","Sa","Si","Su"],           # Shatabhisha
    ["Se","So","Da","Di"],           # Purva Bhadrapada
    ["Du","Tha","Jha","Tra"],        # Uttara Bhadrapada
    ["De","Do","Cha","Chi"],         # Revati
]

DASHA_ORDER = ["Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury"]
DASHA_YEARS = {"Ketu":7,"Venus":20,"Sun":6,"Moon":10,"Mars":7,
               "Rahu":18,"Jupiter":16,"Saturn":19,"Mercury":17}
DASHA_TOTAL = 120

EXALT_SIGN = {"Sun":0,"Moon":1,"Mars":9,"Mercury":5,"Jupiter":3,
              "Venus":11,"Saturn":6,"Rahu":1,"Ketu":7}
EXALT_DEG  = {"Sun":10,"Moon":3,"Mars":28,"Mercury":15,"Jupiter":5,
              "Venus":27,"Saturn":20,"Rahu":20,"Ketu":20}
DEBIL_SIGN = {"Sun":6,"Moon":7,"Mars":3,"Mercury":11,"Jupiter":9,
              "Venus":5,"Saturn":0,"Rahu":7,"Ketu":1}
OWN_SIGNS  = {"Sun":[4],"Moon":[3],"Mars":[0,7],"Mercury":[2,5],
              "Jupiter":[8,11],"Venus":[1,6],"Saturn":[9,10]}
MOOLA      = {"Sun":(4,0,20),"Moon":(1,4,20),"Mars":(0,0,12),
              "Mercury":(5,16,20),"Jupiter":(8,0,10),"Venus":(6,0,15),"Saturn":(9,0,20)}

PLANET_ORDER = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]
PLANET_ABR   = {"Sun":"Su","Moon":"Mo","Mars":"Ma","Mercury":"Me",
                "Jupiter":"Ju","Venus":"Ve","Saturn":"Sa","Rahu":"Ra","Ketu":"Ke"}

# Ashtakavarga benefic offset tables (BPHS)
_AKV: Dict[str,Dict[str,List[int]]] = {
    "Sun":{"Sun":[1,2,4,7,8,9,10,11],"Moon":[3,6,10,11],"Mars":[1,2,4,7,8,9,10,11],
           "Mercury":[3,5,6,9,10,11,12],"Jupiter":[5,6,9,11],"Venus":[6,7,12],
           "Saturn":[1,2,4,7,8,9,10,11],"Lagna":[3,4,6,10,11,12]},
    "Moon":{"Sun":[3,6,7,8,10,11],"Moon":[1,3,6,7,10,11],"Mars":[2,3,5,6,9,10,11],
            "Mercury":[1,3,4,5,7,8,10,11],"Jupiter":[1,4,7,8,10,11],
            "Venus":[3,4,5,7,9,10,11],"Saturn":[3,5,6,11],"Lagna":[3,6,10,11]},
    "Mars":{"Sun":[3,5,6,10,11],"Moon":[3,6,11],"Mars":[1,2,4,7,8,10,11],
            "Mercury":[3,5,6,11],"Jupiter":[6,10,11,12],"Venus":[6,8,11,12],
            "Saturn":[1,4,7,8,9,10,11],"Lagna":[1,2,4,8,10,11]},
    "Mercury":{"Sun":[5,6,9,11,12],"Moon":[2,4,6,8,10,11],"Mars":[1,2,4,7,8,9,10,11],
               "Mercury":[1,3,5,6,9,10,11,12],"Jupiter":[6,8,11,12],
               "Venus":[1,2,3,4,5,8,9,11],"Saturn":[1,2,4,7,8,9,10,11],
               "Lagna":[1,2,4,6,8,10,11]},
    "Jupiter":{"Sun":[1,2,3,4,7,8,9,10,11],"Moon":[2,5,7,9,11],"Mars":[1,2,4,7,8,10,11],
               "Mercury":[1,2,4,5,6,9,10,11],"Jupiter":[1,2,3,4,7,8,10,11],
               "Venus":[2,5,6,9,10,11],"Saturn":[3,5,6,12],"Lagna":[1,2,4,5,6,7,9,10,11]},
    "Venus":{"Sun":[8,11,12],"Moon":[1,2,3,4,5,8,9,11,12],"Mars":[3,4,6,9,11,12],
             "Mercury":[3,5,6,9,11],"Jupiter":[5,8,9,10,11],"Venus":[1,2,3,4,5,8,9,10,11],
             "Saturn":[3,4,5,8,9,10,11],"Lagna":[1,2,3,4,5,8,9,11]},
    "Saturn":{"Sun":[1,2,4,7,8,9,10,11],"Moon":[3,6,11],"Mars":[3,5,6,10,11,12],
              "Mercury":[6,8,9,10,11,12],"Jupiter":[5,6,11,12],"Venus":[6,11,12],
              "Saturn":[3,5,6,11],"Lagna":[1,3,4,6,10,11]},
}
_AKV_PLANETS = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"]

# South Indian grid: sign index → (row, col)
_SIGN_CELL: Dict[int,Tuple[int,int]] = {
    11:(0,0), 0:(0,1), 1:(0,2),  2:(0,3),
    10:(1,0),                     3:(1,3),
     9:(2,0),                     4:(2,3),
     8:(3,0), 7:(3,1), 6:(3,2),  5:(3,3),
}

_WEEKDAY_LORDS = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn"]
_HORA_ORDER    = ["Sun","Venus","Mercury","Moon","Saturn","Jupiter","Mars"]


# ══════════════════════════════════════════════════════════════════════════════
# TIME UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def julian_day(year:int, month:int, day:int, hour_ut:float) -> float:
    if month <= 2: year -= 1; month += 12
    A = int(year/100); B = 2 - A + int(A/4)
    return int(365.25*(year+4716)) + int(30.6001*(month+1)) + day + hour_ut/24 + B - 1524.5

def j2000c(jd:float) -> float:
    return (jd - 2451545.0) / 36525.0

def norm(a:float) -> float:
    return a % 360.0

def _jd_to_dt_str(jd:float) -> str:
    """JD → 'YYYY-MM-DD HH:MM:SS UTC' string."""
    jd2=jd+0.5; z=int(jd2); f=jd2-z
    if z>=2299161:
        a=int((z-1867216.25)/36524.25); z=z+1+a-a//4
    b=z+1524; c=int((b-122.1)/365.25); d=int(365.25*c); e=int((b-d)/30.6001)
    day2=b-d-int(30.6001*e)
    mo=e-1 if e<14 else e-13
    yr=c-4716 if mo>2 else c-4715
    hf=f*24; h=int(hf); m=int((hf-h)*60); s=int(((hf-h)*60-m)*60)
    return f"{yr}-{mo:02d}-{day2:02d} {h:02d}:{m:02d}:{s:02d} UTC"


# ══════════════════════════════════════════════════════════════════════════════
# TIER 1 - Swiss Ephemeris (pyswisseph)
# ══════════════════════════════════════════════════════════════════════════════

_SWE_ID = {"Sun":0,"Moon":1,"Mercury":2,"Venus":3,"Mars":4,"Jupiter":5,"Saturn":6,"Rahu":10}
_SWE_FL: Optional[int] = None

def _swe_planet(name:str, jd:float) -> float:
    global _SWE_FL
    if _SWE_FL is None: _SWE_FL = swe.FLG_SIDEREAL | swe.FLG_SPEED
    return norm(swe.calc_ut(jd, _SWE_ID[name], _SWE_FL)[0][0])

def _swe_asc(jd:float, lat:float, lon:float) -> float:
    return norm(swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)[1][0])

def _swe_ayan(jd:float) -> float:
    return swe.get_ayanamsa_ex_ut(jd, swe.SIDM_LAHIRI)[0]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 2 - JPL Horizons REST API  (free, no key, same DE431 as Swiss Ephemeris)
# ══════════════════════════════════════════════════════════════════════════════

_HRZ  = "https://ssd.jpl.nasa.gov/api/horizons.api"
_NAIF = {"Sun":"10","Moon":"301","Mercury":"199","Venus":"299",
         "Mars":"499","Jupiter":"599","Saturn":"699"}
_HRZ_CACHE: Dict[Tuple,float] = {}

def _hrz_fetch(planet:str, jd:float) -> Optional[float]:
    key = (planet, round(jd,5))
    if key in _HRZ_CACHE: return _HRZ_CACHE[key]
    params = {"format":"json","COMMAND":_NAIF[planet],"OBJ_DATA":"NO",
              "MAKE_EPHEM":"YES","EPHEM_TYPE":"OBSERVER","CENTER":"500@399",
              "START_TIME":f"JD{jd:.8f}","STOP_TIME":f"JD{jd+0.02:.8f}",
              "STEP_SIZE":"1d","QUANTITIES":"31","CAL_FORMAT":"JD","ANG_FORMAT":"DEG"}
    try:
        req = urllib.request.Request(_HRZ+"?"+urllib.parse.urlencode(params),
              headers={"User-Agent":"VedicAstroCalc/2.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        m = re.search(r"\$\$SOE\n(.*?)\n\$\$EOE", data.get("result",""), re.DOTALL)
        if not m: return None
        floats = [float(t) for t in m.group(1).strip().split("\n")[0].replace("*","").split()
                  if re.fullmatch(r"-?\d+\.?\d*",t)]
        if len(floats) >= 2:
            _HRZ_CACHE[key] = norm(floats[1]); return _HRZ_CACHE[key]
    except Exception: pass
    return None

def _hrz_online() -> bool:
    try:
        req = urllib.request.Request(_HRZ+"?format=json&COMMAND=499&OBJ_DATA=YES&MAKE_EPHEM=NO",
              headers={"User-Agent":"VedicAstroCalc/2.0"})
        with urllib.request.urlopen(req, timeout=5) as r: return r.status == 200
    except Exception: return False


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 - Pure-Python fallback (Meeus Sun/Moon, JPL Keplerian planets)
# ══════════════════════════════════════════════════════════════════════════════

def _ayanamsha(jd:float) -> float:
    T = j2000c(jd)
    return (23.853056 + (5029.097*T + 1.558*T*T) / 3600.0) % 360.0

def _sun(jd:float) -> float:
    T = j2000c(jd)
    L0 = 280.46646 + 36000.76983*T + 0.0003032*T*T
    M  = 357.52911 + 35999.05029*T - 0.0001537*T*T; Mr = math.radians(M%360)
    C  = ((1.914602-0.004817*T-0.000014*T*T)*math.sin(Mr)
          +(0.019993-0.000101*T)*math.sin(2*Mr)+0.000289*math.sin(3*Mr))
    return norm(L0+C-0.00569-0.00478*math.sin(math.radians(125.04-1934.136*T)))

def _moon(jd:float) -> float:
    T=j2000c(jd)
    Lp=218.3164477+481267.88123421*T-0.0015786*T*T+T**3/538841-T**4/65194000
    D =297.8501921+445267.1114034*T -0.0018819*T*T+T**3/545868-T**4/113065000
    M =357.5291092+35999.0502909*T  -0.0001536*T*T+T**3/24490000
    Mp=134.9633964+477198.8675055*T +0.0087414*T*T+T**3/69699-T**4/14712000
    F =93.2720950 +483202.0175233*T -0.0036539*T*T-T**3/3526000+T**4/863310000
    E =1.0-0.002516*T-0.0000074*T*T
    def r(x): return math.radians(x%360)
    dL=(6288774*math.sin(r(Mp))+1274027*math.sin(r(2*D-Mp))+658314*math.sin(r(2*D))
       +213618*math.sin(r(2*Mp))-185116*E*math.sin(r(M))-114332*math.sin(r(2*F))
       +58793*math.sin(r(2*D-2*Mp))+57066*E*math.sin(r(2*D-M-Mp))+53322*math.sin(r(2*D+Mp))
       +45758*E*math.sin(r(2*D-M))-40923*E*math.sin(r(Mp-M))-34720*math.sin(r(D))
       -30383*E*math.sin(r(Mp+M))+15327*math.sin(r(2*D-2*F))-12528*math.sin(r(Mp+2*F))
       +10980*math.sin(r(Mp-2*F))+10675*math.sin(r(4*D-Mp))+10034*math.sin(r(3*Mp))
       +8548*math.sin(r(4*D-2*Mp))-7888*E*math.sin(r(2*D+M-Mp))-6766*E*math.sin(r(2*D+M))
       -5163*math.sin(r(D-Mp))+4987*E*math.sin(r(D+M))+4036*E*math.sin(r(2*D-M+Mp))
       +3994*math.sin(r(2*D+2*Mp))+3861*math.sin(r(4*D))+3665*math.sin(r(2*D-3*Mp))
       -2689*E*math.sin(r(M-2*Mp))-2602*math.sin(r(2*(D-Mp)))+2390*E*math.sin(r(2*D-M-2*Mp))
       -2348*math.sin(r(D+Mp))+2236*E*math.sin(r(2*D-2*M))-2120*E*math.sin(r(2*Mp+M))
       -2069*E*E*math.sin(r(2*M))+2048*E*math.sin(r(2*D-2*M-Mp))-1773*math.sin(r(2*D+Mp-2*F))
       -1595*math.sin(r(2*(D+F)))+1215*E*math.sin(r(4*D-M-Mp))-1110*math.sin(r(2*Mp+2*F))
       -892*math.sin(r(3*D-Mp))-810*E*math.sin(r(2*D+M+Mp))+759*E*math.sin(r(4*D-M-2*Mp))
       -713*E*E*math.sin(r(Mp-2*M))-700*E*E*math.sin(r(2*D+2*M-Mp))
       +691*E*math.sin(r(2*D+M-2*Mp))+596*E*math.sin(r(2*D-M-2*F))+549*math.sin(r(4*D+Mp))
       +537*math.sin(r(4*Mp))+520*E*math.sin(r(4*D-M))-487*math.sin(r(D-2*Mp))
       -399*E*math.sin(r(2*D+M-2*F))-381*math.sin(r(2*Mp-2*F))+351*E*math.sin(r(D+M+Mp))
       -340*math.sin(r(3*D-2*Mp))+330*math.sin(r(4*D-3*Mp))+327*E*math.sin(r(2*D-M+2*Mp))
       -323*E*E*math.sin(r(2*M+Mp))+299*E*math.sin(r(D+M-Mp))+294*math.sin(r(2*D+3*Mp))
       )/1_000_000.0
    return norm(Lp+dL)

def _rahu(jd:float) -> float:
    T=j2000c(jd)
    return norm(125.04452-1934.136261*T+0.0020708*T*T+T**3/450000.0)

_JPL: Dict[str,List[float]] = {
    "Mercury":[0.38709927,0.00000037,0.20563593,0.00001906,7.00497902,-0.00594749,
               252.25032350,149472.67411175,77.45779628,0.16047689,48.33076593,-0.12534081],
    "Venus":  [0.72333566,0.00000390,0.00677672,-0.00004107,3.39467605,-0.00078890,
               181.97909950,58517.81538729,131.60246718,0.00268329,76.67984255,-0.27769418],
    "Earth":  [1.00000261,0.00000562,0.01671123,-0.00004392,-0.00001531,-0.01294668,
               100.46457166,35999.37244981,102.93768193,0.32327364,0.0,0.0],
    "Mars":   [1.52371034,0.00001847,0.09339410,0.00007882,1.84969142,-0.00813131,
               -4.55343205,19140.30268499,-23.94362959,0.44441088,49.55953891,-0.29257343],
    "Jupiter":[5.20288700,-0.00011607,0.04838624,-0.00013253,1.30439695,-0.00183714,
               34.39644051,3034.74612775,14.72847983,0.21252668,100.47390909,0.20469106],
    "Saturn": [9.53667594,-0.00125060,0.05386179,-0.00050991,2.48599187,0.00193609,
               49.95424423,1222.49514316,92.59887831,-0.41897216,113.66242448,-0.28867794],
}

def _kepler(body:str, jd:float) -> Tuple[float,float]:
    el=_JPL[body]; T=j2000c(jd)
    e=el[2]+el[3]*T; L=norm(el[6]+el[7]*T); w=norm(el[8]+el[9]*T); M=norm(L-w)
    E=math.radians(M)
    for _ in range(20):
        dE=(math.radians(M)-E+e*math.sin(E))/(1-e*math.cos(E)); E+=dE
        if abs(dE)<1e-12: break
    v=2*math.degrees(math.atan2(math.sqrt(1+e)*math.sin(E/2),math.sqrt(1-e)*math.cos(E/2)))
    return norm(v+w),(el[0]+el[1]*T)*(1-e*math.cos(E))

def _planet(name:str, jd:float) -> float:
    EL,ER=_kepler("Earth",jd); Ex,Ey=ER*math.cos(math.radians(EL)),ER*math.sin(math.radians(EL))
    PL,PR=_kepler(name,jd); Px,Py=PR*math.cos(math.radians(PL)),PR*math.sin(math.radians(PL))
    return norm(math.degrees(math.atan2(Py-Ey,Px-Ex)))

def _ascendant(jd:float, lat:float, lon:float) -> float:
    T=j2000c(jd)
    RAMC=norm(280.46061837+360.98564736629*(jd-2451545)+0.000387933*T*T-T**3/38710000+lon)
    eps=23.439291111-0.013004167*T-1.6389e-7*T*T+5.0361e-7*T**3
    E,e,la=math.radians(RAMC),math.radians(eps),math.radians(lat)
    return norm(math.degrees(math.atan2(math.cos(E),-(math.sin(E)*math.cos(e)+math.tan(la)*math.sin(e)))))


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE - selects best available tier automatically
# ══════════════════════════════════════════════════════════════════════════════

_hrz_checked: Optional[bool] = None

def compute_positions(jd:float, lat:float, lon:float) -> Tuple[Dict[str,float],float,str]:
    """Return ({graha: sidereal_lon}, ayanamsha, engine_label). Tries tiers 1→2→3."""
    global _hrz_checked

    if _SWE:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)   # always re-set — guards against state loss
        ayan = _swe_ayan(jd)
        lons = {p: _swe_planet(p,jd) for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Rahu")}
        lons["Ketu"] = norm(lons["Rahu"]+180); lons["Ascendant"] = _swe_asc(jd,lat,lon)
        return lons, ayan, "Swiss Ephemeris (pyswisseph)  -  DE431, < 0.001°"

    if _hrz_checked is None:
        _hrz_checked = _hrz_online()

    if _hrz_checked:
        ayan = _ayanamsha(jd); lons = {}; ok = True
        for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn"):
            t = _hrz_fetch(p, jd)
            if t is None: ok = False; break
            lons[p] = norm(t - ayan)
        if ok:
            lons["Rahu"] = norm(_rahu(jd)-ayan); lons["Ketu"] = norm(lons["Rahu"]+180)
            lons["Ascendant"] = norm(_ascendant(jd,lat,lon)-ayan)
            return lons, ayan, "JPL Horizons API  -  DE431, < 0.001°"
        _hrz_checked = False

    ayan = _ayanamsha(jd); lons = {}
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Rahu"):
        t = _sun(jd) if p=="Sun" else _moon(jd) if p=="Moon" else _rahu(jd) if p=="Rahu" else _planet(p,jd)
        lons[p] = norm(t - ayan)
    lons["Ketu"] = norm(lons["Rahu"]+180)
    lons["Ascendant"] = norm(_ascendant(jd,lat,lon)-ayan)
    return lons, ayan, "Built-in math (JPL Keplerian)  -  ~0.5° for planets"

def get_jd(year:int, month:int, day:int, hour_ut:float) -> float:
    return swe.julday(year,month,day,hour_ut) if _SWE else julian_day(year,month,day,hour_ut)


# ══════════════════════════════════════════════════════════════════════════════
# ASTROLOGY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def sign_of(lon:float) -> Tuple[int,str,float]:
    idx = int(lon/30)%12; return idx, SIGNS[idx], lon%30

def nakshatra_of(lon:float) -> Tuple[str,str,int]:
    span=360/27; idx=int(lon/span)%27; pada=int((lon%span)/(span/4))+1
    return NAKSHATRAS[idx][0], NAKSHATRAS[idx][1], pada

def namakshara_of(lon:float) -> str:
    """Return the traditional name-syllable (Namakṣara) for this longitude's pada."""
    span=360/27; idx=int(lon/span)%27; pada=int((lon%span)/(span/4))
    return NAMAKSHARA[idx][pada]

def dignity_of(planet:str, si:int, deg:float) -> str:
    if planet in ("Rahu","Ketu"):
        if EXALT_SIGN.get(planet)==si: return "Exalted"
        if DEBIL_SIGN.get(planet)==si: return "Debilitated"
        return "-"
    if EXALT_SIGN.get(planet)==si:
        return "Exalted"+(" (exact)" if abs(deg-EXALT_DEG.get(planet,-1))<1 else "")
    if DEBIL_SIGN.get(planet)==si: return "Debilitated"
    mt=MOOLA.get(planet)
    if mt and si==mt[0] and mt[1]<=deg<=mt[2]: return "Moolatrikona"
    if si in OWN_SIGNS.get(planet,[]): return "Own Sign"
    return "-"

def _planet_record(name:str, lon:float) -> Dict:
    """Build a complete planet data record from a sidereal longitude."""
    si,sn,di = sign_of(lon); nak,nl,pada = nakshatra_of(lon)
    return {"lon":round(lon,4),"sign_idx":si,"sign":sn,"sign_lord":SIGN_LORDS[sn],
            "pos":f"{int(di)}° {int((di%1)*60):02d}'","nakshatra":nak,"nak_lord":nl,
            "pada":pada,"syllable":namakshara_of(lon),
            "dignity":dignity_of(name,si,di) if name!="Ascendant" else "-"}


# ══════════════════════════════════════════════════════════════════════════════
# DIVISIONAL CHARTS
# ══════════════════════════════════════════════════════════════════════════════

_D9_START = [0,9,6,3,0,9,6,3,0,9,6,3]   # navamsa start by natal sign

def navamsa_sign(lon:float) -> int:
    sign=int(lon/30)%12; part=int((lon%30)/(30/9))
    return (_D9_START[sign]+part)%12

def drekkana_sign(lon:float) -> int:
    sign=int(lon/30)%12; return (sign+int((lon%30)/10)*4)%12

def dasamsha_sign(lon:float) -> int:
    sign=int(lon/30)%12; start=sign if sign%2==0 else (sign+8)%12
    return (start+int((lon%30)/3))%12

def chaturthamsha_sign(lon:float) -> int:
    # D4: each sign in 4 parts of 7°30'; parts fall in the sign itself and its
    # 4th, 7th, 10th (the Kendras from that sign)
    sign=int(lon/30)%12; part=int((lon%30)/7.5)
    return (sign+part*3)%12

def divisional_sign(lon:float, div:int) -> int:
    if div==9:  return navamsa_sign(lon)
    if div==3:  return drekkana_sign(lon)
    if div==10: return dasamsha_sign(lon)
    if div==4:  return chaturthamsha_sign(lon)
    return int(lon/30)%12

def compute_divisional(lons:Dict[str,float], div:int) -> Dict[str,int]:
    return {name: divisional_sign(lon, div) for name,lon in lons.items()}

def compute_divisional_full(lons:Dict[str,float], div:int) -> Dict[str,Dict]:
    """Divisional chart with per-planet dignity in the divisional sign,
    plus vargottama flag (same sign in D1 and this varga). Single source of truth.
    Also attaches chart-level metadata under the '_meta' key: lagna sign,
    lagna_occupants (planets in the divisional lagna), and vipareeta_raja_yoga."""
    out = {}
    asc_si = None
    for name, lon in lons.items():
        d_si = divisional_sign(lon, div)
        d1_si = int(lon/30) % 12
        if name == "Ascendant":
            asc_si = d_si
            out[name] = {"sign_idx": d_si, "sign": SIGNS[d_si], "dignity": "-",
                         "vargottama": (d_si == d1_si)}
        else:
            out[name] = {
                "sign_idx":   d_si,
                "sign":       SIGNS[d_si],
                "dignity":    dignity_of(name, d_si, 15.0),
                "vargottama": (d_si == d1_si),
            }

    # Chart-level metadata
    if asc_si is not None:
        DUSTHANA = {6, 8, 12}
        # planets in the divisional lagna
        lagna_occ = [p for p, rec in out.items()
                     if p != "Ascendant" and rec["sign_idx"] == asc_si]
        # house of each planet in this divisional chart
        p_houses = {p: ((rec["sign_idx"] - asc_si) % 12 + 1)
                    for p, rec in out.items() if p != "Ascendant"}
        # Vipareeta Raja Yoga: dusthana lord placed in a dusthana
        vry = []
        for hd in DUSTHANA:
            sign_of_house = (asc_si + hd - 1) % 12
            lord = SIGN_LORDS.get(SIGNS[sign_of_house])
            if lord and lord in p_houses and p_houses[lord] in DUSTHANA:
                vry.append(f"{lord} (lord of H{hd}) in H{p_houses[lord]}")
        # Parivartana (mutual sign exchange) within THIS varga. Classified by
        # the exchanged houses: Raja (kendra/trikona ↔ kendra/trikona),
        # Dainya (a dusthana is involved), else Kahala. An exchange involving
        # a debilitated planet cancels its debilitation (Neecha Bhanga).
        GOOD = {1, 4, 5, 7, 9, 10}
        pariv = []
        seven = [p for p in p_houses if p in OWN_SIGNS]
        d_si  = {p: out[p]["sign_idx"] for p in seven}
        for i, a in enumerate(seven):
            for b in seven[i+1:]:
                if d_si[a] in OWN_SIGNS.get(b, []) and d_si[b] in OWN_SIGNS.get(a, []):
                    ha, hb = p_houses[a], p_houses[b]
                    kind = ("Raja" if ha in GOOD and hb in GOOD else
                            "Dainya" if ha in DUSTHANA or hb in DUSTHANA else
                            "Kahala")
                    txt = f"{a} \u21c4 {b} — exchange across H{ha}/H{hb} ({kind})"
                    nb = [p for p in (a, b) if out[p]["dignity"] == "Debilitated"]
                    if nb:
                        txt += f"; cancels debilitation of {', '.join(nb)} (Neecha Bhanga)"
                    pariv.append(txt)
        out["_meta"] = {
            "lagna": SIGNS[asc_si],
            "lagna_occupants": lagna_occ,
            "vipareeta_raja_yoga": vry,
            "parivartana": pariv,
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# LORDSHIPS & ASPECTS  (single source of truth for interpretation layer)
# ══════════════════════════════════════════════════════════════════════════════

_MALEFICS = {"Sun","Mars","Saturn","Rahu","Ketu"}
_BENEFICS = {"Jupiter","Venus","Moon","Mercury"}

# Which sign each planet rules (Parashara). sign_idx 0=Aries .. 11=Pisces
_SIGN_RULER = [
    ("Mars",0),("Venus",1),("Mercury",2),("Moon",3),("Sun",4),("Mercury",5),
    ("Venus",6),("Mars",7),("Jupiter",8),("Saturn",9),("Saturn",10),("Jupiter",11),
]

# Special aspects (graha drishti) by planet — the houses counted from the planet
_SPECIAL_ASPECTS = {
    "Mars":[4,8], "Jupiter":[5,9], "Saturn":[3,10], "Rahu":[5,9], "Ketu":[5,9],
}

def compute_lordships(lagna_idx:int) -> Dict[str,List[int]]:
    """Return {planet: [house_numbers_it_rules]} for the given lagna."""
    lords: Dict[str,List[int]] = {}
    for planet, sign_idx in _SIGN_RULER:
        house = (sign_idx - lagna_idx) % 12 + 1
        lords.setdefault(planet, []).append(house)
    return lords

def compute_aspects(planets:Dict, lagna_idx:int) -> Dict:
    """Graha Drishti with benefic/malefic tagging, lordship context, own-sign
    strengthening, and house-level net summaries. Single source of truth."""
    aspects: Dict = {}
    planet_houses = {p: d.get("house", 0) for p,d in planets.items() if p!="Ascendant"}
    lordships = compute_lordships(lagna_idx)

    house_benefic = {h: [] for h in range(1, 13)}
    house_malefic = {h: [] for h in range(1, 13)}

    for p1, h1 in planet_houses.items():
        if h1 == 0: continue
        house_to_aspnum = {}
        h7 = ((h1 + 6 - 1) % 12) + 1
        house_to_aspnum[h7] = 7
        for offset in _SPECIAL_ASPECTS.get(p1, []):
            hx = ((h1 + offset - 2) % 12) + 1
            house_to_aspnum[hx] = offset

        p1_lords = lordships.get(p1, [])
        is_malefic = p1 in _MALEFICS
        lord_ctx = f" carrying H{'+H'.join(str(h) for h in sorted(p1_lords))}-energy" if p1_lords else ""

        for p2, h2 in planet_houses.items():
            if p2 == p1 or h2 == 0: continue
            if h2 in house_to_aspnum:
                asp_num = house_to_aspnum[h2]
                owns_target = h2 in p1_lords
                own_note = " [own-lord → strengthens despite malefic nature]" if owns_target and is_malefic else ""
                mal_note = " [MALEFIC → afflicts but energises]" if is_malefic and not owns_target else ""
                entry = aspects.get(p1, [])
                entry.append(f"{asp_num}th on {p2} (H{h1}→H{h2}){lord_ctx}{own_note}{mal_note}")
                aspects[p1] = entry
                recv = aspects.get(p2, [])
                recv.append(f"receives {asp_num}th from {p1}{lord_ctx}{own_note}{mal_note}")
                aspects[p2] = recv

        for asp_h, asp_num in house_to_aspnum.items():
            owns_target = asp_h in p1_lords
            lord_ctx_h = f"{p1}({asp_num}th,lord-H{'+H'.join(str(h) for h in sorted(p1_lords))})" if p1_lords else f"{p1}({asp_num}th)"
            own_note_h = "[own-lord]" if owns_target and is_malefic else ""
            mal_note_h = "[MALEFIC]" if is_malefic and not owns_target else ""
            entry_h = f"{lord_ctx_h}{own_note_h}{mal_note_h}"
            if is_malefic and not owns_target:
                house_malefic[asp_h].append(entry_h)
            else:
                house_benefic[asp_h].append(entry_h)

    aspects["_house_aspects"] = {}
    for h in range(1, 13):
        ben = house_benefic[h]; mal = house_malefic[h]
        if not ben and not mal: continue
        net = ("strengthened" if ben and not mal
               else "afflicted" if mal and not ben else "mixed")
        aspects["_house_aspects"][h] = {"benefic_aspects": ben,
                                        "malefic_aspects": mal, "net": net}
    return aspects


# Classical combustion (Asta) orbs in degrees of ecliptic separation from Sun
# (Suryasiddhanta/Phaladeepika). Mercury 12° / Venus 8° when retrograde — the
# engine does not carry retrograde flags, so the direct-motion orbs are used.
_COMBUST_ORB = {"Moon": 12.0, "Mars": 17.0, "Mercury": 14.0,
                "Jupiter": 11.0, "Venus": 10.0, "Saturn": 15.0}

_GANDANTA_ZONE = {
    "Cancer": (26.67, 30), "Scorpio": (26.67, 30), "Pisces": (26.67, 30),
    "Aries":  (0, 3.33),   "Leo":     (0, 3.33),   "Sagittarius": (0, 3.33),
}

def _deg_in_sign_val(pos_str) -> float:
    try:
        parts = str(pos_str).replace("'","").split("°")
        deg = float(parts[0].strip())
        mins = float(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
        return deg + mins/60
    except Exception:
        return 0.0

def compute_afflictions(planets:Dict) -> Dict:
    """Detect the classical affliction types from computed planet data.
    Single source of truth (combustion, debilitation, retrograde, gandanta,
    papakartari, graha yuddha)."""
    aff: Dict = {}
    sun_sign = planets.get("Sun", {}).get("sign", "")
    sun_deg  = _deg_in_sign_val(planets.get("Sun", {}).get("pos", "0"))
    p_deg   = {p: _deg_in_sign_val(d.get("pos","0")) for p,d in planets.items() if p!="Ascendant"}
    p_house = {p: d.get("house", 0) for p,d in planets.items() if p!="Ascendant"}

    for pname, pdata in planets.items():
        if pname in ("Ascendant","Sun"): continue
        issues = []
        orb = _COMBUST_ORB.get(pname)
        sun_lon = planets.get("Sun", {}).get("lon")
        if orb and sun_lon is not None and pdata.get("lon") is not None:
            d_sun = abs((pdata["lon"] - sun_lon + 180) % 360 - 180)
            if d_sun < orb:
                issues.append(f"combust/Asta ({d_sun:.1f}° from Sun, orb {orb:g}°)")
        elif orb and pdata.get("sign") == sun_sign:   # fallback without lon
            diff = abs(p_deg.get(pname, 0) - sun_deg)
            if diff < orb:
                issues.append(f"combust/Asta ({diff:.1f}° from Sun, orb {orb:g}°)")
        if "Debil" in pdata.get("dignity",""):
            issues.append("debilitated — check for Neecha Bhanga")
        if pdata.get("retrograde") or "R" in str(pdata.get("pos","")):
            issues.append("retrograde")
        sign = pdata.get("sign",""); deg = p_deg.get(pname, 0)
        gand = False
        if sign in _GANDANTA_ZONE:
            lo, hi = _GANDANTA_ZONE[sign]
            if lo <= deg <= hi:
                gand = True
                issues.append(f"Gandanta ({deg:.1f}° in {sign})")
        if not gand and (deg < 1.0 or deg > 29.0):
            edge = deg if deg < 1.0 else 30.0 - deg
            issues.append(f"Rashi Sandhi ({deg:.1f}° in {sign}, {edge:.1f}° from sign edge)")
        if issues:
            aff[pname] = issues

    # Papakartari: planet hemmed between malefics in adjacent houses
    for pname in planets:
        if pname == "Ascendant": continue
        h = p_house.get(pname, 0)
        if h == 0: continue
        prev_h, next_h = ((h-2) % 12) + 1, (h % 12) + 1
        prev_mal = [p for p,ph in p_house.items() if ph == prev_h and p in _MALEFICS]
        next_mal = [p for p,ph in p_house.items() if ph == next_h and p in _MALEFICS]
        if prev_mal and next_mal:
            aff.setdefault(pname, []).append(
                f"Papakartari (between {prev_mal[0]} H{prev_h} and {next_mal[0]} H{next_h})")

    # Graha Yuddha: two non-luminary/non-node planets within 1° in same sign
    war = [p for p in planets if p not in ("Sun","Moon","Rahu","Ketu","Ascendant")]
    for i, p1 in enumerate(war):
        for p2 in war[i+1:]:
            l1, l2 = planets[p1].get("lon"), planets[p2].get("lon")
            if l1 is not None and l2 is not None:
                diff = abs((l1 - l2 + 180) % 360 - 180)
                if diff < 1.0:
                    aff.setdefault(p1, []).append(f"Graha Yuddha with {p2} ({diff:.2f}°)")
                    aff.setdefault(p2, []).append(f"Graha Yuddha with {p1} ({diff:.2f}°)")

    # Nodal affliction (Grahaṇa-Yuti): a graha tightly conjunct Rahu or Ketu is
    # "grasped" by the node. Classically central in Prāśna (an afflicted Lagneśa
    # conjunct Ketu shows severance/negation/hidden factors) as well as in Janma
    # charts. Includes Sun and Moon (eclipse axis). Orb 8°, <3° flagged as tight.
    for node in ("Rahu", "Ketu"):
        n_lon = planets.get(node, {}).get("lon")
        if n_lon is None:
            continue
        for pname, pdata in planets.items():
            if pname in ("Ascendant", "Rahu", "Ketu"):
                continue
            l = pdata.get("lon")
            if l is None:
                continue
            d = abs((l - n_lon + 180) % 360 - 180)
            if d < 8.0:
                tight = ", very tight" if d < 3.0 else ""
                aff.setdefault(pname, []).append(
                    f"conjunct {node} ({d:.1f}°{tight}) — nodal affliction/Grahana")

    # Lagna in Gandanta / Rashi Sandhi (classically significant for the chart)
    asc = planets.get("Ascendant")
    if asc:
        a_sign = asc.get("sign",""); a_deg = _deg_in_sign_val(asc.get("pos","0"))
        a_iss = []
        a_gand = False
        if a_sign in _GANDANTA_ZONE:
            lo, hi = _GANDANTA_ZONE[a_sign]
            if lo <= a_deg <= hi:
                a_gand = True
                a_iss.append(f"Gandanta ({a_deg:.1f}° in {a_sign})")
        if not a_gand and (a_deg < 1.0 or a_deg > 29.0):
            edge = a_deg if a_deg < 1.0 else 30.0 - a_deg
            a_iss.append(f"Rashi Sandhi ({a_deg:.1f}° in {a_sign}, {edge:.1f}° from sign edge)")
        if a_iss:
            aff["Ascendant"] = a_iss
    return aff


# ══════════════════════════════════════════════════════════════════════════════
# ASHTAKAVARGA
# ══════════════════════════════════════════════════════════════════════════════

def compute_ashtakavarga(natal_signs:Dict[str,int]) -> Dict[str,List[int]]:
    """Bhinnashtakavarga for 7 planets + Sarvashtakavarga."""
    result: Dict[str,List[int]] = {}
    for planet in _AKV_PLANETS:
        bindus = [0]*12
        for sign in range(12):
            for contributor, benefic in _AKV[planet].items():
                c_sign = natal_signs.get("Ascendant" if contributor=="Lagna" else contributor, 0)
                if (sign - c_sign) % 12 + 1 in benefic:
                    bindus[sign] += 1
        result[planet] = bindus
    result["Sarva"] = [sum(result[p][s] for p in _AKV_PLANETS) for s in range(12)]
    return result


# ══════════════════════════════════════════════════════════════════════════════
# VIMSHOTTARI DASHA
# ══════════════════════════════════════════════════════════════════════════════

def build_dashas(moon_sid:float, birth_dt:datetime) -> Dict:
    """9-period Mahadasha tree with Antardashas and Pratyantardashas."""
    span=360/27; nak_idx=int(moon_sid/span)%27
    lord=NAKSHATRAS[nak_idx][1]; frac_done=(moon_sid%span)/span
    start_idx=DASHA_ORDER.index(lord); today=datetime.now()
    cur_maha=cur_antar=cur_pad=None
    mahas=[]; maha_curr=birth_dt

    for i in range(9):
        maha=DASHA_ORDER[(start_idx+i)%9]; full_yrs=DASHA_YEARS[maha]
        maha_yrs=full_yrs*(1-frac_done if i==0 else 1.0)
        maha_end=maha_curr+timedelta(days=maha_yrs*365.25)
        abs_start=maha_curr-timedelta(days=frac_done*full_yrs*365.25) if i==0 else maha_curr
        maha_i=DASHA_ORDER.index(maha); ad_cur=abs_start; ads=[]

        for j in range(9):
            antar=DASHA_ORDER[(maha_i+j)%9]
            ad_yrs=full_yrs*DASHA_YEARS[antar]/DASHA_TOTAL
            ad_end=ad_cur+timedelta(days=ad_yrs*365.25)
            if ad_end<=birth_dt: ad_cur=ad_end; continue
            ad_start=max(birth_dt,ad_cur)
            antar_i=DASHA_ORDER.index(antar); pad_cur=ad_cur; pads=[]

            for k in range(9):
                prat=DASHA_ORDER[(antar_i+k)%9]
                pad_yrs=full_yrs*DASHA_YEARS[antar]*DASHA_YEARS[prat]/(DASHA_TOTAL**2)
                pad_end=pad_cur+timedelta(days=pad_yrs*365.25)
                pad_start=max(ad_start,pad_cur)
                if pad_start<pad_end:
                    active=pad_start<=today<pad_end
                    pads.append({"planet":prat,"start":pad_start,"end":pad_end,
                                 "years":round(pad_yrs,4),"active":active})
                    if active: cur_pad=prat
                pad_cur=pad_end

            active=ad_start<=today<ad_end
            ads.append({"planet":antar,"start":ad_start,"end":ad_end,
                        "years":round(ad_yrs,4),"active":active,"pratyantardashas":pads})
            if active: cur_antar=antar
            ad_cur=ad_end

        active=maha_curr<=today<maha_end
        mahas.append({"planet":maha,"start":maha_curr,"end":maha_end,
                      "years":round(maha_yrs,2),"active":active,"antardashas":ads})
        if active: cur_maha=maha
        maha_curr=maha_end

    return {"mahadashas":mahas,"current":{"maha":cur_maha,"antar":cur_antar,"pratyantar":cur_pad}}


# ══════════════════════════════════════════════════════════════════════════════
# VARSHAPHALA  (Solar Return / Annual Horoscope)
# ══════════════════════════════════════════════════════════════════════════════

def _sun_sid(jd:float) -> float:
    """Sidereal (Lahiri) Sun for the solar-return search.

    MUST use the same tier as the natal chart: the natal Sun longitude comes
    from Swiss Ephemeris, so the zero-crossing has to be solved against the
    SWE Sun as well. Mixing SWE (natal) with Meeus+polynomial ayanamsha (here)
    shifted the return moment by minutes — enough to move the Varshaphala
    Lagna by several degrees. Meeus remains the Tier-3 fallback only.
    """
    if _SWE:
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)   # always re-set before calc
        return _swe_planet("Sun", jd)
    return norm(_sun(jd) - _ayanamsha(jd))

def find_solar_return_jd(natal_sun_sid:float, birth_month:int,
                          birth_day:int, target_year:int) -> float:
    centre = julian_day(target_year, birth_month, birth_day, 12)
    a, b   = centre - 40, centre + 40
    def diff(jd):
        d = _sun_sid(jd) - natal_sun_sid
        if d > 180: d -= 360
        if d < -180: d += 360
        return d
    for _ in range(60):
        mid = (a+b)/2
        if diff(a)*diff(mid) <= 0: b = mid
        else: a = mid
        if abs(b-a) < 1e-8: break
    return (a+b)/2

def compute_varshaphala(birth_year:int, birth_month:int, birth_day:int,
                        natal_sun_sid:float, natal_lagna_si:int,
                        lat:float, lon:float, target_year:int) -> Dict:
    jd_sr = find_solar_return_jd(natal_sun_sid, birth_month, birth_day, target_year)
    lons_sr, _, _ = compute_positions(jd_sr, lat, lon)

    planets_sr = {name: _planet_record(name, lon) for name,lon in lons_sr.items()}

    asc_si    = planets_sr["Ascendant"]["sign_idx"]
    asc_sn    = SIGNS[asc_si]
    lagna_lord = SIGN_LORDS[asc_sn]

    age      = target_year - birth_year
    mun_si   = (natal_lagna_si + age) % 12

    wd_lord  = _WEEKDAY_LORDS[int(jd_sr+1.5)%7]
    hl_start = _HORA_ORDER.index(_WEEKDAY_LORDS[int(jd_sr+1.5)%7])
    hr_lord  = _HORA_ORDER[(hl_start + int((jd_sr+0.5)%1*24)) % 7]
    candidates = [wd_lord, hr_lord, lagna_lord]
    varsha_pati = max(set(candidates), key=candidates.count)

    return {
        "year_number":   age,
        "target_year":   target_year,
        "jd_return":     round(jd_sr,5),
        "return_dt_utc": _jd_to_dt_str(jd_sr),
        "planets":       planets_sr,
        "lagna":         asc_sn,
        "lagna_pos":     planets_sr["Ascendant"]["pos"],
        "lagna_si":      asc_si,
        "lagna_lord":    lagna_lord,
        "muntha_sign":   SIGNS[mun_si],
        "muntha_si":     mun_si,
        "muntha_lord":   SIGN_LORDS[SIGNS[mun_si]],
        "varsha_pati":   varsha_pati,
        "weekday_lord":  wd_lord,
        "hora_lord":     hr_lord,
        "ashtakavarga":  compute_ashtakavarga(
            {p: planets_sr[p]["sign_idx"] for p in planets_sr}),
    }


# ══════════════════════════════════════════════════════════════════════════════
# JAIMINI  (Chara Karakas - 8-karaka scheme including Rahu)
#
# Each graha is ranked by the degrees it has traversed within its sign (0–30°),
# highest first. Rahu is reckoned in REVERSE (30° − deg) because it moves
# retrograde - this is what "taking Rahu into account" means and is the
# difference between the 7-karaka (no Rahu) and 8-karaka schemes.
#   1 Atmakaraka (AK)   soul / self          highest degree
#   2 Amatyakaraka(AmK) career / advisor
#   3 Bhratrikaraka(BK) siblings
#   4 Matrikaraka (MK)  mother
#   5 Pitrikaraka (PiK) father
#   6 Putrakaraka (PuK) children
#   7 Gnatikaraka (GK)  cousins / obstacles
#   8 Darakaraka (DK)   spouse               lowest degree
# ══════════════════════════════════════════════════════════════════════════════

CHARA_KARAKAS_8 = ["Atmakaraka", "Amatyakaraka", "Bhratrikaraka", "Matrikaraka",
                   "Pitrikaraka", "Putrakaraka", "Gnatikaraka", "Darakaraka"]
CHARA_ABR = {"Atmakaraka": "AK", "Amatyakaraka": "AmK", "Bhratrikaraka": "BK",
             "Matrikaraka": "MK", "Pitrikaraka": "PiK", "Putrakaraka": "PuK",
             "Gnatikaraka": "GK", "Darakaraka": "DK"}
CHARA_MEANING = {"Atmakaraka": "soul / self", "Amatyakaraka": "career / advisor",
                 "Bhratrikaraka": "siblings", "Matrikaraka": "mother",
                 "Pitrikaraka": "father", "Putrakaraka": "children",
                 "Gnatikaraka": "cousins / obstacles", "Darakaraka": "spouse"}


def _arudha(house_si: int, lord_si: int) -> int:
    """Arudha pada of a sign: count house→lord, same count from lord; 1st/7th → 10th."""
    al = (2 * lord_si - house_si) % 12
    if al == house_si or al == (house_si + 6) % 12:
        al = (al + 9) % 12   # 10th from the computed pada
    return al


def compute_jaimini(lons: Dict[str, float], lagna_si: int) -> Dict:
    """Chara Karakas (8, including Rahu), Karakamsha, and Arudha Lagna."""
    grahas = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu"]
    scored = []
    for g in grahas:
        deg = lons[g] % 30
        eff = (30 - deg) if g == "Rahu" else deg     # Rahu reckoned in reverse
        scored.append((g, eff, deg))
    scored.sort(key=lambda x: x[1], reverse=True)

    karakas, karaka_of = {}, {}
    for i, (g, eff, deg) in enumerate(scored):
        role = CHARA_KARAKAS_8[i]
        si, sn, _ = sign_of(lons[g])
        karakas[role] = {"planet": g, "sign": sn, "sign_idx": si,
                         "deg_in_sign": round(deg, 4), "effective": round(eff, 4),
                         "reverse": g == "Rahu"}
        karaka_of[g] = role

    ak = karakas["Atmakaraka"]["planet"]
    dk = karakas["Darakaraka"]["planet"]
    karakamsha_si = navamsa_sign(lons[ak])              # AK's navamsa sign

    lagna_lord = SIGN_LORDS[SIGNS[lagna_si]]
    lord_si = sign_of(lons[lagna_lord])[0]
    al_si = _arudha(lagna_si, lord_si)

    # Upapada Lagna (UL) - arudha pada of the 12th house
    twelfth_si = (lagna_si - 1) % 12
    twelfth_lord = SIGN_LORDS[SIGNS[twelfth_si]]
    ul_si = _arudha(twelfth_si, sign_of(lons[twelfth_lord])[0])

    return {
        "order": CHARA_KARAKAS_8,
        "karakas": karakas,
        "karaka_of": karaka_of,
        "atmakaraka": ak,
        "darakaraka": dk,
        "karakamsha_si": karakamsha_si,
        "karakamsha": SIGNS[karakamsha_si],
        "karakamsha_lord": SIGN_LORDS[SIGNS[karakamsha_si]],
        "arudha_lagna_si": al_si,
        "arudha_lagna": SIGNS[al_si],
        "arudha_lagna_lord": SIGN_LORDS[SIGNS[al_si]],
        "upapada_lagna_si": ul_si,
        "upapada_lagna": SIGNS[ul_si],
        "upapada_lagna_lord": SIGN_LORDS[SIGNS[ul_si]],
        "lagna_lord": lagna_lord,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CHARA DASHA  (Jaimini sign-based dasha - K.N. Rao method)
#
#  • Start at the Lagna sign at birth.
#  • Sequence direction: forward (zodiacal) if Lagna is an ODD sign
#    (Aries, Gemini, Leo, Libra, Sagittarius, Aquarius), else backward.
#  • Duration of a sign = (count from the sign to its lord) − 1 year, where the
#    count direction is forward for odd signs and backward for even signs; a
#    count of 1 (lord in the sign) gives 12 years.
#  • Dual-ruled signs: Scorpio (Mars/Ketu), Aquarius (Saturn/Rahu) - the longer
#    of the two co-lord periods is used (a common convention; schools vary).
#  • Antardashas: each = mahadasha/12, starting from the mahadasha sign and
#    moving in that sign's own direction (its odd/even nature).
# ══════════════════════════════════════════════════════════════════════════════

def _chara_odd(si: int) -> bool:
    """Odd sign? Aries, Gemini, Leo, Libra, Sagittarius, Aquarius (0-based even index)."""
    return si % 2 == 0

def _chara_count(from_si: int, to_si: int, direct: bool) -> int:
    return ((to_si - from_si) % 12 + 1) if direct else ((from_si - to_si) % 12 + 1)

# ── Jaimini sign-strength helpers (Chara Bala) ────────────────────────────────
_MOVABLE = {0, 3, 6, 9}    # Aries, Cancer, Libra, Capricorn
_FIXED   = {1, 4, 7, 10}   # Taurus, Leo, Scorpio, Aquarius
_DUAL    = {2, 5, 8, 11}   # Gemini, Virgo, Sagittarius, Pisces
_BALA_GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

def _rasi_aspects(si: int) -> List[int]:
    """Signs aspected by the sign at si (Jaimini Rasi Drishti)."""
    if si in _MOVABLE:
        nxt = (si + 1) % 12
        return [s for s in _FIXED if s != nxt]      # movable → fixed, minus the next sign
    if si in _FIXED:
        prev = (si - 1) % 12
        return [s for s in _MOVABLE if s != prev]   # fixed → movable, minus the previous sign
    return [s for s in _DUAL if s != si]            # dual → the other dual signs

def _conjunct_count(ps: Dict[str, int], p: str) -> int:
    return sum(1 for q in _BALA_GRAHAS if q != p and ps.get(q) == ps[p])

def _aspect_count(ps: Dict[str, int], p: str) -> int:
    si = ps[p]
    return sum(1 for q in _BALA_GRAHAS if q != p and si in _rasi_aspects(ps[q]))

def _dignity_rank(p: str, ps: Dict[str, int], lons: Dict[str, float]) -> int:
    d = dignity_of(p, ps[p], lons[p] % 30)
    if d.startswith("Exalted"):     return 3
    if d == "Moolatrikona":         return 2
    if d == "Own Sign":             return 1
    if d == "Debilitated":          return -1
    return 0

def stronger_colord(sign_si: int, a: str, b: str,
                    ps: Dict[str, int], lons: Dict[str, float]) -> Tuple[str, str]:
    """Pick the stronger co-lord by Jaimini criteria, in order. Returns (lord, reason)."""
    in_a, in_b = ps[a] == sign_si, ps[b] == sign_si
    if in_a != in_b:
        return (a, "in the sign") if in_a else (b, "in the sign")
    ca, cb = _conjunct_count(ps, a), _conjunct_count(ps, b)
    if ca != cb:
        return (a if ca > cb else b, "more conjunctions")
    aa, ab = _aspect_count(ps, a), _aspect_count(ps, b)
    if aa != ab:
        return (a if aa > ab else b, "more aspects (rasi drishti)")
    da, db = _dignity_rank(a, ps, lons), _dignity_rank(b, ps, lons)
    if da != db:
        return (a if da > db else b, "dignity")
    ga, gb = lons[a] % 30, lons[b] % 30
    if abs(ga - gb) > 1e-9:
        return (a if ga > gb else b, "higher degree")
    return (b, "tie → node")   # deterministic final fallback

def _chara_years(sign_si: int, ps: Dict[str, int],
                 lons: Dict[str, float]) -> Tuple[int, str, str]:
    """Return (years, lord_used, reason). reason is '' for single-lord signs."""
    direct = _chara_odd(sign_si)
    sn = SIGNS[sign_si]
    if sn == "Scorpio":
        lord, reason = stronger_colord(sign_si, "Mars", "Ketu", ps, lons)
    elif sn == "Aquarius":
        lord, reason = stronger_colord(sign_si, "Saturn", "Rahu", ps, lons)
    else:
        lord, reason = SIGN_LORDS[sn], ""
    y = _chara_count(sign_si, ps[lord], direct) - 1
    return (12 if y == 0 else y), lord, reason

def _chara_antardashas(maha_si: int, maha_years: float, start_dt: datetime,
                       today: datetime) -> List[Dict]:
    direct = _chara_odd(maha_si)
    sub = maha_years / 12.0
    out, cur = [], start_dt
    for i in range(12):
        si = (maha_si + i) % 12 if direct else (maha_si - i) % 12
        end = cur + timedelta(days=sub * 365.25)
        out.append({"sign": SIGNS[si], "sign_idx": si, "start": cur, "end": end,
                    "years": round(sub, 3), "active": cur <= today < end})
        cur = end
    return out

def build_chara_dasha(planet_signs: Dict[str, int], lons: Dict[str, float],
                      lagna_si: int, birth_dt: datetime, span_years: float = 120.0) -> Dict:
    direct = _chara_odd(lagna_si)
    order = [((lagna_si + i) % 12 if direct else (lagna_si - i) % 12) for i in range(12)]

    durations, colords = {}, {}
    for si in range(12):
        yrs, lord, reason = _chara_years(si, planet_signs, lons)
        durations[si] = yrs
        if SIGNS[si] in ("Scorpio", "Aquarius"):
            colords[SIGNS[si]] = {"lord": lord, "reason": reason}

    today = datetime.now()
    mahas, cur, total, idx, current = [], birth_dt, 0.0, 0, None
    while total < span_years:
        si = order[idx % 12]
        yrs = durations[si]
        end = cur + timedelta(days=yrs * 365.25)
        active = cur <= today < end
        mahas.append({"sign": SIGNS[si], "sign_idx": si, "start": cur, "end": end,
                      "years": yrs, "active": active,
                      "antardashas": _chara_antardashas(si, yrs, cur, today)})
        if active:
            current = SIGNS[si]
        cur = end; total += yrs; idx += 1

    return {"mahadashas": mahas, "current": current,
            "direction": "direct (zodiacal)" if direct else "reverse",
            "durations": {SIGNS[si]: durations[si] for si in range(12)},
            "colords": colords}


# ══════════════════════════════════════════════════════════════════════════════
# GEOCODING  (Nominatim → IANA timezone → zoneinfo for historical DST)
# ══════════════════════════════════════════════════════════════════════════════

_UA = {"User-Agent": "VedicAstroCalc/3.0 (birth-chart app; contact via app)",
       "Accept": "application/json"}

def _http_get(url:str) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
    except Exception: return None

def _open_meteo_geo(name:str) -> Optional[Dict]:
    """Open-Meteo geocoder - free, no key, returns coordinates AND an IANA timezone."""
    d = _http_get("https://geocoding-api.open-meteo.com/v1/search"
                  f"?name={urllib.parse.quote_plus(name)}&count=1&language=en&format=json")
    if not d or not d.get("results"):
        return None
    r = d["results"][0]
    label = []
    for x in (r.get("name"), r.get("admin1"), r.get("country")):
        if x and x not in label:
            label.append(x)
    return {"lat": float(r["latitude"]), "lon": float(r["longitude"]),
            "label": ", ".join(label), "iana": r.get("timezone")}

def _nominatim_geo(query:str) -> Optional[Dict]:
    time.sleep(1)   # Nominatim policy: ≤1 request/second
    data = _http_get("https://nominatim.openstreetmap.org/search"
                     f"?q={urllib.parse.quote_plus(query)}&format=json&limit=3&addressdetails=1")
    if not data:
        return None
    prefer = {"city","town","village","suburb","municipality","county","state","country","administrative"}
    results = [r for r in data if r.get("type","") in prefer] or data
    if not results:
        return None
    r = results[0]; addr = r.get("address", {})
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county") or query
    return {"lat": float(r["lat"]), "lon": float(r["lon"]),
            "label": f"{city}, {addr.get('country','')}".rstrip(", "), "iana": None}

@lru_cache(maxsize=512)
def geocode(query:str) -> Optional[Dict]:
    """Resolve a place name. Open-Meteo first (reliable + gives a timezone),
    Nominatim as a fallback. Cached so the same place isn't fetched twice."""
    names = [query.strip()]
    head = query.split(",")[0].strip()
    if head and head != query.strip():
        names.append(head)
    for nm in names:
        g = _open_meteo_geo(nm)
        if g:
            return g
    return _nominatim_geo(query)

def iana_tz(lat:float, lon:float) -> Optional[str]:
    d = _http_get(f"https://timeapi.io/api/timezone/coordinate?latitude={lat:.6f}&longitude={lon:.6f}")
    if not d:
        return None
    if isinstance(d, list):
        d = d[0] if d else None
    if not isinstance(d, dict):
        return None
    return d.get("timeZone")

def hist_offset(iana:str, year:int, month:int, day:int, hour:int, minute:int) -> Optional[float]:
    if not _ZONEINFO: return None
    try:
        dt = datetime(year,month,day,hour,minute,tzinfo=ZoneInfo(iana))
        return dt.utcoffset().total_seconds()/3600
    except (ZoneInfoNotFoundError, Exception): return None

def resolve_location(city:str, year:int, month:int, day:int,
                     hour:int, minute:int) -> Optional[Dict]:
    """Geocode a place + resolve the UTC offset. Always returns a usable offset when
    the place is found: IANA-based if possible, else estimated from longitude."""
    geo = geocode(city)
    if not geo:
        return None
    iana = geo.get("iana") or iana_tz(geo["lat"], geo["lon"])
    offset = hist_offset(iana, year, month, day, hour, minute) if iana else None
    approx = False
    if offset is None:                       # last-resort: estimate from longitude
        offset = round(geo["lon"] / 15.0)
        approx = True
        if not iana:
            iana = f"~UTC{offset:+d}"
    h, m = int(abs(offset)), int(round((abs(offset) % 1) * 60))
    off_str = f"UTC{'+' if offset >= 0 else '-'}{h:02d}:{m:02d}" + (" (est.)" if approx else "")
    return {**geo, "iana": iana, "offset": offset, "offset_str": off_str, "approx": approx}


# ══════════════════════════════════════════════════════════════════════════════
# PANCHANGA (five limbs at the birth moment)
# ══════════════════════════════════════════════════════════════════════════════
TITHI_NAMES = ["Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
               "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dvadashi",
               "Trayodashi", "Chaturdashi", "Purnima"]
YOGA_NAMES = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
              "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
              "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
              "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]
KARANA_MOVABLE = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
VARA = [("Sunday", "Sun"), ("Monday", "Moon"), ("Tuesday", "Mars"), ("Wednesday", "Mercury"),
        ("Thursday", "Jupiter"), ("Friday", "Venus"), ("Saturday", "Saturn")]


def compute_panchang(sun_lon: float, moon_lon: float, weekday_idx: int,
                     moon_nak: str, moon_nak_lord: str) -> Dict:
    """Five limbs from sidereal Sun/Moon longitudes. weekday_idx: 0=Sun … 6=Sat."""
    diff = (moon_lon - sun_lon) % 360
    ti = int(diff // 12)                      # 0..29 across the lunar month
    paksha = "Shukla" if ti < 15 else "Krishna"
    tname = TITHI_NAMES[ti % 15]
    if ti % 15 == 14:
        tname = "Purnima" if paksha == "Shukla" else "Amavasya"
    yi = int(((sun_lon + moon_lon) % 360) // (360 / 27))
    ki = int(diff // 6)                        # 0..59 half-tithis
    if ki == 0:    kname = "Kimstughna"
    elif ki == 57: kname = "Shakuni"
    elif ki == 58: kname = "Chatushpada"
    elif ki == 59: kname = "Naga"
    else:          kname = KARANA_MOVABLE[(ki - 1) % 7]
    vname, vlord = VARA[weekday_idx % 7]
    return {
        "tithi": f"{paksha} {tname}", "tithi_num": ti + 1, "paksha": paksha,
        "tithi_pct": round((diff % 12) / 12 * 100, 1),
        "vara": vname, "vara_lord": vlord,
        "nakshatra": moon_nak, "nakshatra_lord": moon_nak_lord,
        "yoga": YOGA_NAMES[yi % 27], "karana": kname,
    }


# ══════════════════════════════════════════════════════════════════════════════
# YOGAS (combinations) - natal D1
# ══════════════════════════════════════════════════════════════════════════════
# Graha drishti (sign-offset a planet aspects; 0-indexed). All aspect the 7th (6);
# Mars also 4th/8th, Jupiter 5th/9th, Saturn 3rd/10th.
_ASPECT_OFF = {"Mars": {3, 6, 7}, "Jupiter": {4, 6, 8}, "Saturn": {2, 6, 9}}
_TARA   = ["Mars", "Mercury", "Jupiter", "Venus", "Saturn"]   # non-luminary, non-node
_BENEFS = ["Mercury", "Jupiter", "Venus"]
_PMP    = {"Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa",
           "Venus": "Malavya", "Saturn": "Sasa"}
_GRAHAS_7 = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
_ASPECTORS = _GRAHAS_7 + ["Rahu"]
_RAHU_ASPECT = {4, 6, 8}            # Rahu casts the 5th, 7th and 9th aspect (Ketu excluded)


def graha_aspects_by_sign(planets: Dict) -> Dict[int, List[str]]:
    """{sign_idx: [planets casting a graha-drishti aspect onto that sign]}.
    7th aspect for all; Mars also 4/8, Jupiter 5/9, Saturn 3/10; Rahu 5/7/9. Ketu excluded."""
    si = {p: planets[p]["sign_idx"] for p in _ASPECTORS if p in planets}
    out: Dict[int, List[str]] = {i: [] for i in range(12)}
    for p in _ASPECTORS:
        if p not in si:
            continue
        offs = _RAHU_ASPECT if p == "Rahu" else _ASPECT_OFF.get(p, {6})
        for o in offs:
            out[(si[p] + o) % 12].append(p)
    return out


def compute_yogas(planets: Dict, lagna_idx: int) -> List[Dict]:
    """Detect a broad, well-defined set of natal yogas. Conventions vary by school;
    this uses common Parashari rules (whole-sign houses, graha drishti)."""
    si = {p: planets[p]["sign_idx"] for p in PLANET_ORDER}
    hs = {p: planets[p]["house"]    for p in PLANET_ORDER}    # 1..12 from Lagna

    def lord_of(h):       return SIGN_LORDS[SIGNS[(lagna_idx + h - 1) % 12]]
    def rules(p):         return [h for h in range(1, 13) if lord_of(h) == p]
    def aspoff(p):        return _ASPECT_OFF.get(p, {6})
    def aspects(p, q):    return ((si[q] - si[p]) % 12) in aspoff(p)
    def conj(p, q):       return si[p] == si[q]
    def exch(p, q):       return si[p] in OWN_SIGNS.get(q, []) and si[q] in OWN_SIGNS.get(p, [])
    def dist(p, anchor):  return (si[p] - si[anchor]) % 12 + 1     # 1..12 from a planet

    def link(a, b):
        if a == b:               return None
        if conj(a, b):           return "conjunction"
        if exch(a, b):           return "exchange (parivartana)"
        if aspects(a, b) and aspects(b, a): return "mutual aspect"
        return None

    Y: List[Dict] = []
    def add(name, group, plist, detail): Y.append(
        {"name": name, "group": group, "planets": list(plist), "detail": detail})

    # ── Pancha Mahapurusha (kendra from Lagna OR Moon - common convention) ───────
    moon_si = planets["Moon"]["sign_idx"]
    for p, nm in _PMP.items():
        exa = EXALT_SIGN.get(p) == si[p]
        own = si[p] in OWN_SIGNS.get(p, [])
        if not (exa or own):
            continue
        hL = hs[p]
        hM = (si[p] - moon_si) % 12 + 1
        refs = ([("Lagna")] if hL in (1, 4, 7, 10) else []) + \
               ([("Moon")] if hM in (1, 4, 7, 10) else [])
        if refs:
            add(f"{nm} Yoga", "Pancha Mahapurusha", [p],
                f"{p} {'exalted' if exa else 'in own sign'}, in a kendra from the "
                f"{' & '.join(refs)} (house {hL} from Lagna, house {hM} from Moon).")

    # ── Raja yogas ──────────────────────────────────────────────────────────────
    for p in PLANET_ORDER:
        rl = rules(p)
        if any(h in (4, 7, 10) for h in rl) and any(h in (5, 9) for h in rl):
            add(f"Yogakaraka ({p})", "Raja", [p],
                f"{p} rules both a kendra and a trikona (houses {', '.join(map(str, rl))}).")
    kendra_l  = {lord_of(h) for h in (1, 4, 7, 10)}
    trikona_l = {lord_of(h) for h in (1, 5, 9)}
    seen = set()
    # Dharma-Karmadhipati - the 9th (dharma) and 10th (karma) lords linked (top Raja yoga)
    L9, L10 = lord_of(9), lord_of(10)
    if L9 == L10:
        add("Dharma-Karmadhipati Yoga", "Raja", [L9],
            f"{L9} rules both the 9th and 10th - dharma and karma combined.")
    else:
        rel = link(L9, L10)
        if rel:
            seen.add(tuple(sorted((L9, L10))))
            add("Dharma-Karmadhipati Yoga", "Raja", [L9, L10],
                f"9th lord {L9} and 10th lord {L10} linked by {rel} - a powerful Raja yoga.")
    for a in sorted(kendra_l):
        for b in sorted(trikona_l):
            if a == b or tuple(sorted((a, b))) in seen:
                continue
            rel = link(a, b)
            if rel:
                seen.add(tuple(sorted((a, b))))
                add("Raja Yoga", "Raja", [a, b],
                    f"Kendra lord {a} and trikona lord {b} linked by {rel}.")

    # ── Dhana (wealth) yogas - links among 2/5/9/11 lords ───────────────────────
    wl = [(h, lord_of(h)) for h in (2, 5, 9, 11)]
    dseen = set()
    for i in range(len(wl)):
        for j in range(i + 1, len(wl)):
            (h1, a), (h2, b) = wl[i], wl[j]
            if a == b:
                if (a, h1, h2) not in dseen:
                    dseen.add((a, h1, h2))
                    add("Dhana Yoga", "Dhana", [a], f"{a} rules wealth houses {h1} & {h2}.")
                continue
            rel = link(a, b)
            if rel and tuple(sorted((a, b))) not in dseen:
                dseen.add(tuple(sorted((a, b))))
                add("Dhana Yoga", "Dhana", [a, b],
                    f"Lords of houses {h1} & {h2} ({a}, {b}) linked by {rel}.")

    # ── Vipareeta Raja yogas - dusthana lords in dusthanas ──────────────────────
    for h, nm in ((6, "Harsha"), (8, "Sarala"), (12, "Vimala")):
        L = lord_of(h)
        if hs[L] in (6, 8, 12):
            add(f"Vipareeta Raja Yoga · {nm}", "Vipareeta Raja", [L],
                f"{h}th lord {L} placed in a dusthana (house {hs[L]}).")

    # ── Sun yogas ───────────────────────────────────────────────────────────────
    veshi = [p for p in _TARA if dist(p, "Sun") == 2]
    vasi  = [p for p in _TARA if dist(p, "Sun") == 12]
    if veshi and vasi:
        add("Ubhayachari Yoga", "Sun", veshi + vasi, "Planets in both the 2nd and 12th from the Sun.")
    else:
        if veshi: add("Veshi Yoga", "Sun", veshi, "Planet(s) in the 2nd from the Sun.")
        if vasi:  add("Vasi Yoga",  "Sun", vasi,  "Planet(s) in the 12th from the Sun.")
    if conj("Sun", "Mercury"):
        add("Budha-Aditya Yoga", "Sun", ["Sun", "Mercury"],
            "Sun and Mercury conjunct - intelligence and skill.")

    # ── Moon yogas ──────────────────────────────────────────────────────────────
    m2  = [p for p in _TARA if dist(p, "Moon") == 2]
    m12 = [p for p in _TARA if dist(p, "Moon") == 12]
    mcj = [p for p in _TARA if conj(p, "Moon")]
    if m2 and m12:
        add("Durudhara Yoga", "Moon", m2 + m12, "Planets flank the Moon (2nd and 12th).")
    else:
        if m2:  add("Sunapha Yoga", "Moon", m2,  "Planet(s) in the 2nd from the Moon.")
        if m12: add("Anapha Yoga",  "Moon", m12, "Planet(s) in the 12th from the Moon.")
    if not m2 and not m12 and not mcj:
        add("Kemadruma Yoga", "Moon", ["Moon"],
            "No planets in the 2nd, 12th, or with the Moon - a challenging lunar yoga "
            "(often cancelled by planets in kendras from the Moon).")
    if dist("Jupiter", "Moon") in (1, 4, 7, 10):
        add("Gajakesari Yoga", "Moon", ["Moon", "Jupiter"],
            f"Jupiter in a kendra (house {dist('Jupiter','Moon')}) from the Moon.")
    if conj("Moon", "Mars"):
        add("Chandra-Mangala Yoga", "Moon", ["Moon", "Mars"], "Moon and Mars conjunct.")
    adhi = [p for p in _BENEFS if dist(p, "Moon") in (6, 7, 8)]
    if len(adhi) == len(_BENEFS):
        add("Adhi Yoga", "Moon", adhi,
            "All benefics (Mercury, Jupiter, Venus) in the 6th/7th/8th from the Moon.")

    # ── Other classics ──────────────────────────────────────────────────────────
    amala_l = [p for p in _BENEFS if hs[p] == 10]
    amala_m = [p for p in _BENEFS if dist(p, "Moon") == 10]
    if amala_l:
        add("Amala Yoga", "Other", amala_l, "Benefic in the 10th from the Lagna - lasting repute.")
    elif amala_m:
        add("Amala Yoga", "Other", amala_m, "Benefic in the 10th from the Moon.")
    for p in PLANET_ORDER:
        if DEBIL_SIGN.get(p) == si[p]:
            sl = SIGN_LORDS[SIGNS[si[p]]]
            if hs.get(sl) in (1, 4, 7, 10):
                add("Neecha Bhanga Raja Yoga", "Other", [p, sl],
                    f"{p} is debilitated, but its sign-lord {sl} sits in a kendra - "
                    "debilitation is cancelled.")

    # Lakshmi - 9th lord strong (own/exalted) in a kendra/trikona, with a strong Lagna lord
    def _strong(p):     return EXALT_SIGN.get(p) == si[p] or si[p] in OWN_SIGNS.get(p, [])
    def _well(p):       return hs[p] in (1, 4, 5, 7, 9, 10)
    L1 = lord_of(1)
    if L1 != L9 and _strong(L9) and _well(L9) and (_strong(L1) or _well(L1)):
        add("Lakshmi Yoga", "Dhana", [L1, L9],
            f"9th lord {L9} strong in a kendra/trikona (house {hs[L9]}) and Lagna lord "
            f"{L1} well-placed - wealth and grace.")

    # Vasumati - natural benefics in the upachaya houses (3, 6, 10, 11) from Lagna or Moon
    vas_l = [p for p in _BENEFS if hs[p] in (3, 6, 10, 11)]
    vas_m = [p for p in _BENEFS if dist(p, "Moon") in (3, 6, 10, 11)]
    if len(vas_l) >= 2:
        add("Vasumati Yoga", "Dhana", vas_l,
            "Benefics in the upachaya houses (3/6/10/11) from the Lagna - steady wealth.")
    elif len(vas_m) >= 2:
        add("Vasumati Yoga", "Dhana", vas_m,
            "Benefics in the upachaya houses (3/6/10/11) from the Moon - steady wealth.")

    # Malika (Mala) - the seven classical planets occupy seven consecutive houses
    _CLASSICAL = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    _MALIKA = {1: "Lagna", 2: "Dhana", 3: "Vikrama", 4: "Sukha", 5: "Putra", 6: "Shatru",
               7: "Kalatra", 8: "Randhra", 9: "Bhagya", 10: "Karma", 11: "Labha", 12: "Vyaya"}
    occ = {hs[p] for p in _CLASSICAL}
    if len(occ) == 7:
        for s in range(1, 13):
            run = {((s - 1 + k) % 12) + 1 for k in range(7)}
            if run == occ:
                end = ((s - 1 + 6) % 12) + 1
                add(f"Malika Yoga · {_MALIKA[s]}", "Other", _CLASSICAL,
                    f"All seven planets fall in seven consecutive houses (H{s}–H{end}) - "
                    "a 'garland' yoga.")
                break

    # ── Kahala / Chamara / Parvata / Saraswati ──────────────────────────────────
    KEND = (1, 4, 7, 10)
    L4 = lord_of(4)
    if L4 != L9 and (hs[L4] - hs[L9]) % 12 in (0, 3, 6, 9) and (_strong(L1) or _well(L1)):
        add("Kahala Yoga", "Raja", [L4, L9],
            f"4th lord {L4} and 9th lord {L9} in mutual kendras with a strong Lagna lord "
            f"{L1} - drive, courage and leadership.")
    if _strong(L1) and hs[L1] in KEND and aspects("Jupiter", L1):
        add("Chamara Yoga", "Raja", [L1, "Jupiter"],
            f"Lagna lord {L1} exalted/own in a kendra (house {hs[L1]}) and aspected by Jupiter "
            "- honour, eloquence and a long life.")
    ben_kend = [p for p in _BENEFS if hs[p] in KEND]
    if ben_kend and not any(hs[p] in (6, 8) for p in PLANET_ORDER):
        add("Parvata Yoga", "Raja", ben_kend,
            "Benefics in kendras with the 6th and 8th houses empty - fame, prosperity and "
            "a charitable nature.")
    _SARAS_H = (1, 2, 4, 5, 7, 9, 10)
    if (all(hs[p] in _SARAS_H for p in _BENEFS)
            and (_strong("Jupiter") or hs["Jupiter"] in (1, 4, 5, 7, 9, 10))):
        add("Saraswati Yoga", "Other", list(_BENEFS),
            "Mercury, Jupiter and Venus in kendras/trikonas/2nd with Jupiter strong - "
            "learning, arts, wisdom and eloquence.")

    return Y


# ══════════════════════════════════════════════════════════════════════════════
# MUHURTA (electional) - favourable days for an activity over a window
# ══════════════════════════════════════════════════════════════════════════════
def _sun_moon_sid(jd: float):
    """Sidereal Sun & Moon only - fast, network-free (for day-by-day scanning)."""
    if _SWE:
        return norm(_swe_planet("Sun", jd)), norm(_swe_planet("Moon", jd))
    ayan = _ayanamsha(jd)
    return norm(_sun(jd) - ayan), norm(_moon(jd) - ayan)


# Nakshatra nature groups (classical)
_NK_CHARA   = {"Punarvasu", "Swati", "Shravana", "Dhanishtha", "Shatabhisha"}          # movable
_NK_STHIRA  = {"Rohini", "Uttara Phalguni", "Uttara Ashadha", "Uttara Bhadrapada"}     # fixed
_NK_MRIDU   = {"Mrigashira", "Chitra", "Anuradha", "Revati"}                           # soft
_NK_KSHIPRA = {"Ashwini", "Pushya", "Hasta"}                                           # swift
_NK_DHRUVA  = _NK_STHIRA
_BAD_YOGAS  = {"Vishkambha", "Atiganda", "Shula", "Ganda", "Vyaghata",
               "Vajra", "Vyatipata", "Parigha", "Vaidhriti"}

# activity -> favourable nakshatras + favourable weekdays
MUHURTA_ACTIVITIES = {
    "Marriage (Vivaha)": {
        "nak": {"Rohini", "Mrigashira", "Magha", "Uttara Phalguni", "Hasta", "Swati",
                "Anuradha", "Mula", "Uttara Ashadha", "Uttara Bhadrapada", "Revati"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "Travel / Journey (Yatra)": {
        "nak": _NK_CHARA | {"Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta",
                            "Anuradha", "Revati"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "Start business / trade": {
        "nak": _NK_KSHIPRA | _NK_CHARA | {"Chitra", "Anuradha", "Uttara Phalguni",
                                          "Uttara Ashadha", "Uttara Bhadrapada", "Revati"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "Education / learning (Vidyarambha)": {
        "nak": {"Hasta", "Ashwini", "Punarvasu", "Pushya", "Chitra", "Swati", "Shravana",
                "Dhanishtha", "Shatabhisha", "Mrigashira", "Anuradha", "Revati"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "House construction (Griha Arambha)": {
        "nak": _NK_STHIRA | {"Mrigashira", "Chitra", "Swati", "Dhanishtha", "Shatabhisha",
                             "Anuradha", "Revati"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "House-warming (Griha Pravesha)": {
        "nak": _NK_STHIRA | {"Mrigashira", "Chitra", "Anuradha", "Revati", "Shravana",
                             "Dhanishtha", "Shatabhisha", "Pushya"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "Buy vehicle / property": {
        "nak": _NK_CHARA | {"Hasta", "Chitra", "Uttara Phalguni", "Uttara Ashadha",
                            "Uttara Bhadrapada", "Revati", "Anuradha", "Pushya",
                            "Mrigashira", "Ashwini"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
    "Medical treatment / healing": {
        "nak": {"Ashwini", "Pushya", "Hasta", "Chitra", "Anuradha", "Revati",
                "Mrigashira", "Shravana"},
        "vara": {"Sunday", "Tuesday", "Wednesday", "Thursday", "Friday"}},
    "New venture / naming (general)": {
        "nak": _NK_KSHIPRA | _NK_CHARA | _NK_MRIDU | _NK_STHIRA | {"Punarvasu"},
        "vara": {"Monday", "Wednesday", "Thursday", "Friday"}},
}


def compute_muhurta(activity: str, lat: float, lon: float, tz_offset: float,
                    start, days: int = 183, all_nak: bool = False) -> List[Dict]:
    """For each day, find the local-time WINDOW(S) of each Moon-nakshatra (boundary
    times interpolated). By default only nakshatras suited to the activity are returned;
    with all_nak=True every nakshatra is returned (flagged favourable or not) so the full
    continuous sequence is visible. Rated by vara/tithi/yoga/karana."""
    spec = MUHURTA_ACTIVITIES.get(activity)
    if not spec:
        return []
    good_nak, good_vara = spec["nak"], spec["vara"]
    span = 360.0 / 27

    def hm(mn):
        mn = max(0, min(int(round(mn)), 1440))
        return f"{mn // 60:02d}:{mn % 60:02d}"

    out: List[Dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        widx = d.isoweekday() % 7
        vara = VARA[widx % 7][0]

        # hourly Moon longitudes across the local day, unwrapped so they increase monotonically
        lons = []
        for h in range(25):
            _, m = _sun_moon_sid(get_jd(d.year, d.month, d.day, float(h) - tz_offset))
            while lons and m < lons[-1] - 1:
                m += 360
            lons.append(m)

        # every nakshatra segment that day, with interpolated start/end minutes
        segs = []
        cur = int(lons[0] / span)
        seg_start = 0.0
        for h in range(1, 25):
            ni = int(lons[h] / span)
            if ni != cur:                          # one boundary at most (Moon ~0.5°/h)
                bnd = (int(lons[h - 1] / span) + 1) * span
                frac = ((bnd - lons[h - 1]) / (lons[h] - lons[h - 1])
                        if lons[h] != lons[h - 1] else 0.5)
                cross = (h - 1 + frac) * 60.0
                segs.append((NAKSHATRAS[cur % 27][0], seg_start, cross))
                cur, seg_start = ni, cross
        segs.append((NAKSHATRAS[cur % 27][0], seg_start, 1440.0))

        if not all_nak and not any(nak in good_nak for nak, _, _ in segs):
            continue

        # day panchanga sampled at ~sunrise (06:00 local) for tithi / yoga / karana
        s6, m6 = _sun_moon_sid(get_jd(d.year, d.month, d.day, 6.0 - tz_offset))
        n6, nl6, _ = nakshatra_of(m6)
        pan = compute_panchang(s6, m6, widx, n6, nl6)
        tnum, pk = pan["tithi_num"], pan["paksha"]

        for nak, a, b in segs:
            fav = nak in good_nak
            if not all_nak and not fav:
                continue
            if fav:
                score, flags = 2, []
                if vara in good_vara:
                    score += 1
                else:
                    flags.append("weekday weak")
                if pk == "Krishna" and tnum == 15:
                    score -= 3; flags.append("Amavasya")
                elif pk == "Shukla" and tnum == 15:
                    score += 1
                elif tnum in (4, 9, 14):
                    score -= 2; flags.append("Rikta tithi")
                if pan["yoga"] in _BAD_YOGAS:
                    score -= 2; flags.append(f"{pan['yoga']} yoga")
                if pan["karana"] == "Vishti":
                    score -= 1; flags.append("Vishti karana")
                rating = ("Excellent" if score >= 3 else "Good" if score >= 2
                          else "Fair" if score >= 1 else "Caution")
            else:
                score, rating, flags = -1, "- not for this", ["nakshatra not used here"]
            out.append({"date": d.isoformat(), "weekday": vara, "nakshatra": nak,
                        "favourable": fav, "window": f"{hm(a)}–{hm(b)}", "tithi": pan["tithi"],
                        "yoga": pan["yoga"], "karana": pan["karana"],
                        "rating": rating, "score": score, "flags": ", ".join(flags) or "-"})
    return out


def muhurta_grid(activity: str, lat: float, lon: float, tz_offset: float,
                 start, days: int = 31) -> List[Dict]:
    """Per-day factor ratings for a month-style heatmap. Each factor is 'good'/'mix'/'bad'."""
    spec = MUHURTA_ACTIVITIES.get(activity)
    if not spec:
        return []
    good_nak, good_vara = spec["nak"], spec["vara"]
    span = 360.0 / 27
    grid = []
    for i in range(days):
        d = start + timedelta(days=i)
        widx = d.isoweekday() % 7
        vara = VARA[widx % 7][0]

        # favourable-nakshatra minutes during the local day (windowed)
        lons = []
        for h in range(25):
            _, m = _sun_moon_sid(get_jd(d.year, d.month, d.day, float(h) - tz_offset))
            while lons and m < lons[-1] - 1:
                m += 360
            lons.append(m)
        fav_min = 0.0
        cur, seg_start = int(lons[0] / span), 0.0
        for h in range(1, 25):
            ni = int(lons[h] / span)
            if ni != cur:
                bnd = (int(lons[h - 1] / span) + 1) * span
                frac = ((bnd - lons[h - 1]) / (lons[h] - lons[h - 1])
                        if lons[h] != lons[h - 1] else 0.5)
                cross = (h - 1 + frac) * 60.0
                if NAKSHATRAS[cur % 27][0] in good_nak:
                    fav_min += cross - seg_start
                cur, seg_start = ni, cross
        if NAKSHATRAS[cur % 27][0] in good_nak:
            fav_min += 1440.0 - seg_start
        nak = "good" if fav_min >= 600 else "mix" if fav_min > 0 else "bad"

        s6, m6 = _sun_moon_sid(get_jd(d.year, d.month, d.day, 6.0 - tz_offset))
        n6, nl6, _ = nakshatra_of(m6)
        pan = compute_panchang(s6, m6, widx, n6, nl6)
        tnum, pk = pan["tithi_num"], pan["paksha"]
        varaC  = "good" if vara in good_vara else "bad"
        tithiC = "bad" if (pk == "Krishna" and tnum == 15) or tnum in (4, 9, 14) else "good"
        yogaC  = "bad" if pan["yoga"] in _BAD_YOGAS else "good"
        karC   = "bad" if pan["karana"] == "Vishti" else "good"

        sc = (2 if nak == "good" else 1 if nak == "mix" else -2)
        sc += (1 if varaC == "good" else 0)
        sc -= sum(1 for c in (tithiC, yogaC, karC) if c == "bad")
        overall = ("excellent" if sc >= 3 else "good" if sc >= 2
                   else "fair" if sc >= 1 else "bad")

        grid.append({"date": d.isoformat(), "dom": d.day, "wd": vara[0], "weekday": vara,
                     "nak": nak, "nak_label": n6, "vara": varaC, "tithi": tithiC,
                     "tithi_label": pan["tithi"], "yoga": yogaC, "yoga_label": pan["yoga"],
                     "karana": karC, "karana_label": pan["karana"], "overall": overall})
    return grid


# ══════════════════════════════════════════════════════════════════════════════
# ASHTAKOOTA - marriage / partnership compatibility (Guna Milan, 36 points)
# ══════════════════════════════════════════════════════════════════════════════
_VARNA = {3: 4, 7: 4, 11: 4, 0: 3, 4: 3, 8: 3, 1: 2, 5: 2, 9: 2, 2: 1, 6: 1, 10: 1}
_VASHYA_GRP = {0: "Q", 1: "Q", 8: "Q", 9: "Q", 2: "H", 5: "H", 6: "H", 10: "H",
               3: "W", 11: "W", 4: "V", 7: "K"}
_VASHYA_PTS = {("Q", "Q"): 2, ("Q", "H"): 1, ("Q", "W"): 2, ("Q", "V"): 0, ("Q", "K"): 1,
               ("H", "Q"): 1, ("H", "H"): 2, ("H", "W"): 1, ("H", "V"): 0.5, ("H", "K"): 1,
               ("W", "Q"): 2, ("W", "H"): 1, ("W", "W"): 2, ("W", "V"): 1, ("W", "K"): 1,
               ("V", "Q"): 1, ("V", "H"): 0.5, ("V", "W"): 1, ("V", "V"): 2, ("V", "K"): 0,
               ("K", "Q"): 1, ("K", "H"): 1, ("K", "W"): 1, ("K", "V"): 1, ("K", "K"): 2}
_YONI = ["Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep", "Cat",
         "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer", "Deer", "Dog",
         "Monkey", "Mongoose", "Monkey", "Lion", "Horse", "Lion", "Cow", "Elephant"]
_YONI_ENEMY = {frozenset(("Horse", "Buffalo")), frozenset(("Elephant", "Lion")),
               frozenset(("Sheep", "Monkey")), frozenset(("Serpent", "Mongoose")),
               frozenset(("Dog", "Deer")), frozenset(("Cat", "Rat")),
               frozenset(("Cow", "Tiger"))}
_GANA = {**{i: "Deva" for i in (0, 4, 6, 7, 12, 14, 16, 21, 26)},
         **{i: "Manushya" for i in (1, 3, 5, 10, 11, 19, 20, 24, 25)},
         **{i: "Rakshasa" for i in (2, 8, 9, 13, 15, 17, 18, 22, 23)}}
_GANA_PTS = {("Deva", "Deva"): 6, ("Deva", "Manushya"): 6, ("Deva", "Rakshasa"): 1,
             ("Manushya", "Deva"): 5, ("Manushya", "Manushya"): 6, ("Manushya", "Rakshasa"): 0,
             ("Rakshasa", "Deva"): 1, ("Rakshasa", "Manushya"): 0, ("Rakshasa", "Rakshasa"): 6}
_NADI = {**{i: "Adi" for i in (0, 5, 6, 11, 12, 17, 18, 23, 24)},
         **{i: "Madhya" for i in (1, 4, 7, 10, 13, 16, 19, 22, 25)},
         **{i: "Antya" for i in (2, 3, 8, 9, 14, 15, 20, 21, 26)}}
_NAT_FRIEND = {  # planet: (friends, enemies); the rest are neutral
    "Sun": ({"Moon", "Mars", "Jupiter"}, {"Venus", "Saturn"}),
    "Moon": ({"Sun", "Mercury"}, set()),
    "Mars": ({"Sun", "Moon", "Jupiter"}, {"Mercury"}),
    "Mercury": ({"Sun", "Venus"}, {"Moon"}),
    "Jupiter": ({"Sun", "Moon", "Mars"}, {"Mercury", "Venus"}),
    "Venus": ({"Mercury", "Saturn"}, {"Sun", "Moon"}),
    "Saturn": ({"Mercury", "Venus"}, {"Sun", "Moon", "Mars"})}
_GM_PTS = {("F", "F"): 5, ("F", "N"): 4, ("N", "F"): 4, ("N", "N"): 3,
           ("F", "E"): 1, ("E", "F"): 1, ("N", "E"): 0.5, ("E", "N"): 0.5, ("E", "E"): 0}


# [removed] legacy compute_compatibility(boy,girl) — superseded by the
# chart-based compute_compatibility() further below.


# [removed] legacy Manglik helper + its house-set constant —
# superseded by _mangal_dosha(chart) in the compatibility module.

def nak_index(name: str) -> int:
    return next((i for i, (n, _) in enumerate(NAKSHATRAS) if n == name), 0)


# ══════════════════════════════════════════════════════════════════════════════
# SHAD BALA - six-fold planetary strength (virupas; 60 virupas = 1 rupa)
# Position/time parts (Sthana, Dig, Paksha, Vara, Naisargika) are exact; Cheshta,
# Ayana, Nathonnatha, Tribhaga and Hora are approximated (the lightweight engine
# carries no planetary speed, declination or sunrise) - labelled as such.
# ══════════════════════════════════════════════════════════════════════════════
_SB = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
_SB_EXALT = {"Sun": 10.0, "Moon": 33.0, "Mars": 298.0, "Mercury": 165.0,
             "Jupiter": 95.0, "Venus": 357.0, "Saturn": 200.0}
_SB_NAIS = {"Sun": 60.0, "Moon": 51.43, "Mars": 17.14, "Mercury": 25.71,
            "Jupiter": 34.29, "Venus": 42.86, "Saturn": 8.57}
_SB_REQ = {"Sun": 5.0, "Moon": 6.0, "Mars": 5.0, "Mercury": 7.0,
           "Jupiter": 6.5, "Venus": 5.5, "Saturn": 5.0}
_SB_MOOLA = {"Sun": 4, "Moon": 1, "Mars": 0, "Mercury": 5, "Jupiter": 8, "Venus": 6, "Saturn": 10}
_SB_DIR = {"Mercury": 0, "Jupiter": 0, "Moon": 90, "Venus": 90, "Saturn": 180,
           "Sun": 270, "Mars": 270}
_SB_MALE = {"Sun", "Mars", "Jupiter"}
_SB_FEMALE = {"Moon", "Venus"}
_SB_NEUT = {"Mercury", "Saturn"}
_SB_DAY = {"Sun", "Jupiter", "Venus"}
_SB_BEN = {"Jupiter", "Venus", "Mercury", "Moon"}
_SB_NORTH = {"Sun", "Mars", "Jupiter", "Venus", "Mercury"}
_SB_DIGNVIR = {"MT": 45, "own": 30, "GF": 22.5, "F": 15, "N": 7.5, "E": 3.75, "GE": 1.875}
_HORA_ORDER = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]


def _sb_arc(a, b):
    d = abs((a - b) % 360)
    return d if d <= 180 else 360 - d


def _sb_varga_sign(lon, div):
    s = int(lon / 30) % 12
    p = lon % 30
    if div == 2:
        first = p < 15
        odd = s % 2 == 0
        return (4 if first else 3) if odd else (3 if first else 4)
    if div == 3:
        return drekkana_sign(lon)
    if div == 7:
        start = s if s % 2 == 0 else (s + 6) % 12
        return (start + int(p / (30.0 / 7))) % 12
    if div == 9:
        return navamsa_sign(lon)
    if div == 12:
        return (s + int(p / 2.5)) % 12
    return s


def _sb_d30_lord(lon):
    s = int(lon / 30) % 12
    p = lon % 30
    if s % 2 == 0:
        return ("Mars" if p < 5 else "Saturn" if p < 10 else "Jupiter"
                if p < 18 else "Mercury" if p < 25 else "Venus")
    return ("Venus" if p < 5 else "Mercury" if p < 12 else "Jupiter"
            if p < 20 else "Saturn" if p < 25 else "Mars")


def _sb_compound(p, other, rashi):
    fr, en = _NAT_FRIEND[p]
    nat = "F" if other in fr else "E" if other in en else "N"
    d = (rashi[other] - rashi[p]) % 12 + 1
    temp = "F" if d in (2, 3, 4, 10, 11, 12) else "E"
    return {("F", "F"): "GF", ("F", "E"): "N", ("N", "F"): "F", ("N", "E"): "E",
            ("E", "F"): "N", ("E", "E"): "GE"}[(nat, temp)]


def _sb_saptavarga(p, lon_p, rashi, own):
    total = 0.0
    for div in (1, 2, 3, 7, 9, 12, 30):
        if div == 30:
            lord = _sb_d30_lord(lon_p)
            total += 30 if lord == p else _SB_DIGNVIR[_sb_compound(p, lord, rashi)]
            continue
        vs = _sb_varga_sign(lon_p, div)
        if vs == _SB_MOOLA[p]:
            total += 45
        elif vs in own[p]:
            total += 30
        else:
            lord = SIGN_LORDS[SIGNS[vs]]
            total += 30 if lord == p else _SB_DIGNVIR[_sb_compound(p, lord, rashi)]
    return total


def compute_shadbala(planets, lagna_idx, asc_lon, sun_lon, moon_lon, ayan,
                     hour_local, weekday_idx) -> Dict:
    rashi = {p: planets[p]["sign_idx"] for p in _SB}
    lon = {p: planets[p]["lon"] for p in _SB}
    house = {p: planets[p]["house"] for p in _SB}
    own = {p: OWN_SIGNS.get(p, []) for p in _SB}
    elong = _sb_arc(moon_lon, sun_lon)
    h = hour_local % 24
    vara_lord = VARA[weekday_idx % 7][1]
    if 6 <= h < 18:
        trib_lord = ["Mercury", "Sun", "Saturn"][min(int((h - 6) // 4), 2)]
    else:
        trib_lord = ["Moon", "Venus", "Mars"][min(int(((h - 18) % 24) // 4), 2)]
    start = _HORA_ORDER.index(vara_lord) if vara_lord in _HORA_ORDER else 0
    hora_lord = _HORA_ORDER[(start + int((h - 6) % 24)) % 7]
    dayval = (12 - abs(h - 12)) / 12.0 * 60.0

    res = {}
    for p in _SB:
        lp = lon[p]
        uccha = _sb_arc(lp, (_SB_EXALT[p] + 180) % 360) / 3.0
        sapta = _sb_saptavarga(p, lp, rashi, own)
        nav = navamsa_sign(lp)
        oy = 0.0
        odd_r, odd_n = rashi[p] % 2 == 0, nav % 2 == 0
        if p in _SB_FEMALE:
            oy += 15 if not odd_r else 0
            oy += 15 if not odd_n else 0
        else:
            oy += 15 if odd_r else 0
            oy += 15 if odd_n else 0
        hh = house[p]
        kd = 60 if hh in (1, 4, 7, 10) else 30 if hh in (2, 5, 8, 11) else 15
        dec = int((lp % 30) // 10)
        dk = 15.0 if ((p in _SB_MALE and dec == 0) or (p in _SB_NEUT and dec == 1)
                      or (p in _SB_FEMALE and dec == 2)) else 0.0
        sthana = uccha + sapta + oy + kd + dk

        weak = (asc_lon + _SB_DIR[p] + 180) % 360
        dig = _sb_arc(lp, weak) / 3.0

        natho = 60.0 if p == "Mercury" else (dayval if p in _SB_DAY else 60 - dayval)
        paksha = (elong / 180.0 * 60.0) if p in _SB_BEN else (60 - elong / 180.0 * 60.0)
        if p == "Moon":
            paksha *= 2
        trib = 60.0 if (p == "Jupiter" or p == trib_lord) else 0.0
        lordb = (45.0 if p == vara_lord else 0.0) + (60.0 if p == hora_lord else 0.0)
        ltrop = math.radians((lp + ayan) % 360)
        decl = math.degrees(math.asin(math.sin(math.radians(23.4393)) * math.sin(ltrop)))
        sd = decl if p in _SB_NORTH else -decl
        ayana = max(0.0, min(60.0, (24.0 + sd) / 48.0 * 60.0))
        kala = natho + paksha + trib + lordb + ayana

        if p == "Sun":
            cheshta = ayana
        elif p == "Moon":
            cheshta = paksha
        else:
            es = _sb_arc(lp, sun_lon)
            if p in ("Mars", "Jupiter", "Saturn"):
                cheshta = es / 3.0
            else:
                maxe = 28.0 if p == "Mercury" else 47.0
                cheshta = max(0.0, (maxe - min(es, maxe)) / maxe * 60.0)

        drik = 0.0
        for q in _SB:
            if q == p:
                continue
            if (rashi[p] - rashi[q]) % 12 in _ASPECT_OFF.get(q, {6}):
                drik += 15 if q in _SB_BEN else -15
        drik /= 4.0

        total = sthana + dig + kala + cheshta + _SB_NAIS[p] + drik
        rupa = total / 60.0
        ceff = min(max(cheshta, 0.0), 60.0)
        ishta = math.sqrt(uccha * ceff)
        kashta = math.sqrt((60 - uccha) * (60 - ceff))
        res[p] = {"sthana": round(sthana, 1), "dig": round(dig, 1), "kala": round(kala, 1),
                  "cheshta": round(cheshta, 1), "naisargika": round(_SB_NAIS[p], 1),
                  "drik": round(drik, 1), "total": round(total, 1), "rupa": round(rupa, 2),
                  "required": _SB_REQ[p], "ratio": round(rupa / _SB_REQ[p], 2),
                  "strong": rupa >= _SB_REQ[p], "uccha": round(uccha, 1),
                  "ishta": round(ishta, 1), "kashta": round(kashta, 1)}
    order = sorted(_SB, key=lambda p: res[p]["rupa"], reverse=True)
    return {"planets": res, "order": order}


_BB_NARA = {2, 5, 6, 10}
_BB_CHATU = {0, 1, 4, 8, 9}
_BB_JALA = {3, 11}
_BB_KEETA = {7}


def _bb_sign_dir(si):
    if si in _BB_NARA:
        return 0      # human signs strong in the East / Lagna
    if si in _BB_CHATU:
        return 270    # quadruped signs strong in the South / 10th
    if si in _BB_JALA:
        return 90     # watery signs strong in the North / 4th
    return 180        # insect (Scorpio) strong in the West / 7th


def compute_bhavabala(planets, lagna_idx, asc_lon, shadbala) -> Dict:
    """Bhava Bala per house = house-lord's Shad Bala (Bhavadhipati) + Bhava Dig Bala
    (sign-type direction) + Bhava Drishti Bala (net aspects). Drishti/Dig are approximate."""
    SB = shadbala["planets"]
    rashi = {p: planets[p]["sign_idx"] for p in _SB}
    res = {}
    for h in range(1, 13):
        si = (lagna_idx + h - 1) % 12
        lord = SIGN_LORDS[SIGNS[si]]
        adhipati = SB[lord]["total"]
        cusp = (asc_lon + (h - 1) * 30) % 360
        weak = (asc_lon + _bb_sign_dir(si) + 180) % 360
        dig = _sb_arc(cusp, weak) / 3.0
        drishti = 0.0
        for q in _SB:
            if (si - rashi[q]) % 12 in _ASPECT_OFF.get(q, {6}):
                drishti += 15 if q in _SB_BEN else -15
        drishti /= 4.0
        total = adhipati + dig + drishti
        res[h] = {"lord": lord, "sign": SIGNS[si], "adhipati": round(adhipati, 1),
                  "dig": round(dig, 1), "drishti": round(drishti, 1),
                  "total": round(total, 1), "rupa": round(total / 60.0, 2)}
    order = sorted(range(1, 13), key=lambda h: res[h]["rupa"], reverse=True)
    return {"houses": res, "order": order}


def generate_chart(year:int, month:int, day:int, hour:int, minute:int,
                   lat:float, lon:float, tz_offset:float,
                   location:str="", name:str="", gender:str="") -> Dict:
    """Compute a complete Jyotiṣa birth chart (data only, no rendering)."""
    local_dt = datetime(year,month,day,hour,minute,
                        tzinfo=timezone(timedelta(hours=tz_offset)))
    ut_dt    = local_dt.astimezone(timezone.utc)
    hour_ut  = ut_dt.hour + ut_dt.minute/60 + ut_dt.second/3600
    jd       = get_jd(ut_dt.year, ut_dt.month, ut_dt.day, hour_ut)

    lons, ayan, engine = compute_positions(jd, lat, lon)

    planets = {pname: _planet_record(pname, slon) for pname,slon in lons.items()}

    # Rückläufigkeits-Flags (nur mit SWE; Geschwindigkeit < 0 = retrograd).
    # Wichtig für compute_afflictions ("retrograde") und den Medizin-Tab (KAP).
    # Nur als Flag, NICHT im pos-String — _deg_in_sign_val parst pos numerisch.
    # Sonne/Mond sind nie retrograd; mittlere Knoten laufen definitionsgemäss
    # rückwärts und werden nicht geflaggt.
    if _SWE:
        for pname in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
            try:
                swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
                xx, _rf = swe.calc_ut(jd, _SWE_ID[pname],
                                      swe.FLG_SIDEREAL | swe.FLG_SPEED)
                planets[pname]["retrograde"] = xx[3] < 0
            except Exception:
                pass

    lagna_idx = planets["Ascendant"]["sign_idx"]
    houses    = {h: SIGNS[(lagna_idx+h-1)%12] for h in range(1,13)}
    occupants: Dict[int,List[str]] = {h:[] for h in range(1,13)}
    for pname, pd in planets.items():
        if pname=="Ascendant": continue
        h=(pd["sign_idx"]-lagna_idx)%12+1; pd["house"]=h; occupants[h].append(pname)

    # Bhava Chalit - equal houses with the Ascendant as each bhava's madhya (middle),
    # so a planet near a sign edge can fall into a different bhava than its rasi house.
    asc_lon = lons["Ascendant"]
    bhava_house: Dict[str, int] = {}
    bhava_place: Dict[str, int] = {}   # planet -> sign occupying its bhava's madhya
    for pname in planets:
        if pname == "Ascendant":
            continue
        bh = int(((lons[pname] - asc_lon + 15) % 360) // 30) + 1
        bhava_house[pname] = bh
        bhava_place[pname] = (lagna_idx + bh - 1) % 12
        planets[pname]["bhava"] = bh
        _sh = (bh - planets[pname]["house"]) % 12
        planets[pname]["bhava_shift"] = _sh - 12 if _sh > 6 else _sh

    today_dt  = datetime.now(timezone.utc)
    jd_today  = get_jd(today_dt.year, today_dt.month, today_dt.day,
                        today_dt.hour + today_dt.minute/60)
    t_lons, _, _ = compute_positions(jd_today, lat, lon)
    transits  = {pname: _planet_record(pname, slon) for pname,slon in t_lons.items()}
    transit_local = today_dt.astimezone(timezone(timedelta(hours=tz_offset)))

    natal_si  = {p: planets[p]["sign_idx"] for p in planets}
    akv       = compute_ashtakavarga(natal_si)

    d9  = compute_divisional(lons, 9)
    d3  = compute_divisional(lons, 3)
    d10 = compute_divisional(lons, 10)
    d4  = compute_divisional(lons, 4)
    # Full versions with per-planet dignity + vargottama (single source of truth)
    d9_full  = compute_divisional_full(lons, 9)
    d3_full  = compute_divisional_full(lons, 3)
    d10_full = compute_divisional_full(lons, 10)
    d4_full  = compute_divisional_full(lons, 4)

    varshaphala = compute_varshaphala(
        year, month, day, lons["Sun"], lagna_idx,
        lat, lon, datetime.now().year)

    jaimini = compute_jaimini(lons, lagna_idx)
    chara_dasha = build_chara_dasha(
        {p: planets[p]["sign_idx"] for p in planets if p != "Ascendant"},
        lons, lagna_idx, local_dt.replace(tzinfo=None))

    panchang = compute_panchang(lons["Sun"], lons["Moon"], local_dt.isoweekday() % 7,
                                planets["Moon"]["nakshatra"], planets["Moon"]["nak_lord"])
    yogas = compute_yogas(planets, lagna_idx)
    # Varga-Yogas: VRY und Parivartana aus D9/D10 in die Yoga-Liste aufnehmen,
    # damit sie im Yogas-Tab und in den KI-Fakten sichtbar sind (Fund: ein
    # 1↔9-Parivartana im Daśāṃśa wurde bisher nirgends ausgewiesen).
    for _vf, _vlabel in ((d9_full, "D9"), (d10_full, "D10")):
        _vm = _vf.get("_meta", {}) if isinstance(_vf, dict) else {}
        for _e in _vm.get("vipareeta_raja_yoga", []):
            yogas.append({"name": f"Vipareeta Raja Yoga ({_vlabel})",
                          "group": "Varga", "planets": [_e.split(" ")[0]],
                          "detail": f"In the {_vlabel} chart: {_e}."})
        for _e in _vm.get("parivartana", []):
            _pl = [_e.split(" ")[0], _e.split(" \u21c4 ")[1].split(" ")[0]] \
                if " \u21c4 " in _e else []
            _kind = "Raja Parivartana" if "(Raja)" in _e else \
                    "Dainya Parivartana" if "(Dainya)" in _e else "Parivartana"
            yogas.append({"name": f"{_kind} Yoga ({_vlabel})",
                          "group": "Varga", "planets": _pl,
                          "detail": f"In the {_vlabel} chart: {_e}."})

    shadbala = compute_shadbala(planets, lagna_idx, asc_lon, lons["Sun"], lons["Moon"],
                                ayan, hour + minute / 60.0, local_dt.isoweekday() % 7)
    bhavabala = compute_bhavabala(planets, lagna_idx, asc_lon, shadbala)

    ah,am = int(abs(tz_offset)), int(round((abs(tz_offset)%1)*60))
    sgn   = "+" if tz_offset>=0 else "-"

    return {
        "meta": {
            "name": name, "gender": gender,
            "birth":    local_dt.strftime("%d %B %Y  %H:%M"),
            # numeric birth data — display-format-independent (used by chart_html
            # for the Varshaphala AJAX parameters; never parse the string above)
            "birth_y": year, "birth_mo": month, "birth_d": day,
            "birth_h": hour, "birth_min": minute,
            "ut":       ut_dt.strftime("%d %B %Y  %H:%M UTC"),
            "tz":       f"UTC{sgn}{ah:02d}:{am:02d}",
            "location": location, "lat":lat, "lon":lon,
            "jd":       round(jd,5), "ayan": round(ayan,4), "engine": engine,
        },
        "lagna":      planets["Ascendant"]["sign"],
        "lagna_pos":  planets["Ascendant"]["pos"],
        "lagna_idx":  lagna_idx,
        "planets":    planets,
        "houses":     houses,
        "occupants":  occupants,
        "lons":       lons,
        "transits":   transits,
        "transit_date": today_dt.strftime("%d %b %Y"),
        "transit_local": transit_local.strftime("%d %b %Y · %H:%M"),
        "transit_time_utc": today_dt.strftime("%H:%M UTC"),
        "transit_lagna_idx": transits["Ascendant"]["sign_idx"],
        "transit_lagna_pos": transits["Ascendant"]["pos"],
        "ashtakavarga": akv,
        "shadbala": shadbala,
        "bhavabala": bhavabala,
        "d9":  d9,  "d9_lagna":  d9["Ascendant"],
        "d3":  d3,  "d3_lagna":  d3["Ascendant"],
        "d10": d10, "d10_lagna": d10["Ascendant"],
        "d4":  d4,  "d4_lagna":  d4["Ascendant"],
        "d9_full": d9_full, "d3_full": d3_full, "d10_full": d10_full, "d4_full": d4_full,
        "aspects":    compute_aspects(planets, lagna_idx),
        "lordships":  compute_lordships(lagna_idx),
        "afflictions": compute_afflictions(planets),
        "dashas":      build_dashas(lons["Moon"], local_dt.replace(tzinfo=None)),
        "varshaphala": varshaphala,
        "jaimini":     jaimini,
        "chara_dasha": chara_dasha,
        "panchang":    panchang,
        "yogas":       yogas,
        "bhava":       {"house": bhava_house, "place": bhava_place},
    }


EXAMPLE = dict(
    year=1957, month=8, day=24, hour=13, minute=55,
    lat=47.4833, lon=7.7356, tz=1.0,
    location="Liestal, Switzerland",
    name="Example Person", gender="Male",
)


# ══════════════════════════════════════════════════════════════════════════════
#  COMPATIBILITY — Ashtakūṭa (Guṇa Milāna) 36-point system + Mangal Dosha
#  + house overlays.  All computation lives here (single source of truth).
#  chart_html.py only renders; report_service.py only routes the AJAX request.
# ══════════════════════════════════════════════════════════════════════════════

# ── Kūṭa reference tables (classical) ─────────────────────────────────────────
# Varna (max 1): Moon-sign varna. Brahmin>Kshatriya>Vaishya>Shudra by rank.
_VARNA_BY_SIGN = {  # sign_idx -> varna rank (3=Brahmin highest ... 0=Shudra)
    3: 3, 7: 3, 11: 3,          # Cancer, Scorpio, Pisces = Brahmin
    0: 2, 4: 2, 8: 2,           # Aries, Leo, Sagittarius = Kshatriya
    1: 1, 5: 1, 9: 1,           # Taurus, Virgo, Capricorn = Vaishya
    2: 0, 6: 0, 10: 0,          # Gemini, Libra, Aquarius = Shudra
}
# Vashya Kuta (max 2): mutual attraction / control. Five classical groups:
#   C = Chatushpada (quadruped), M = Manava/Dvipada (human),
#   J = Jalachara (water), V = Vanachara (wild), K = Keeta (insect).
# Sign→group with the classical half-sign splits for Sagittarius & Capricorn.
def _vashya_group(sign_idx, deg_in_sign):
    # deg_in_sign: 0..30
    if sign_idx == 0:  return "C"   # Aries      – quadruped
    if sign_idx == 1:  return "C"   # Taurus     – quadruped
    if sign_idx == 2:  return "M"   # Gemini     – human
    if sign_idx == 3:  return "J"   # Cancer     – water (crab)
    if sign_idx == 4:  return "V"   # Leo        – wild (lion)
    if sign_idx == 5:  return "M"   # Virgo      – human
    if sign_idx == 6:  return "M"   # Libra      – human
    if sign_idx == 7:  return "K"   # Scorpio    – insect (keeta)
    if sign_idx == 8:                # Sagittarius – 1st half human, 2nd half quadruped
        return "M" if deg_in_sign < 15 else "C"
    if sign_idx == 9:                # Capricorn  – 1st half quadruped, 2nd half water
        return "C" if deg_in_sign < 15 else "J"
    if sign_idx == 10: return "M"   # Aquarius   – human
    if sign_idx == 11: return "J"   # Pisces     – water
    return "M"

# Full classical 5×5 Vashya point matrix (row = person A group, col = B group).
# 2 = fully controlled/attracted, 1 = half, 0.5 = mild, 0 = none.
# Rows/cols order: C, M, J, V, K
_VASHYA_ORDER = ["C", "M", "J", "V", "K"]
_VASHYA_MATRIX = {
    #        C     M     J     V     K
    "C": {"C":2.0,"M":1.0,"J":1.0,"V":0.0,"K":1.0},
    "M": {"C":0.5,"M":2.0,"J":0.5,"V":0.0,"K":1.0},
    "J": {"C":1.0,"M":1.0,"J":2.0,"V":0.5,"K":0.5},
    "V": {"C":1.0,"M":0.0,"J":0.5,"V":2.0,"K":1.0},
    "K": {"C":0.5,"M":1.0,"J":1.0,"V":1.0,"K":2.0},
}
# Yoni (max 4): 14 animal yonis by nakshatra, with sex; enemy/friend matrix.
_YONI = [  # nak_idx -> (animal, sex)  (0-based, 27 nakshatras)
    ("Horse","M"),("Elephant","M"),("Sheep","F"),("Serpent","M"),("Serpent","F"),
    ("Dog","F"),("Cat","F"),("Sheep","M"),("Cat","M"),("Rat","M"),
    ("Rat","F"),("Cow","F"),("Buffalo","M"),("Tiger","F"),("Buffalo","F"),
    ("Tiger","M"),("Deer","F"),("Deer","M"),("Dog","M"),("Monkey","M"),
    ("Mongoose","M"),("Monkey","F"),("Lion","F"),("Horse","F"),("Lion","M"),
    ("Cow","M"),("Elephant","F"),
]
# Yoni Kuta — full 14×14 compatibility matrix (classical Vivaha values 0–4).
# 4 = same yoni (best), 3 = friendly, 2 = neutral, 1 = unfriendly, 0 = mortal enemies.
# Row/column order = the 14 canonical yonis:
_YONI_ORDER = ["Horse", "Elephant", "Sheep", "Serpent", "Dog", "Cat", "Rat",
               "Cow", "Buffalo", "Tiger", "Deer", "Monkey", "Mongoose", "Lion"]
# Matrix rows follow _YONI_ORDER; each row has 14 values (0–4).
_YONI_MATRIX = [
    # Hor El Sh Se Do Ca Ra Co Bu Ti De Mo Mn Li
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],  # Horse
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 3, 2, 0],  # Elephant
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],  # Sheep/Goat
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],  # Serpent
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 2, 1],  # Dog
    [2, 2, 2, 1, 2, 4, 0, 2, 2, 1, 3, 3, 2, 2],  # Cat
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 1, 2],  # Rat
    [1, 2, 3, 1, 2, 2, 2, 4, 3, 0, 3, 2, 2, 1],  # Cow
    [0, 3, 3, 1, 2, 2, 2, 3, 4, 1, 2, 2, 2, 1],  # Buffalo
    [1, 1, 1, 2, 1, 1, 2, 0, 1, 4, 1, 2, 2, 3],  # Tiger
    [3, 2, 2, 2, 0, 3, 2, 3, 2, 1, 4, 2, 2, 1],  # Deer/Hare
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 2, 2, 4, 3, 2],  # Monkey
    [2, 2, 3, 0, 2, 2, 1, 2, 2, 2, 2, 3, 4, 2],  # Mongoose
    [1, 0, 1, 2, 1, 2, 2, 1, 1, 3, 1, 2, 2, 4],  # Lion
]
_YONI_IDX = {name: i for i, name in enumerate(_YONI_ORDER)}
# Gana (max 6): Deva / Manushya / Rakshasa per nakshatra.
_GANA = [  # nak_idx -> gana
    "Deva","Manu","Raksha","Manu","Deva","Manu","Deva","Deva","Raksha",
    "Raksha","Manu","Manu","Deva","Raksha","Deva","Raksha","Deva","Raksha",
    "Raksha","Manu","Manu","Deva","Raksha","Raksha","Manu","Manu","Deva",
]
# Nadi (max 8): Aadi / Madhya / Antya per nakshatra.
_NADI = [  # nak_idx -> nadi (0=Aadi,1=Madhya,2=Antya)
    0,1,2,0,1,2,0,1,2, 2,1,0,2,1,0,2,1,0, 0,1,2,0,1,2,0,1,2,
]
# Graha Maitri: planetary friendship (natural). rows/cols index by planet name.
_FRIEND = {
    "Sun":     {"friends":{"Moon","Mars","Jupiter"}, "enemies":{"Venus","Saturn"}},
    "Moon":    {"friends":{"Sun","Mercury"}, "enemies":set()},
    "Mars":    {"friends":{"Sun","Moon","Jupiter"}, "enemies":{"Mercury"}},
    "Mercury": {"friends":{"Sun","Venus"}, "enemies":{"Moon"}},
    "Jupiter": {"friends":{"Sun","Moon","Mars"}, "enemies":{"Mercury","Venus"}},
    "Venus":   {"friends":{"Mercury","Saturn"}, "enemies":{"Sun","Moon"}},
    "Saturn":  {"friends":{"Mercury","Venus"}, "enemies":{"Sun","Moon","Mars"}},
}
_SIGN_LORD_NAME = ["Mars","Venus","Mercury","Moon","Sun","Mercury",
                   "Venus","Mars","Jupiter","Saturn","Saturn","Jupiter"]


def _tara_points(nak_a, nak_b):
    """Tara/Dina kuta (max 3): count from A to B and B to A, check remainder."""
    def one_way(f, t):
        cnt = ((t - f) % 27) + 1
        rem = cnt % 9
        # remainders 3,5,7 are inauspicious (0 pts that direction)
        return 0.0 if rem in (3, 5, 7) else 1.5
    return one_way(nak_a, nak_b) + one_way(nak_b, nak_a)


def _vashya_points(sa, sb, deg_a=0.0, deg_b=0.0):
    """Vashya Kuta (max 2) via the full classical 5-group matrix.
    deg_a/deg_b = Moon's degree in its sign (for Sagittarius/Capricorn half-splits)."""
    ga = _vashya_group(sa, deg_a)
    gb = _vashya_group(sb, deg_b)
    return float(_VASHYA_MATRIX[ga][gb])


def _yoni_points(na, nb):
    """Yoni Kuta (max 4) via the full 14×14 classical matrix."""
    aa = _YONI[na][0]; ab = _YONI[nb][0]
    ia = _YONI_IDX.get(aa); ib = _YONI_IDX.get(ab)
    if ia is None or ib is None:
        return 2.0
    return float(_YONI_MATRIX[ia][ib])


def _maitri_points(la, lb):
    if la == lb:
        return 5.0
    a_f = lb in _FRIEND.get(la, {}).get("friends", set())
    a_e = lb in _FRIEND.get(la, {}).get("enemies", set())
    b_f = la in _FRIEND.get(lb, {}).get("friends", set())
    b_e = la in _FRIEND.get(lb, {}).get("enemies", set())
    if a_f and b_f: return 5.0
    if (a_f and not b_e) or (b_f and not a_e): return 4.0
    if not a_e and not b_e: return 3.0
    if (a_e and b_f) or (b_e and a_f): return 1.0
    if a_e and b_e: return 0.0
    return 0.5


def _gana_points(na, nb):
    ga, gb = _GANA[na], _GANA[nb]
    if ga == gb: return 6.0
    pair = (ga, gb)
    table = {
        ("Deva","Manu"):5.0, ("Manu","Deva"):6.0,
        ("Deva","Raksha"):1.0, ("Raksha","Deva"):5.0,
        ("Manu","Raksha"):0.0, ("Raksha","Manu"):3.0,
    }
    return table.get(pair, 0.0)


def _bhakut_points(sa, sb):
    """Bhakut/Rashi kuta (max 7): inauspicious if 6/8 or 5/9 or 2/12 apart."""
    d1 = ((sb - sa) % 12) + 1
    d2 = ((sa - sb) % 12) + 1
    pair = frozenset((d1, d2))
    if pair in (frozenset((2,12)), frozenset((5,9)), frozenset((6,8))):
        return 0.0
    return 7.0


def _nadi_points(na, nb):
    """Nadi kuta (max 8): same nadi = 0 (dosha), different = 8."""
    return 0.0 if _NADI[na] == _NADI[nb] else 8.0


def compute_ashtakuta(chart_a, chart_b):
    """Full Ashtakūṭa (36-guṇa) compatibility between two charts.
    Uses each chart's Moon nakshatra & sign. Returns a structured dict."""
    ma, mb = chart_a["planets"]["Moon"], chart_b["planets"]["Moon"]
    # resolve nakshatra index from name
    nak_names = [n for n, _ in NAKSHATRAS]
    na = nak_names.index(ma["nakshatra"]); nb = nak_names.index(mb["nakshatra"])
    sa, sb = ma["sign_idx"], mb["sign_idx"]
    la, lb = ma["nak_lord"], mb["nak_lord"]
    deg_a = ma.get("lon", sa * 30) % 30   # Moon's degree within its sign
    deg_b = mb.get("lon", sb * 30) % 30

    varna = 1.0 if _VARNA_BY_SIGN.get(sa,0) <= _VARNA_BY_SIGN.get(sb,0) else 0.0
    vashya = _vashya_points(sa, sb, deg_a, deg_b)
    tara = _tara_points(na, nb)
    yoni = _yoni_points(na, nb)
    maitri = _maitri_points(la, lb)
    gana = _gana_points(na, nb)
    bhakut = _bhakut_points(sa, sb)
    nadi = _nadi_points(na, nb)

    kutas = [
        ("Varna",  varna,  1, "Spirituelle Reife & Ego-Harmonie"),
        ("Vashya", vashya, 2, "Anziehung & gegenseitige Kontrolle"),
        ("Tara",   tara,   3, "Gesundheit & Wohlergehen (Nakshatra-Kompatibilität)"),
        ("Yoni",   yoni,   4, "Körperliche & intime Kompatibilität"),
        ("Graha Maitri", maitri, 5, "Geistige & seelische Freundschaft"),
        ("Gana",   gana,   6, "Temperament & Wesensart"),
        ("Bhakut", bhakut, 7, "Emotionale Bindung, Wohlstand & Familie"),
        ("Nadi",   nadi,   8, "Gesundheit, Genetik & Nachkommen"),
    ]
    total = sum(k[1] for k in kutas)

    # Nadi dosha and Bhakut dosha flags (most important cancellations)
    nadi_dosha = (nadi == 0.0)
    bhakut_dosha = (bhakut == 0.0)
    gana_dosha = (gana == 0.0)

    if total >= 28:   verdict, vcls = "Ausgezeichnet", "exc"
    elif total >= 21: verdict, vcls = "Gut", "good"
    elif total >= 18: verdict, vcls = "Akzeptabel", "ok"
    else:             verdict, vcls = "Herausfordernd", "low"

    return {
        "kutas": [{"name":k[0],"score":k[1],"max":k[2],"meaning":k[3]} for k in kutas],
        "total": round(total, 1), "max": 36,
        "percent": round(total/36*100),
        "verdict": verdict, "verdict_class": vcls,
        "nadi_dosha": nadi_dosha, "bhakut_dosha": bhakut_dosha, "gana_dosha": gana_dosha,
        "moon_a": {"nak":ma["nakshatra"],"sign":ma["sign"]},
        "moon_b": {"nak":mb["nakshatra"],"sign":mb["sign"]},
    }


def _mangal_dosha(chart):
    """Mangal (Kuja) Dosha: Mars in houses 1,2,4,7,8,12 from Lagna.
    (Lagna-only rule — the stricter classical convention.)
    House from Moon is still computed for reference/display, but does not
    by itself set the dosha flag."""
    mars = chart["planets"]["Mars"]
    h_lagna = mars.get("house", 0)
    # house from Moon (reference only)
    moon_si = chart["planets"]["Moon"]["sign_idx"]
    mars_si = mars["sign_idx"]
    h_moon = ((mars_si - moon_si) % 12) + 1
    dosha_houses = {1, 2, 4, 7, 8, 12}
    from_lagna = h_lagna in dosha_houses
    from_moon = h_moon in dosha_houses
    return {
        "present": from_lagna,          # Lagna-only rule
        "from_lagna": from_lagna, "house_lagna": h_lagna,
        "from_moon": from_moon, "house_moon": h_moon,
        "rule": "lagna",
    }


def compute_compatibility(chart_a, chart_b):
    """Top-level: Ashtakūṭa + Mangal Dosha match + house overlays."""
    ashta = compute_ashtakuta(chart_a, chart_b)
    md_a = _mangal_dosha(chart_a)
    md_b = _mangal_dosha(chart_b)
    # Mangal match: dosha cancels if both have it (or neither)
    if md_a["present"] and md_b["present"]:
        mangal_verdict = "Beide haben Mangal Dosha — der Dosha wird gegenseitig aufgehoben (günstig)."
        mangal_ok = True
    elif not md_a["present"] and not md_b["present"]:
        mangal_verdict = "Keiner hat Mangal Dosha — kein Mars-Konflikt."
        mangal_ok = True
    else:
        who = "Person A" if md_a["present"] else "Person B"
        mangal_verdict = f"Nur {who} hat Mangal Dosha — klassisch als Ungleichgewicht gewertet; Prüfung im Detail nötig."
        mangal_ok = False

    # House overlay: where does B's Moon/Sun/Venus fall counted from A's Lagna, and vice versa
    def overlay(base, other):
        base_lagna_si = base["planets"]["Ascendant"]["sign_idx"]
        out = {}
        for p in ("Moon", "Sun", "Venus", "Mars", "Jupiter"):
            osi = other["planets"][p]["sign_idx"]
            out[p] = ((osi - base_lagna_si) % 12) + 1
        return out

    return {
        "ashtakuta": ashta,
        "mangal": {"a": md_a, "b": md_b, "verdict": mangal_verdict, "ok": mangal_ok},
        "overlay_b_in_a": overlay(chart_a, chart_b),
        "overlay_a_in_b": overlay(chart_b, chart_a),
        "extra_milana": compute_extra_milana(chart_a, chart_b),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRA MILĀNA FACTORS (beyond the 36 guṇa):
#  Vedha, Rajju, Strī-Dīrgha, Rāśi Kūṭa.
#  Convention: chart_a = male (Mann), chart_b = female (Frau).
# ══════════════════════════════════════════════════════════════════════════════

# ── Vedha (Nakshatra obstruction) pairs — mutual "piercing" nakshatras (0-based).
# If the two Moon nakshatras form a Vedha pair, it is a serious affliction.
_VEDHA_PAIRS = {
    frozenset((0, 17)),   # Ashwini – Jyeshtha
    frozenset((1, 16)),   # Bharani – Anuradha
    frozenset((2, 15)),   # Krittika – Vishakha
    frozenset((3, 14)),   # Rohini – Swati
    frozenset((4, 13)),   # Mrigashira – Chitra
    frozenset((5, 12)),   # Ardra – Hasta
    frozenset((6, 21)),   # Punarvasu – Shravana
    frozenset((7, 20)),   # Pushya – Uttara Ashadha
    frozenset((8, 19)),   # Ashlesha – Purva Ashadha
    frozenset((9, 18)),   # Magha – Mula
    frozenset((10, 26)),  # Purva Phalguni – Revati
    frozenset((11, 25)),  # Uttara Phalguni – Uttara Bhadrapada
    frozenset((22, 24)),  # Dhanishtha – Purva Bhadrapada
    frozenset((23, 23)),  # Shatabhisha (self-vedha, some texts)
}

# ── Rajju: the 27 nakshatras mapped to 5 body-parts (ārohaṇa/avarohaṇa weave).
# 0=Pada(foot) 1=Kati(hip) 2=Nabhi/Udara(navel) 3=Kantha(neck) 4=Siro(head)
# Pattern ascends 0-1-2-3-4 then descends 3-2-1-0 and repeats.
_RAJJU_SEQ = [0,1,2,3,4,3,2,1,0]
_RAJJU = [ _RAJJU_SEQ[i % 9] for i in range(27) ]
_RAJJU_NAME = {0:"Pada (Fuß)",1:"Kati (Hüfte)",2:"Nabhi (Nabel)",
               3:"Kantha (Hals)",4:"Siro (Kopf)"}
_RAJJU_HARM = {
    0:"traditionell mit Unruhe/Reisen assoziiert",
    1:"traditionell mit Themen um Kinder & Wohlstand assoziiert",
    2:"traditionell mit Belastung der Partnerschaft assoziiert",
    3:"traditionell als Belastung für die Gesundheit der Frau gedeutet",
    4:"traditionell als schwerster Rajju gewertet (Gesundheit des Mannes)",
}


def _vedha_check(na, nb):
    present = frozenset((na, nb)) in _VEDHA_PAIRS
    return {"present": present,
            "verdict": "Vedha-Hinweis vorhanden (Nakshatra-Obstruktion) — klassisch als "
                       "zu beachtender Punkt gewertet; im Gesamtbild und mit möglichen "
                       "Aufhebungen einzuordnen."
                       if present else "Kein Vedha — keine Nakshatra-Obstruktion (günstig)."}


def _rajju_check(na, nb):
    ra, rb = _RAJJU[na], _RAJJU[nb]
    same = (ra == rb)
    return {
        "same": same,
        "part_a": _RAJJU_NAME[ra], "part_b": _RAJJU_NAME[rb],
        "part": _RAJJU_NAME[ra] if same else None,
        "harm": _RAJJU_HARM[ra] if same else None,
        "verdict": (f"Beide Monde in {_RAJJU_NAME[ra]} (gleiche Rajju) — {_RAJJU_HARM[ra]}. "
                    f"Klassisch als zu beachtender Punkt gewertet; kann durch andere "
                    f"stärkende Faktoren (Parihara) ausgeglichen werden."
                    if same else "Verschiedene Rajju — günstig, kein Rajju-Hinweis.")
    }


def _stri_dirgha_check(na_male, nb_female):
    """Strī-Dīrgha: count from the woman's nakshatra to the man's.
    Auspicious if the count is greater than 9 (some texts: >=9)."""
    count = ((na_male - nb_female) % 27) + 1
    ok = count > 9
    return {
        "count": count, "ok": ok,
        "verdict": (f"Strī-Dīrgha erfüllt (Zählung {count} > 9) — günstig für Langlebigkeit & Wohlstand."
                    if ok else
                    f"Strī-Dīrgha nicht erfüllt (Zählung {count} ≤ 9) — klassisch ein schwächerer Punkt, "
                    f"im Gesamtbild jedoch nachrangig gegenüber den Kern-Kūṭas.")
    }


def _rasi_kuta_check(sa_male, sb_female):
    """Rāśi Kūṭa (standalone): position of Moon-signs relative to each other.
    Auspicious when the man's Moon-sign is in the 7th–12th from the woman's,
    and the woman's Moon-sign in the 2nd–12th from the man's (classical rule).
    2/12 (dwir-dwadasha), 5/9 (nava-pancham), 6/8 (shashtashtaka) are examined."""
    # distance man from woman, and woman from man (1-based)
    d_m_from_w = ((sa_male - sb_female) % 12) + 1
    d_w_from_m = ((sb_female - sa_male) % 12) + 1
    pair = frozenset((d_m_from_w, d_w_from_m))
    # classical adverse combinations
    if pair == frozenset((6, 8)):
        ok, note = False, "Shashtashtaka (6/8) — klassisch ein sensibler Punkt; auf Ausgleich durch andere Faktoren achten."
    elif pair == frozenset((5, 9)):
        ok, note = True, "Nava-Pancham (5/9) — günstig, harmonisch."
    elif pair == frozenset((2, 12)):
        ok, note = False, "Dwir-Dwadasha (2/12) — gemischt; im Gesamtbild einzuordnen."
    elif d_m_from_w == 1:
        ok, note = True, "Gleiches Mondzeichen — vertraut, aber prüfe Nadi/Rajju."
    else:
        # man's sign in 7th–12th from woman is classically favourable
        ok = d_m_from_w in (7, 8, 9, 10, 11, 12) or d_w_from_m in (2,3,4,5,6,7)
        note = ("Mondzeichen-Stellung günstig." if ok
                else "Mondzeichen-Stellung neutral bis leicht ungünstig.")
    return {
        "ok": ok,
        "man_from_woman": d_m_from_w,
        "woman_from_man": d_w_from_m,
        "verdict": note,
    }


def compute_extra_milana(chart_a, chart_b):
    """Extra factors. chart_a = male, chart_b = female (by caller convention)."""
    ma, mb = chart_a["planets"]["Moon"], chart_b["planets"]["Moon"]
    nak_names = [n for n, _ in NAKSHATRAS]
    na = nak_names.index(ma["nakshatra"])   # male
    nb = nak_names.index(mb["nakshatra"])   # female
    sa, sb = ma["sign_idx"], mb["sign_idx"]
    return {
        "vedha":       _vedha_check(na, nb),
        "rajju":       _rajju_check(na, nb),
        "stri_dirgha": _stri_dirgha_check(na, nb),
        "rasi_kuta":   _rasi_kuta_check(sa, sb),
    }
