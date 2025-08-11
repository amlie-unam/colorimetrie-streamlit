# -*- coding: utf-8 -*-
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from fpdf import FPDF

# =========================
# Utils NCS -> RGB (approx)
# =========================
BASE = {
    "R": (1.0, 0.0, 0.0),
    "Y": (1.0, 1.0, 0.0),
    "G": (0.0, 1.0, 0.0),
    "B": (0.0, 0.0, 1.0),
    "W": (1.0, 1.0, 1.0),
    "S": (0.0, 0.0, 0.0),  # Svart/Black
}

def _mix(c1, c2, t):
    return tuple((1 - t) * a + t * b for a, b in zip(c1, c2))

def hue_to_rgb(hue: str):
    if not hue or hue.upper() == "N":
        return BASE["W"]
    hue = hue.strip().upper()
    if hue in BASE:
        return BASE[hue]
    m = re.match(r"^([RGBY])(\d{1,2})([RGBY])$", hue)
    if m:
        a, pct, b = m.group(1), int(m.group(2)), m.group(3)
        t = pct / 100.0
        return _mix(BASE[a], BASE[b], t)
    letters = [ch for ch in hue if ch in BASE]
    if not letters:
        return BASE["W"]
    r = sum(BASE[ch][0] for ch in letters) / len(letters)
    g = sum(BASE[ch][1] for ch in letters) / len(letters)
    b = sum(BASE[ch][2] for ch in letters) / len(letters)
    return (r, g, b)

def ncs_to_rgb(ncs_code: str):
    """
    Attend 'SBBCC-HUE' (ex: S0502-Y, S3560-Y30R, S0300-N)
    Retourne un tuple (R,G,B) en 0..255
    """
    m = re.match(r"^S\s*(\d{2})(\d{2})\s*-\s*([A-Z](?:\d{1,2}[A-Z])?|N)$", (ncs_code or "").replace(" ", ""))
    if not m:
        return (200, 200, 200)
    blackness = int(m.group(1))
    chroma    = int(m.group(2))
    hue       = m.group(3)
    whiteness = max(0, 100 - blackness - chroma)

    hr, hg, hb = hue_to_rgb(hue)
    r = (chroma/100.0)*hr + (whiteness/100.0)*BASE["W"][0] + (blackness/100.0)*BASE["S"][0]
    g = (chroma/100.0)*hg + (whiteness/100.0)*BASE["W"][1] + (blackness/100.0)*BASE["S"][1]
    b = (chroma/100.0)*hb + (whiteness/100.0)*BASE["W"][2] + (blackness/100.0)*BASE["S"][2]
    return (int(round(r*255)), int(round(g*255)), int(round(b*255)))

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)

# =========================
# Chargement des données
# =========================
st.set_page_config(page_title="Nuancier NCS", layout="wide")

@st.cache_data
def load_data():
    return pd.read_csv("palette_ncs_avec_adjectifs.csv", sep=";")

df = load_data()

# =========================
# UI filtres (2 options)
# =========================
col1, col2, col3 = st.columns(3)
temperature = col1.selectbox("Température", ["chaud", "froid"], index=0)
clarte      = col2.selectbox("Clarté", ["clair", "foncé"], index=0)
luminosite  = col3.selectbox("Luminance", ["lumineux", "mat"], index=0)
inclure_neutres = st.toggle("Inclure aussi les neutres (autour de S3030)", value=False)

# =========================
# Filtrage
# =========================
mask = (
    (df["temperature"] == temperature) &
    (df["clarte"] == clarte) &
    (df["luminosite"] == luminosite)
)
if inclure_neutres:
    mask = mask | (
        (df["temperature"] == "neutre") &
        (df["clarte"] == clarte) &
        (df["luminosite"] == luminosite)
    )

result = df[mask].copy()
st.write(f"**{len(result)} couleurs** trouvées")

# =========================
# Couleurs HEX pour rendu
# =========================
result["rgb"] = result["ncs_code"].apply(ncs_to_rgb)
result["hex"] = result["rgb"].apply(rgb_to_hex)

# =========================
# Aperçu tableau
# =========================
st.dataframe(
    result[["ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte"]],
    use_container_width=True
)

# =========================
# Export CSV
# =========================
st.download_button(
    "Exporter la sélection (CSV)",
    data=result[["ncs_code", "nom", "hex", "noirceur%", "saturation%", "teinte"]]
         .to_csv(index=False, sep=";").encode("utf-8"),
    file_name="selection_couleurs.csv",
    mime="text/csv"
)

# =========================
# PDF (via FPDF, pas reportlab)
# =========================
def generate_pdf(dataframe: pd.DataFrame, temperature: str, clarte: str, luminosite: str) -> bytes:
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 8, f"Sélection ({temperature}, {clarte}, {luminosite})", ln=1)

    # Grille 3 colonnes
    left_margin = 15
    right_margin = 15
    usable_width = 210 - left_margin - right_margin
    cols = 3
    swatch_w = usable_width / cols
    swatch_h = 25  # hauteur rectangle couleur
    gap_y = 10

    col = 0
    x0 = left_margin
    y = pdf.get_y() + 5

    for _, row in dataframe.iterrows():
        x = x0 + col * swatch_w

        # Pastille couleur
        r, g, b = row["rgb"]
        pdf.set_fill_color(r, g, b)
        pdf.rect(x, y, swatch_w, swatch_h, style='F')

        # Texte
        pdf.set_xy(x, y + swatch_h + 3)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=9)
        label1 = f"{row['ncs_code']}  |  {row['nom']}"
        label2 = f"Noirceur: {row['noirceur%']}  |  Saturation: {row['saturation%']}  |  Teinte: {row['teinte']}  |  {row['hex']}"
        pdf.multi_cell(w=swatch_w, h=5, txt=label1, border=0, align='L')
        pdf.set_x(x)
        pdf.multi_cell(w=swatch_w, h=5, txt=label2, border=0, align='L')

        col += 1
        if col >= cols:
            col = 0
            y = pdf.get_y() + gap_y
            # Nouvelle page si on arrive en bas
            if y + swatch_h + 20 > 297 - 15:  # A4 hauteur 297mm
                pdf.add_page()
                y = pdf.get_y() + 5

    # Retour bytes
    out = BytesIO()
    pdf.output(out)
    return out.getvalue()

pdf_bytes = generate_pdf(result, temperature, clarte, luminosite)

st.download_button(
    "Télécharger la sélection en PDF",
    data=pdf_bytes,
    file_name="selection_couleurs.pdf",
    mime="application/pdf"
)

st.caption("Note : conversion NCS→RGB approximative (fidèle pour écran).")
