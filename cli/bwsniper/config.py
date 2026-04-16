"""
cli/bwsniper/config.py — Constants for the TUI client.

Only TUI-related constants live here.  API / BW-specific config is on the server.
"""

# ── Tab indices ──────────────────────────────────────────────────────────────
VIEW_MONITOR  = 0
VIEW_HISTORY  = 1
VIEW_CART     = 2
VIEW_BROWSE   = 3
VIEW_LOG      = 4
VIEW_SETTINGS = 5
VIEW_COUNT    = 6

# ── Browse tab ───────────────────────────────────────────────────────────────
BROWSE_SORTS = [
    "EndingSoonest", "EndingLatest", "NewArrivals",
    "CurrentPriceLowest", "CurrentPriceHighest",
    "RetailPriceLowest",  "RetailPriceHighest",
    "BidsLowest",         "BidsHighest",
]
BROWSE_SORT_LABELS = {
    "EndingSoonest":       "Ending Soonest",
    "EndingLatest":        "Ending Latest",
    "NewArrivals":         "New Arrivals",
    "CurrentPriceLowest":  "Price ↑",
    "CurrentPriceHighest": "Price ↓",
    "RetailPriceLowest":   "Retail ↑",
    "RetailPriceHighest":  "Retail ↓",
    "BidsLowest":          "Bids ↑",
    "BidsHighest":         "Bids ↓",
}

QUICK_FILTERS = [
    ("NewArrivals",        "New Arrivals"),
    ("Hottest",            "Hottest"),
    ("ThreeDollarsOrLess", "$3 or Less"),
    ("EndsToday",          "Ends Today"),
    ("EndsTomorrow",       "Ends Tomorrow"),
    ("NoBidsYet",          "No Bids Yet"),
    ("Over90PercentOff",   "90%+ Off"),
]

COND_MAP = {
    "New":          "New",          "AppearsNew":     "Appears New",
    "UsedGood":     "Good",         "UsedFair":       "Fair",
    "Damaged":      "Damaged",      "GentlyUsed":     "Gently Used",
    "Used":         "Used",         "EasyFix":        "Easy Fix",
    "HeavyUse":     "Heavy Use",    "MajorFix":       "Major Fix",
    "MixedCondition": "Mixed",
}

COND_CYCLE = [
    ("",               "All"),
    ("New",            "New"),
    ("AppearsNew",     "Appears New"),
    ("GentlyUsed",     "Gently Used"),
    ("UsedGood",       "Good"),
    ("Used",           "Used"),
    ("UsedFair",       "Fair"),
    ("Damaged",        "Damaged"),
    ("EasyFix",        "Easy Fix"),
    ("HeavyUse",       "Heavy Use"),
    ("MajorFix",       "Major Fix"),
    ("MixedCondition", "Mixed"),
]

SITE_BASE = "https://www.buywander.com"
