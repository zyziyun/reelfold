"""Offline place names for footage: DJI flight logs (the ``.SRT`` a DJI drone / Osmo writes beside each clip) ->
the nearest well-known city, in English and Chinese. Nothing leaves the computer and only the city name is used
(never coordinates in copy).

    from vstudio import places
    places.from_footage(["DJI_0001.MP4", ...])   # {"en": "Seattle", "zh": "西雅图", "km": 19.6, "country": "US",
                                                 #  "date": "2026-10-10", "aerial": True, "alt_m": 85.0} | None
    places.nearest(47.76, -122.18)               # {"en": "Seattle", "zh": "西雅图", "km": 19.6, "country": "US"}

The gazetteer is a short hand-made list of major cities and travel destinations (public facts); a point farther
than ``MAX_KM`` from all of them has no name (the copy then says nothing about where).
"""
import glob
import math
import os
import re

MAX_KM = 60.0

# (en, zh, country, lat, lon)
CITIES = [
    ("Seattle", "西雅图", "US", 47.606, -122.332), ("Portland", "波特兰", "US", 45.515, -122.679),
    ("Vancouver", "温哥华", "CA", 49.283, -123.121), ("San Francisco", "旧金山", "US", 37.775, -122.419),
    ("San Jose", "圣何塞", "US", 37.338, -121.886), ("Los Angeles", "洛杉矶", "US", 34.052, -118.244),
    ("San Diego", "圣地亚哥", "US", 32.716, -117.161), ("Las Vegas", "拉斯维加斯", "US", 36.170, -115.140),
    ("Phoenix", "凤凰城", "US", 33.448, -112.074), ("Salt Lake City", "盐湖城", "US", 40.761, -111.891),
    ("Denver", "丹佛", "US", 39.739, -104.990), ("Austin", "奥斯汀", "US", 30.267, -97.743),
    ("Dallas", "达拉斯", "US", 32.777, -96.797), ("Houston", "休斯顿", "US", 29.760, -95.370),
    ("Chicago", "芝加哥", "US", 41.878, -87.630), ("Minneapolis", "明尼阿波利斯", "US", 44.978, -93.265),
    ("New Orleans", "新奥尔良", "US", 29.951, -90.072), ("Atlanta", "亚特兰大", "US", 33.749, -84.388),
    ("Miami", "迈阿密", "US", 25.762, -80.192), ("Orlando", "奥兰多", "US", 28.538, -81.379),
    ("Washington, D.C.", "华盛顿", "US", 38.907, -77.037), ("Philadelphia", "费城", "US", 39.953, -75.165),
    ("New York", "纽约", "US", 40.713, -74.006), ("Boston", "波士顿", "US", 42.360, -71.059),
    ("Honolulu", "檀香山", "US", 21.307, -157.858), ("Anchorage", "安克雷奇", "US", 61.218, -149.900),
    ("Yosemite", "优胜美地", "US", 37.865, -119.538), ("Grand Canyon", "大峡谷", "US", 36.107, -112.113),
    ("Yellowstone", "黄石公园", "US", 44.428, -110.588), ("Mount Rainier", "雷尼尔山", "US", 46.853, -121.760),
    ("Toronto", "多伦多", "CA", 43.653, -79.383), ("Montreal", "蒙特利尔", "CA", 45.502, -73.567),
    ("Banff", "班夫", "CA", 51.178, -115.571), ("Calgary", "卡尔加里", "CA", 51.045, -114.057),
    ("Mexico City", "墨西哥城", "MX", 19.433, -99.133), ("Cancún", "坎昆", "MX", 21.162, -86.851),
    ("Havana", "哈瓦那", "CU", 23.113, -82.366), ("Lima", "利马", "PE", -12.046, -77.043),
    ("Cusco", "库斯科", "PE", -13.532, -71.967), ("Bogotá", "波哥大", "CO", 4.711, -74.072),
    ("Rio de Janeiro", "里约热内卢", "BR", -22.907, -43.173), ("São Paulo", "圣保罗", "BR", -23.551, -46.633),
    ("Buenos Aires", "布宜诺斯艾利斯", "AR", -34.604, -58.382), ("Santiago", "圣地亚哥", "CL", -33.449, -70.669),
    ("London", "伦敦", "GB", 51.507, -0.128), ("Edinburgh", "爱丁堡", "GB", 55.953, -3.188),
    ("Dublin", "都柏林", "IE", 53.350, -6.260), ("Paris", "巴黎", "FR", 48.857, 2.352),
    ("Nice", "尼斯", "FR", 43.710, 7.262), ("Lyon", "里昂", "FR", 45.764, 4.836),
    ("Amsterdam", "阿姆斯特丹", "NL", 52.368, 4.904), ("Brussels", "布鲁塞尔", "BE", 50.850, 4.352),
    ("Berlin", "柏林", "DE", 52.520, 13.405), ("Munich", "慕尼黑", "DE", 48.135, 11.582),
    ("Zurich", "苏黎世", "CH", 47.377, 8.542), ("Interlaken", "因特拉肯", "CH", 46.686, 7.863),
    ("Vienna", "维也纳", "AT", 48.208, 16.374), ("Prague", "布拉格", "CZ", 50.076, 14.438),
    ("Budapest", "布达佩斯", "HU", 47.498, 19.040), ("Rome", "罗马", "IT", 41.903, 12.496),
    ("Florence", "佛罗伦萨", "IT", 43.770, 11.256), ("Venice", "威尼斯", "IT", 45.441, 12.316),
    ("Milan", "米兰", "IT", 45.464, 9.190), ("Barcelona", "巴塞罗那", "ES", 41.385, 2.173),
    ("Madrid", "马德里", "ES", 40.417, -3.704), ("Lisbon", "里斯本", "PT", 38.722, -9.139),
    ("Athens", "雅典", "GR", 37.984, 23.728), ("Santorini", "圣托里尼", "GR", 36.393, 25.462),
    ("Istanbul", "伊斯坦布尔", "TR", 41.008, 28.978), ("Cappadocia", "卡帕多奇亚", "TR", 38.643, 34.828),
    ("Copenhagen", "哥本哈根", "DK", 55.676, 12.568), ("Stockholm", "斯德哥尔摩", "SE", 59.329, 18.069),
    ("Oslo", "奥斯陆", "NO", 59.914, 10.752), ("Tromsø", "特罗姆瑟", "NO", 69.649, 18.956),
    ("Reykjavík", "雷克雅未克", "IS", 64.147, -21.943), ("Helsinki", "赫尔辛基", "FI", 60.170, 24.938),
    ("Moscow", "莫斯科", "RU", 55.756, 37.617), ("Dubai", "迪拜", "AE", 25.205, 55.271),
    ("Cairo", "开罗", "EG", 30.044, 31.236), ("Marrakech", "马拉喀什", "MA", 31.629, -7.981),
    ("Cape Town", "开普敦", "ZA", -33.925, 18.424), ("Nairobi", "内罗毕", "KE", -1.292, 36.822),
    ("Sydney", "悉尼", "AU", -33.869, 151.209), ("Melbourne", "墨尔本", "AU", -37.814, 144.963),
    ("Brisbane", "布里斯班", "AU", -27.470, 153.026), ("Perth", "珀斯", "AU", -31.950, 115.860),
    ("Auckland", "奥克兰", "NZ", -36.849, 174.763), ("Queenstown", "皇后镇", "NZ", -45.031, 168.663),
    ("Tokyo", "东京", "JP", 35.676, 139.650), ("Kyoto", "京都", "JP", 35.012, 135.768),
    ("Osaka", "大阪", "JP", 34.694, 135.502), ("Sapporo", "札幌", "JP", 43.062, 141.354),
    ("Fukuoka", "福冈", "JP", 33.590, 130.402), ("Okinawa", "冲绳", "JP", 26.212, 127.681),
    ("Seoul", "首尔", "KR", 37.567, 126.978), ("Busan", "釜山", "KR", 35.180, 129.076),
    ("Jeju", "济州岛", "KR", 33.489, 126.498), ("Taipei", "台北", "TW", 25.033, 121.565),
    ("Hong Kong", "香港", "HK", 22.320, 114.169), ("Macau", "澳门", "MO", 22.199, 113.544),
    ("Singapore", "新加坡", "SG", 1.352, 103.820), ("Kuala Lumpur", "吉隆坡", "MY", 3.139, 101.687),
    ("Bangkok", "曼谷", "TH", 13.756, 100.502), ("Chiang Mai", "清迈", "TH", 18.788, 98.985),
    ("Phuket", "普吉岛", "TH", 7.880, 98.392), ("Bali", "巴厘岛", "ID", -8.409, 115.189),
    ("Hanoi", "河内", "VN", 21.028, 105.854), ("Ho Chi Minh City", "胡志明市", "VN", 10.823, 106.630),
    ("Manila", "马尼拉", "PH", 14.600, 120.984), ("Delhi", "德里", "IN", 28.614, 77.209),
    ("Mumbai", "孟买", "IN", 19.076, 72.878), ("Kathmandu", "加德满都", "NP", 27.717, 85.324),
    ("Beijing", "北京", "CN", 39.904, 116.407), ("Shanghai", "上海", "CN", 31.230, 121.474),
    ("Guangzhou", "广州", "CN", 23.129, 113.264), ("Shenzhen", "深圳", "CN", 22.543, 114.058),
    ("Hangzhou", "杭州", "CN", 30.274, 120.155), ("Suzhou", "苏州", "CN", 31.299, 120.585),
    ("Nanjing", "南京", "CN", 32.060, 118.797), ("Chengdu", "成都", "CN", 30.573, 104.066),
    ("Chongqing", "重庆", "CN", 29.563, 106.551), ("Xi'an", "西安", "CN", 34.341, 108.940),
    ("Wuhan", "武汉", "CN", 30.593, 114.305), ("Changsha", "长沙", "CN", 28.228, 112.939),
    ("Xiamen", "厦门", "CN", 24.480, 118.089), ("Qingdao", "青岛", "CN", 36.067, 120.383),
    ("Dalian", "大连", "CN", 38.914, 121.615), ("Harbin", "哈尔滨", "CN", 45.803, 126.535),
    ("Kunming", "昆明", "CN", 25.039, 102.718), ("Dali", "大理", "CN", 25.607, 100.268),
    ("Lijiang", "丽江", "CN", 26.855, 100.227), ("Guilin", "桂林", "CN", 25.274, 110.290),
    ("Sanya", "三亚", "CN", 18.253, 109.512), ("Lhasa", "拉萨", "CN", 29.652, 91.172),
    ("Urumqi", "乌鲁木齐", "CN", 43.825, 87.617), ("Zhangjiajie", "张家界", "CN", 29.117, 110.479),
    ("Huangshan", "黄山", "CN", 30.133, 118.167), ("Jiuzhaigou", "九寨沟", "CN", 33.260, 103.918),
]


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))


