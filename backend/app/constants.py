COMMODITIES: dict[str, str] = {
    "CL=F": "Crude Oil (WTI)",
    "NG=F": "Natural Gas",
    "HO=F": "Heating Oil",
    "RB=F": "RBOB Gasoline",
    "BZ=F": "Brent Crude",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "HG=F": "Copper",
    "PL=F": "Platinum",
    "PA=F": "Palladium",
    "ZC=F": "Corn",
    "ZW=F": "Wheat",
    "ZS=F": "Soybeans",
    "KC=F": "Coffee",
    "CT=F": "Cotton",
    "SB=F": "Sugar",
    "CC=F": "Cocoa",
}

RSS_FEEDS: dict[str, str] = {
    "energy": "https://feeds.reuters.com/reuters/businessNews",
    "metals": "https://www.mining.com/feed/",
    "agriculture": "https://www.agweb.com/rss/news",
    "general": "https://feeds.bloomberg.com/markets/news.rss",
}

COMMODITY_KEYWORDS: dict[str, list[str]] = {
    "CL=F": ["crude", "oil", "opec", "wti", "petroleum", "shale"],
    "NG=F": ["natural gas", "lng", "gas supply"],
    "HO=F": ["heating oil", "fuel oil", "distill"],
    "RB=F": ["gasoline", "rbob"],
    "BZ=F": ["brent", "north sea crude"],
    "GC=F": ["gold", "bullion", "precious metal"],
    "SI=F": ["silver"],
    "HG=F": ["copper", "lme"],
    "PL=F": ["platinum"],
    "PA=F": ["palladium"],
    "ZC=F": ["corn", "maize", "ethanol"],
    "ZW=F": ["wheat", "grain", "ukraine"],
    "ZS=F": ["soybean"],
    "KC=F": ["coffee"],
    "CT=F": ["cotton"],
    "SB=F": ["sugar"],
    "CC=F": ["cocoa"],
}

HORIZONS: tuple[str, ...] = ("5d", "10d", "21d")

FRED_SERIES: dict[str, str] = {
    "fed_funds_rate": "DFF",
    "usd_eur": "DEXUSEU",
    "usd_jpy": "DEXJPUS",
    "yield_spread_10y2y": "T10Y2Y",
    "breakeven_inflation": "T10YIE",
    "vix": "VIXCLS",
    "cpi": "CPIAUCSL",
    "unrate": "UNRATE",
    "wti_spot": "DCOILWTICO",
    "gold_fix": "GOLDAMGBD228NLBM",
}

REGIME_LABELS: dict[int, str] = {
    0: "Mean-reverting (Bear)",
    1: "Trending (Bull)",
    2: "High Volatility",
}

REDIS_SIGNAL_FILTERED_KEY = "signals:filtered"
REDIS_SIGNAL_RAW_KEY = "signals:raw"
REDIS_SIGNAL_META_KEY = "signals:meta"

REDIS_AGENT_ANALYSIS_KEY = "agent:analysis:latest"
REDIS_AGENT_META_KEY = "agent:analysis:meta"
REDIS_DAILY_SCAN_KEY = "agent:daily_scan:latest"
