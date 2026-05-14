# SpeculAIr Modern Thematic Discovery Map
# Maps FMP's legacy "industry" classifications to modern, actionable retail investment themes.

MODERN_THEMES = {
    "AI & Semiconductors": [
        "Semiconductors", 
        "Semiconductor Equipment & Materials"
    ],
    "SaaS & Cloud Computing": [
        "Software - Infrastructure", 
        "Software - Application",
        "Information Technology Services"
    ],
    "Electrification & Clean Energy": [
        "Auto Manufacturers", # Captures TSLA, RIVN
        "Solar", 
        "Electrical Equipment & Parts",
        "Uranium",
        "Utilities - Renewable"
    ],
    "Cybersecurity & Data": [
        # Some cybersecurity is lumped in Software - Infrastructure, but we can tag specific industries or use an ETF list later
    ],
    "Biotech & Life Sciences": [
        "Biotechnology", 
        "Drug Manufacturers - General", 
        "Drug Manufacturers - Specialty & Generic",
        "Medical Instruments & Supplies",
        "Diagnostics & Research"
    ],
    "Space & Defense": [
        "Aerospace & Defense"
    ],
    "Digital Payments & Fintech": [
        "Credit Services",
        "Financial Data & Stock Exchanges"
    ],
    "Digital Media & E-Commerce": [
        "Internet Content & Information", 
        "Internet Retail",
        "Entertainment",
        "Electronic Gaming & Multimedia"
    ],
    "Infrastructure & Industrials": [
        "Building Products & Equipment",
        "Engineering & Construction",
        "Industrial Machinery",
        "Specialty Industrial Machinery"
    ],
    "Commodities & Energy": [
        "Oil & Gas E&P",
        "Oil & Gas Integrated",
        "Oil & Gas Midstream",
        "Gold",
        "Other Industrial Metals & Mining"
    ],
    "Consumer Brands & Retail": [
        "Apparel Retail",
        "Apparel Manufacturing",
        "Restaurants",
        "Footwear & Accessories",
        "Packaged Foods",
        "Household & Personal Products"
    ],
    "Housing & Real Estate": [
        "REIT - Industrial",
        "REIT - Retail",
        "REIT - Office",
        "REIT - Residential",
        "REIT - Healthcare Facilities",
        "Real Estate Services",
        "Residential Construction"
    ]
}

# Invert for O(1) lookup
INDUSTRY_TO_THEME = {}
for theme, industries in MODERN_THEMES.items():
    for ind in industries:
        INDUSTRY_TO_THEME[ind] = theme

def get_modern_theme(industry: str) -> str:
    """Returns a curated SpeculAIr theme based on FMP industry, or 'Broad Market' if uncategorized."""
    if not industry:
        return "Broad Market"
    return INDUSTRY_TO_THEME.get(industry, "Broad Market")