def nearest(lat, lon, max_km=MAX_KM):
    """The closest gazetteer city within ``max_km`` -> {en, zh, country, km} or None."""
    best = min(CITIES, key=lambda c: haversine_km(lat, lon, c[3], c[4]))
    km = haversine_km(lat, lon, best[3], best[4])
    if km > max_km:
        return None
    return dict(en=best[0], zh=best[1], country=best[2], km=round(km, 1))


_LAT = re.compile(r"\[latitude\s*:\s*(-?\d+(?:\.\d+)?)\]")
_LON = re.compile(r"\[lon(?:gi|gt)?tude\s*:\s*(-?\d+(?:\.\d+)?)\]")
_GPS = re.compile(r"GPS\s*\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")          # older DJI: GPS(lon, lat, alt)
_ALT = re.compile(r"rel_alt\s*:\s*(-?\d+(?:\.\d+)?)")
_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")


def read_srt(path, max_bytes=400000):
    """A DJI flight-log subtitle -> {lat, lon, alt_m, date} (median position, max relative altitude) or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read(max_bytes)
    except OSError:
        return None
    lats = [float(x) for x in _LAT.findall(txt)]
    lons = [float(x) for x in _LON.findall(txt)]
    if not lats or not lons:
        g = _GPS.findall(txt)
        lons, lats = [float(a) for a, _b in g], [float(b) for _a, b in g]
    pts = [(a, b) for a, b in zip(lats, lons) if abs(a) > 1e-6 or abs(b) > 1e-6]
    if not pts:
        return None
    pts.sort()
    lat, lon = pts[len(pts) // 2]
    alts = [float(x) for x in _ALT.findall(txt)]
    d = _DATE.search(txt)
    return dict(lat=lat, lon=lon, alt_m=max(alts) if alts else None, date="-".join(d.groups()) if d else None)


def srt_for(video):
    stem = os.path.splitext(video)[0]
    for ext in (".SRT", ".srt"):
        if os.path.isfile(stem + ext):
            return stem + ext
    hits = glob.glob(glob.escape(stem) + ".[sS][rR][tT]")
    return hits[0] if hits else None


def from_footage(videos, max_km=MAX_KM):
    """The place of a set of clips (their DJI logs; the most common city wins) -> {en, zh, country, km, date,
    aerial, alt_m} or None when no clip has a log or none is near a known city. ``aerial``: a log flew higher than
    20 m (a drone shot, not a handheld Osmo)."""
    found, alts, dates = {}, [], []
    for v in videos or []:
        s = srt_for(str(v))
        r = read_srt(s) if s else None
        if not r:
            continue
        if r.get("alt_m") is not None:
            alts.append(r["alt_m"])
        if r.get("date"):
            dates.append(r["date"])
        c = nearest(r["lat"], r["lon"], max_km)
        if c:
            found.setdefault(c["en"], []).append(c)
    if not found and not alts:
        return None
    out = {}
    if found:
        name = max(found, key=lambda k: (len(found[k]), -min(c["km"] for c in found[k])))
        out = dict(found[name][0], km=min(c["km"] for c in found[name]))
    if dates:
        out["date"] = sorted(dates)[0]
    if alts:
        out["alt_m"] = round(max(alts), 1)
        out["aerial"] = max(alts) > 20
    return out or None
